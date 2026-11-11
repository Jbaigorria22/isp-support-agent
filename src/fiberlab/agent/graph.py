"""The L1 support flow as a LangGraph state machine (ADR-0001).

Design rules:
  - Nodes that WAIT for the customer only call interrupt() and do nothing else.
    LangGraph re-runs a node from the top when it resumes, so side effects
    (tool calls) must never sit before an interrupt.
  - Tools are called by code here, never chosen by the LLM.
"""

import operator
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from fiberlab.agent import rules
from fiberlab.agent.brain import Brain
from fiberlab.agent.retrieval import Retriever
from fiberlab.agent.toolbox import Toolbox

MAX_VERIFY_ATTEMPTS = 3
MAX_WIFI_PASSWORD_ATTEMPTS = 3

OFFER_WIFI_CHANGE = "offer_wifi_change"
AWAIT_WIFI_PASSWORD = "await_wifi_password"
CANCELLED = "cancelled"

PASSWORD_PROBLEMS = {
    "too_short": "tiene menos de 10 caracteres",
    "too_long": "tiene más de 63 caracteres",
    "has_spaces": "tiene espacios",
    "needs_letter_and_digit": "necesita letras y números",
    "contains_network_name": "no puede contener el nombre de la red",
}

GREETING = (
    "¡Hola! Soy el asistente técnico de FiberLab. Para ayudarte necesito tu número "
    "de cliente (por ejemplo C1234) y los últimos 3 dígitos de tu documento."
)


class State(TypedDict, total=False):
    transcript: Annotated[list[str], operator.add]  # "agent: ..." / "customer: ..."
    prompt: str                 # what the agent says at the next interrupt
    last_reply: str             # customer's last message
    verify_attempts: int
    session_token: str
    customer_id: str
    first_name: str
    zone: str
    problem: str
    intent: str
    facts: dict
    outcome: str
    reason: str
    restarted: bool
    guide_attempts: int
    guidance: str
    guides_used: Annotated[list[str], operator.add]  # knowledge-base guide IDs, for audit
    wifi_attempts: int
    steps_tried: Annotated[list[str], operator.add]
    ticket_id: str
    final_message: str


