# How the agent's graph works

A walkthrough of `src/fiberlab/agent/graph.py`: the L1 support flow modelled as an
explicit state machine. See [ADR-0001](adr/0001-agent-architecture.md) for the
decision record; this document explains how it actually runs.

## The idea

Three pieces:

| Piece | What it is |
|-------|------------|
| **State** | The case file that travels through the whole flow. Every node reads it and returns what to change |
| **Node** | One step. A function that takes the state and returns an update |
| **Edge** | The arrow to the next step. Fixed, or chosen by a routing function |

## The nodes

| Node | What it does | Goes to |
|------|--------------|---------|
| `start` | Prepares the greeting and zeroes the counters | `ask` |
| `ask` | **The only node that talks to the customer.** Calls `interrupt()` and waits | routed by `after_ask` |
| `verify` | Extracts ID + 3 digits, calls `verify_customer`, stores the session token | `ask`, or `unverified` after 3 failures |
| `unverified` | Ends the conversation and points to official channels | END |
| `classify` | Asks the LLM which intent the message is | `diagnose`, `wifi_offer` or `escalate` |
| `diagnose` | Calls the diagnostic tools (outages, modem, health, speeds) and asks `rules.decide` | routed by the outcome |
| `offer_restart` | Only asks for consent: "shall I restart it?" | `ask` |
| `restart` | If the customer agreed, calls `restart_modem` | solved, `guide` or `escalate` |
| `guide` | Retrieves the matching knowledge-base guide and has the LLM phrase its steps | `ask` |
| `check_resolved` | Asks whether it worked; counts the attempt | solved, `guide` again, or `escalate` |
| `escalate` | Writes the L2 ticket summary and calls `create_ticket` | END |
| `wifi_offer` | Shows the network and warns every device will disconnect | `ask` |
| `wifi_confirm` | Reads the yes/no; asks for the new password if yes | `ask` or END |
| `wifi_apply` | Sends the password straight to the tool, never to the LLM | solved, retry, or END |

## Why it is built this way

**`ask` is the only node that talks.** Every other node prepares `prompt` and routes
here. One single place where the conversation pauses — which is why redacting the
WiFi password from the transcript took one line.

**`after_ask` is the dispatcher.** Since every customer reply arrives at the same
node, a routing function reads the state and works out where the conversation is:
no token yet → `verify`; no intent yet → `classify`; we had just offered a restart
→ `restart`; otherwise → `check_resolved`.

**`interrupt()` freezes the graph.** It saves the state and hands control back. When
the customer replies, the flow resumes exactly where it stopped.

**Escalation is decided by code, not by the LLM.** `rules.decide` is plain Python:
area outage, optical signal out of range, red health score, two failed guided
attempts, or an explicit request. The LLM contributes the intent — an ingredient —
but never the decision. That makes every path testable and immune to a customer
talking the agent out of escalating.

**Actions with side effects need consent.** `offer_restart` and `wifi_confirm` exist
only to ask. Restarting the ONT cuts the service and changing the password
disconnects every device, so the customer decides, not the agent.

**Every loop has a limit.** Verification stops after 3 failures, guided attempts
after 2, WiFi password attempts after 3. A loop with no exit is a bug waiting to
happen.

**The second guide is never the first.** `guides_used` is passed as `exclude` to the
retriever, so a failed attempt is not repeated word for word.

## The map

```
START → start → ask ──┬─ no token ──► verify ──┬─ ok ────► ask (what is the problem?)
                      │                        └─ 3 fails ► unverified → END
                      │
                      ├─ no intent ─► classify ─┬─ out of scope ──► escalate
                      │                         ├─ wants new password ► wifi_offer → ask → wifi_confirm → wifi_apply
                      │                         └─ technical ───────► diagnose
                      │                                                  │
                      │                            ┌─────────────────────┼─────────────────────┐
                      │                            ▼                     ▼                     ▼
                      │                   outage / bad signal      ONT offline            line healthy
                      │                   / red health score            │                      │
                      │                            │              offer_restart            guide (RAG)
                      │                            ▼                     ▼                      │
                      └──────────────────────► escalate              restart          max 2 attempts → escalate
```

## In one sentence

**The LLM understands and writes. The code decides and acts. The customer authorises.**
