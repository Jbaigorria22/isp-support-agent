# ISP Support Agent

An L1 technical-support agent for **FiberLab**, a fictional internet provider.
It verifies the customer, diagnoses the connection with real tools, guides the
customer step by step and, when it cannot solve the case, escalates to Level 2
with a structured ticket.

Built with **LangGraph + MCP + Amazon Bedrock**, with a **security-first** design:
identity and escalation rules are enforced in code, not only in the prompt.

`Python 3.11+` · `LangGraph` · `MCP` · `Amazon Bedrock` · `LangSmith` · `SQLite` · `pytest`

> All data is synthetic. FiberLab, its customers and its procedures are invented.
> No internal procedures or data from any real ISP or call center are used.

## Why this project

Level-1 support at an ISP spends most of its time on a few repetitive cases
("no service", "slow internet", "WiFi drops"), each with a known diagnostic path.
This agent handles those cases end to end, and hands Level 2 a usable ticket
instead of a vague note. See the [project brief](docs/brief.md).

## Key design decisions

Full reasoning in [ADR-0001](docs/adr/0001-agent-architecture.md).

- **Workflow, not a free agent.** The LLM never calls tools. It only extracts,
  classifies and writes text through structured outputs; the LangGraph graph
  decides and calls the MCP tools in code. A prompt injection can at worst
  produce odd text, never an unauthorized action.
- **Identity enforced by the tool layer.** `verify_customer` issues a short-lived
  **HMAC-signed session token** bound to one customer. Account tools accept the
  token, never a raw customer ID, so the model cannot be talked into reading or
  changing another customer's account.
- **No account enumeration.** Unknown IDs and wrong answers return the same error;
  3 failed attempts lock verification for 15 minutes.
- **Deterministic escalation rules** (`agent/rules.py`): outages, bad optical
  signal, failed restart, repeated failed guidance or out-of-scope requests
  always escalate.
- **Side effects need confirmation.** `restart_modem` waits for the customer's
  explicit "yes" through a LangGraph interrupt, not through a tool argument the
  model could set.
- **Swappable brain.** A `Brain` interface with two implementations:
  `BedrockBrain` (real model) and `RuleBrain` (deterministic, no cost). Tests run
  the real graph against the real MCP server with `RuleBrain`.

## How it works

```
Customer ⇄ LangGraph flow ──► MCP client ──stdio──► FiberLab MCP server ──► SQLite
              │
              └─► Brain (Amazon Bedrock): understands and writes text only
```

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
| `restart_modem` | Yes | Restarts the ONT (after customer confirmation) |
| `create_ticket` | Yes | Creates an L2 ticket |

## Project structure

```
src/fiberlab/
├── backend/seed.py        # synthetic customers, modems, zones and outages (SQLite)
├── tools.py               # tool logic: verification, lockout, diagnostics
├── auth.py                # HMAC-signed session tokens
├── mcp_server.py          # FiberLab MCP server (stdio)
└── agent/
    ├── graph.py           # LangGraph state machine
    ├── brain.py           # Brain interface: BedrockBrain / RuleBrain
    ├── rules.py           # deterministic escalation rules
    ├── toolbox.py         # MCP client wrapper used by the graph
    ├── knowledge.py       # troubleshooting steps
    ├── cli.py             # console chat
    └── check_bedrock.py   # one cheap call to confirm Bedrock access
tests/                     # 22 tests: tools, rules and full conversations
docs/                      # brief + architecture decision records
```

## Run

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"

python -m fiberlab.backend.seed          # creates data/fiberlab.db
pytest                                   # 22 tests: tools, rules and full conversations

python -m fiberlab.agent.cli --offline   # chat without AWS (rule-based brain)
```

To use the real model on Amazon Bedrock:

```bash
cp .env.example .env                     # Windows: copy .env.example .env — then fill in your values
python -m fiberlab.agent.check_bedrock   # one cheap call to confirm Bedrock access
python -m fiberlab.agent.cli             # chat with the real model
```

Conversations are in **Spanish** (the target customers); code and docs are in English.

## Test scenarios (synthetic customers)

| Customer | Verification | Scenario | Expected outcome |
|----------|--------------|----------|------------------|
| C1001 | 482 | Area outage in CENTRO | Inform outage + ETA |
| C1002 | 137 | ONT hung | Remote restart fixes it |
| C1003 | 905 | Optical signal out of range | Escalate |
| C1004 | 268 | Line delivers plan, slow at home | WiFi guidance |
| C1005 | 551 | Everything healthy | Guide / close |
| C1006 | 319 | ONT offline, restart fails | Escalate |

## Security and credentials

- `.env` and `data/` are git-ignored; only `.env.example` (placeholders) is committed.
- Offline mode and the full test suite need **no AWS credentials**.
- For Bedrock, use short-lived credentials (`aws sso login`) and an identity
  limited to `bedrock:InvokeModel` on the configured model, plus an AWS Budgets alert.

## Roadmap

| Stage | Deliverable | Status |
|-------|-------------|--------|
| 0 | [Brief](docs/brief.md) + [ADR-0001](docs/adr/0001-agent-architecture.md) | ✅ |
| 1 | Simulated ISP backend + MCP server | ✅ |
| 2 | LangGraph agent (console) | ✅ |
| 3 | RAG knowledge base | ⏳ |
| 4 | Evals + LangSmith | ⏳ |
| 5 | Observability: OpenTelemetry + Prometheus + Grafana | ⏳ |
| 6 | Guardrails + security tests (prompt injection, PII) | ⏳ |
| 7 | Web UI + AWS deployment (Terraform) | ⏳ |