def build_graph(brain: Brain, toolbox: Toolbox, retriever: Retriever | None = None, checkpointer=None):
    retriever = retriever or Retriever()
    # ----- waiting nodes (interrupt only) ---------------------------------- #

    def ask(state: State) -> State:
        reply = interrupt({"say": state["prompt"]})
        # A new WiFi password is a secret: it never enters the transcript.
        shown = "[redacted]" if state.get("outcome") == AWAIT_WIFI_PASSWORD else reply
        return {"last_reply": reply, "transcript": [f"agent: {state['prompt']}", f"customer: {shown}"]}

    # ----- working nodes --------------------------------------------------- #

    def start(state: State) -> State:
        return {"prompt": GREETING, "verify_attempts": 0, "guide_attempts": 0, "restarted": False}

    async def verify(state: State) -> State:
        attempts = state.get("verify_attempts", 0) + 1
        ident = brain.extract_identity(state["last_reply"])
        if not ident.get("customer_id") or not ident.get("doc_last3"):
            return {"verify_attempts": attempts,
                    "prompt": "No llegué a ver los datos. Pasame tu número de cliente y los últimos 3 dígitos de tu documento."}

        result = await toolbox.call("verify_customer", customer_id=ident["customer_id"], doc_last3=ident["doc_last3"])
        if not result.get("ok"):
            return {"verify_attempts": attempts,
                    "prompt": "No pude verificar esos datos. Revisalos y volvé a intentar, por favor."}

        return {
            "verify_attempts": attempts,
            "session_token": result["session_token"],
            "customer_id": ident["customer_id"].upper(),
            "first_name": result["first_name"],
            "zone": result["zone"],
            "prompt": f"¡Gracias, {result['first_name']}! Contame qué problema tenés con tu servicio.",
        }

    def classify(state: State) -> State:
        intent = brain.classify_intent(state["last_reply"])
        update: State = {"problem": state["last_reply"], "intent": intent}
        if intent == "out_of_scope":
            update |= {"outcome": rules.ESCALATE, "reason": "request is outside L1 technical support scope"}
        return update

    async def diagnose(state: State) -> State:
        token = state["session_token"]
        outages = await toolbox.call("get_area_outages", zone=state["zone"])
        modem = await toolbox.call("get_modem_status", session_token=token)
        facts = {"outages": outages.get("active_outages", []), "modem": modem}
        if modem.get("status") == "online":
            facts["health"] = await toolbox.call("get_line_health", session_token=token)
        if state["intent"] == "slow_internet":
            facts["speeds"] = await toolbox.call("get_speed_history", session_token=token, days=7)
        decision = rules.decide(state["intent"], facts)
        return {"facts": facts, "outcome": decision.outcome, "reason": decision.reason}

    def offer_restart(state: State) -> State:
        return {"prompt": "Tu equipo de fibra figura desconectado. ¿Querés que lo reinicie a distancia? "
                          "Tarda unos minutos y se corta el servicio mientras tanto."}

    async def restart(state: State) -> State:
        if not brain.is_affirmative(state["last_reply"]):
            return {"outcome": rules.GUIDE, "reason": "customer declined the remote restart"}
        result = await toolbox.call("restart_modem", session_token=state["session_token"])
        if result.get("status_after_restart") == "online":
            return {"restarted": True, "steps_tried": ["remote ONT restart (recovered)"], "outcome": "solved",
                    "final_message": "¡Listo! Reinicié tu equipo y ya figura conectado. Si vuelve a pasar, escribinos."}
        decision = rules.decide(state["intent"], {**state["facts"], "modem": {"status": "offline"}}, already_restarted=True)
        return {"restarted": True, "steps_tried": ["remote ONT restart (did not recover)"],
                "outcome": decision.outcome, "reason": decision.reason}

    def guide(state: State) -> State:
        health = state.get("facts", {}).get("health", {}).get("status")
        found = retriever.search(
            problem=state["intent"], health=health if health in ("green", "red") else "green",
            query=state.get("problem", ""), k=1, exclude=state.get("guides_used", []),
        )
        if not found:
            return {"outcome": rules.ESCALATE, "reason": "no remaining knowledge-base guide for this problem"}
        text = brain.write_guidance(state.get("problem", ""), found[0])
        return {"guidance": text, "guides_used": [found[0].id], "outcome": rules.GUIDE,
                "prompt": f"{text}\n\n¿Se resolvió el problema?"}

    def check_resolved(state: State) -> State:
        attempts = state.get("guide_attempts", 0) + 1
        tried = [f"knowledge-base guide {state.get('guides_used', ['?'])[-1]} (attempt {attempts})"]
        if brain.is_affirmative(state["last_reply"]):
            return {"guide_attempts": attempts, "steps_tried": tried, "outcome": "solved",
                    "final_message": "¡Genial! Me alegra que se haya resuelto. ¡Que tengas buen día!"}
        escalation = rules.after_failed_guidance(attempts)
        if escalation:
            return {"guide_attempts": attempts, "steps_tried": tried,
                    "outcome": escalation.outcome, "reason": escalation.reason}
        return {"guide_attempts": attempts, "steps_tried": tried, "outcome": rules.GUIDE}

    async def escalate(state: State) -> State:
        intent = state.get("intent", "no_service")
        category = "outage" if state.get("outcome") == rules.OUTAGE else intent
        priority = "high" if category in ("no_service", "outage") else "medium"
        summary = brain.write_ticket_summary({
            "customer_id": state["customer_id"], "intent": intent, "problem": state.get("problem"),
            "facts": state.get("facts"), "steps_tried": state.get("steps_tried", []), "reason": state.get("reason"),
        })
        ticket = await toolbox.call(
            "create_ticket", session_token=state["session_token"], category=category, priority=priority,
            summary=summary, steps_tried="; ".join(state.get("steps_tried", [])) or "none",
        )
        ticket_id = ticket.get("ticket_id", "pendiente")
        if state.get("outcome") == rules.OUTAGE:
            outage = state["facts"]["outages"][0]
            message = (f"Hay un corte en tu zona ({outage['description']}). Estimamos que se resuelve en "
                       f"{outage['eta_hours']} horas. Registré tu reclamo con el número {ticket_id}.")
        else:
            message = (f"Derivé tu caso a nuestro equipo técnico especializado con el número {ticket_id}. "
                       f"Ya tienen todo el diagnóstico, así que no vas a tener que repetir nada.")
        return {"ticket_id": ticket_id, "final_message": message}

    async def wifi_offer(state: State) -> State:
        info = await toolbox.call("get_wifi_info", session_token=state["session_token"])
        return {"facts": {"wifi": info}, "outcome": OFFER_WIFI_CHANGE,
                "prompt": f"Puedo cambiar la clave de tu red {info['ssid']}. Al hacerlo se van a desconectar "
                          f"los {info['device_count']} dispositivos conectados y vas a tener que volver a "
                          f"conectarlos con la clave nueva. ¿Querés continuar?"}

    def wifi_confirm(state: State) -> State:
        if not brain.is_affirmative(state["last_reply"]):
            return {"outcome": CANCELLED, "final_message": "Perfecto, no cambié nada. Tu clave sigue siendo la misma."}
        return {"outcome": AWAIT_WIFI_PASSWORD, "wifi_attempts": 0,
                "prompt": "Escribí la nueva clave: entre 10 y 63 caracteres, con letras y números, sin espacios."}

    async def wifi_apply(state: State) -> State:
        # The password goes straight from the customer to the tool: the LLM never sees it.
        attempts = state.get("wifi_attempts", 0) + 1
        result = await toolbox.call("change_wifi_password", session_token=state["session_token"],
                                    new_password=state["last_reply"])
        update: State = {"last_reply": "[redacted]", "wifi_attempts": attempts}
        if result.get("ok"):
            return update | {"outcome": "solved", "steps_tried": ["WiFi password changed"],
                             "final_message": f"¡Listo! Cambié la clave de {result['ssid']}. "
                                              f"Volvé a conectar tus dispositivos con la clave nueva."}
        if attempts >= MAX_WIFI_PASSWORD_ATTEMPTS:
            return update | {"outcome": CANCELLED,
                             "final_message": "No pude aplicar una clave válida, así que no cambié nada. "
                                              "Podés volver a intentarlo cuando quieras."}
        problem = PASSWORD_PROBLEMS.get(result.get("code"), "no cumple los requisitos")
        return update | {"prompt": f"Esa clave {problem}. Probá con otra: entre 10 y 63 caracteres, "
                                   f"con letras y números, sin espacios."}

    def unverified(state: State) -> State:
        return {"outcome": "unverified",
                "final_message": "No pude verificar tu identidad. Por seguridad, comunicate por nuestros canales oficiales."}

    # ----- routing --------------------------------------------------------- #

    def after_ask(state: State) -> str:
        if not state.get("session_token"):
            return "verify"
        if not state.get("intent"):
            return "classify"
        if state.get("outcome") == rules.OFFER_RESTART:
            return "restart"
        if state.get("outcome") == OFFER_WIFI_CHANGE:
            return "wifi_confirm"
        if state.get("outcome") == AWAIT_WIFI_PASSWORD:
            return "wifi_apply"
        return "check_resolved"

    def after_verify(state: State) -> str:
        if state.get("session_token"):
            return "ask"
        return "unverified" if state["verify_attempts"] >= MAX_VERIFY_ATTEMPTS else "ask"

    def by_outcome(state: State) -> str:
        return {
            rules.OUTAGE: "escalate",
            rules.ESCALATE: "escalate",
            rules.OFFER_RESTART: "offer_restart",
            rules.GUIDE: "guide",
            "solved": END,
            CANCELLED: END,
        }[state["outcome"]]

    def after_classify(state: State) -> str:
        return {"out_of_scope": "escalate", "wifi_password": "wifi_offer"}.get(state["intent"], "diagnose")

    def end_or_ask(state: State) -> str:
        return END if state.get("outcome") in ("solved", CANCELLED) else "ask"

    g = StateGraph(State)
    for name, fn in [("start", start), ("ask", ask), ("verify", verify), ("classify", classify),
                     ("diagnose", diagnose), ("offer_restart", offer_restart), ("restart", restart),
                     ("guide", guide), ("check_resolved", check_resolved), ("escalate", escalate),
                     ("unverified", unverified), ("wifi_offer", wifi_offer),
                     ("wifi_confirm", wifi_confirm), ("wifi_apply", wifi_apply)]:
        g.add_node(name, fn)

    g.add_edge(START, "start")
    g.add_edge("start", "ask")
    g.add_conditional_edges("ask", after_ask,
                            ["verify", "classify", "restart", "check_resolved", "wifi_confirm", "wifi_apply"])
    g.add_conditional_edges("verify", after_verify, ["ask", "unverified"])
    g.add_conditional_edges("classify", after_classify, ["escalate", "wifi_offer", "diagnose"])
    g.add_edge("wifi_offer", "ask")
    g.add_conditional_edges("wifi_confirm", end_or_ask, ["ask", END])
    g.add_conditional_edges("wifi_apply", end_or_ask, ["ask", END])
    g.add_conditional_edges("diagnose", by_outcome, ["escalate", "offer_restart", "guide", END])
    g.add_edge("offer_restart", "ask")
    g.add_conditional_edges("restart", by_outcome, ["escalate", "guide", END])
    g.add_conditional_edges("guide", lambda s: "escalate" if s["outcome"] == rules.ESCALATE else "ask",
                            ["escalate", "ask"])
    g.add_conditional_edges("check_resolved", by_outcome, ["escalate", "guide", END])
    g.add_edge("escalate", END)
    g.add_edge("unverified", END)

    return g.compile(checkpointer=checkpointer or InMemorySaver())
