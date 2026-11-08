# ISP Support Agent

An L1 technical-support agent for **FiberLab**, a fictional internet provider.
It verifies the customer, diagnoses the connection with real tools, guides the
customer step by step and, when it cannot solve the case, escalates to Level 2
with a structured ticket.

Built with **LangGraph + MCP + Amazon Bedrock**, with a **security-first** design:
identity and escalation rules are enforced in code, not only in the prompt.

> All data is synthetic. FiberLab, its customers and its procedures are invented.

## Status

| Stage | Deliverable | Status |
|-------|-------------|--------|
| 0 | [Brief](docs/brief.md) + [ADR-0001](docs/adr/0001-agent-architecture.md) | ✅ |
| 1 | Simulated ISP backend + MCP server | ✅ |
| 2 | LangGraph agent (console) | ✅ |
| 3 | RAG knowledge base | ⏳ |
| 4 | Evals + LangSmith | ⏳ |
| 5 | Observability: OpenTelemetry + Prometheus + Grafana | ⏳ |
| 6 | Guardrails + security tests | ⏳ |
| 7 | Web UI + AWS deployment (Terraform) | ⏳ |

## How it works

```
Customer ⇄ LangGraph flow ──► MCP client ──stdio──► FiberLab MCP server ──► SQLite
              │
              └─► Brain (Amazon Bedrock): understands and writes text only
```

The LLM **never calls tools**. It extracts, classifies and writes; the graph decides
and calls tools in code. Escalation rules live in `agent/rules.py`.

```
start → ask → verify ─┬─► ask (problem) → classify → diagnose ─┬─► escalate (outage / bad signal / out of scope)
                      └─► unverified (3 failures)              ├─► offer_restart → ask → restart → solved | escalate
                                                               └─► guide → ask → check_resolved → solved | guide | escalate
```

## MCP tools

| Tool | Needs verified identity | Side effect |
|------|------------------------|-------------|
| `verify_customer` | – | Issues a signed session token |
| `get_area_outages` | No | – |
| `get_modem_status` | Yes | – |
| `get_speed_history` | Yes | – |
| `restart_modem` | Yes | Restarts the ONT |
| `create_ticket` | Yes | Creates an L2 ticket |

## Test scenarios (synthetic customers)

| Customer | Verification | Scenario | Expected outcome |
|----------|--------------|----------|------------------|
| C1001 | 482 | Area outage in CENTRO | Inform outage + ETA |
| C1002 | 137 | ONT hung | Remote restart fixes it |
| C1003 | 905 | Optical signal out of range | Escalate |
| C1004 | 268 | Line delivers plan, slow at home | WiFi guidance |
| C1005 | 551 | Everything healthy | Guide / close |
| C1006 | 319 | ONT offline, restart fails | Escalate |

## Run

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"

python -m fiberlab.backend.seed          # creates data/fiberlab.db
pytest                                   # 22 tests: tools, rules and full conversations

python -m fiberlab.agent.cli --offline   # chat without AWS (rule-based brain)

copy .env.example .env                   # then fill in your values
python -m fiberlab.agent.check_bedrock   # one cheap call to confirm Bedrock access
python -m fiberlab.agent.cli             # chat with the real model
```
