# ADR-0001: Agent architecture and stack

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

See [brief](../brief.md). We need an L1 support agent that diagnoses internet problems
using tools, follows a predictable flow, escalates correctly, and cannot be talked
into unsafe actions. The project is also a vehicle to learn LangGraph, MCP, RAG,
LangSmith and AWS deployment with Terraform.

## Decision

### 1. Orchestration: LangGraph (explicit state machine)

A free-form ReAct loop is hard to test and easy to manipulate. A graph with explicit
nodes makes each step observable, testable and enforceable.

```
START → verify_identity → classify_intent ─┬─→ diagnose (tool loop) → guide (RAG) → check_resolved ─┬─→ close
                                           │                                                       └─→ escalate
                                           └─→ out_of_scope ──────────────────────────────────────────→ escalate
```

| Node | Responsibility |
|------|----------------|
| `verify_identity` | Collect customer ID + verification factor; call `verify_customer`. Account tools stay locked until it succeeds |
| `classify_intent` | `no_service`, `slow_internet`, `wifi`, `out_of_scope` |
| `diagnose` | Call diagnostic tools (outage, modem status, signal, speed history) |
| `guide` | Give step-by-step instructions grounded in the knowledge base |
| `check_resolved` | Ask the customer; loop back to `guide` at most twice |
| `escalate` | Create an L2 ticket with a structured summary |
| `close` | Confirm resolution and end |

**Escalation rules** (deterministic, not left to the LLM):
- Confirmed area outage → inform the customer + open/attach to the outage ticket
- Modem offline after a remote restart
- Signal levels out of range
- Two guided attempts failed
- Customer explicitly asks for a human
- Out-of-scope request

### 2. Tools: MCP server over a simulated ISP backend

The backend is a small SQLite database with synthetic customers, modems, zones and
outages. Tools are exposed through an **MCP server** (Python MCP SDK) and loaded into
the agent with `langchain-mcp-adapters`.

| Tool | Requires verified identity | Side effect |
|------|---------------------------|-------------|
| `verify_customer` | No | None |
| `get_area_outages` | No | None |
| `get_modem_status` | Yes | None |
| `get_speed_history` | Yes | None |
| `restart_modem` | Yes | **Yes**: requires explicit customer confirmation (LangGraph interrupt) |
| `create_ticket` | Yes | **Yes** |

Identity enforcement lives **in code** (graph state + tool layer), not only in the
prompt:

- `verify_customer` returns a short-lived **HMAC-signed session token** bound to one
  customer. Account tools accept the token, never a raw `customer_id`, so the model
  cannot be talked into reading or changing another customer's account.
- Unknown IDs and wrong answers get the **same** error (no account enumeration).
- **3 failed attempts lock** verification for 15 minutes.
- `restart_modem` requires customer confirmation, enforced by a LangGraph interrupt
  (Stage 2), not by a tool argument the model could set.

### 3. Model: Amazon Bedrock

Model accessed through `langchain-aws` (`ChatBedrockConverse`), Region `us-east-1`.
Start with a small, cheap model with good tool use; the exact model is chosen in
Stage 2 by comparing eval results and cost.

### 4. Knowledge: RAG over a synthetic FiberLab knowledge base

Markdown troubleshooting guides (router restart, WiFi channel, cable checks, speed
test). Local vector store for development; managed option evaluated in Stage 7.

### 5. Observability and evaluation: LangSmith

Tracing from day one. A synthetic dataset of conversations with expected intent and
expected decision (solve / escalate) drives evals.

### 6. Interface and language

Console first, web UI later (Stage 7). Conversations in **Spanish**; code, docs and
commit messages in **English**.

## Consequences

- More upfront design than a single ReAct agent, but every decision is testable.
- Escalation and identity rules are deterministic, which reduces flexibility but
  removes the most dangerous failure modes.
- Bedrock adds a small per-use cost; a budget alert and a cheap model keep it low.
- The simulated backend means results do not prove real-world accuracy; the goal is
  correct architecture and behavior, not production readiness.

## Resolved in Stage 1

- Verification factor: customer ID + last 3 digits of a synthetic document number.
- MCP SDK pinned to `mcp<2` because `langchain-mcp-adapters` requires MCP 1.x.

## Resolved in Stage 2

- **Workflow, not a free agent.** The LLM never calls tools. It only understands
  text (extract identity, classify intent, yes/no) and writes text (guidance, ticket
  summary), always through structured outputs. The graph calls the MCP tools in code.
  A prompt injection can at worst produce odd text, never an unauthorized action.
  Tested: a verified customer asking to restart another customer's ONT changes nothing.
- **Interrupt-only waiting nodes.** LangGraph re-runs a node from the top when it
  resumes, so nodes that wait for the customer contain no side effects.
- **`Brain` interface** with two implementations: `BedrockBrain` (real model) and
  `RuleBrain` (deterministic, used by tests). End-to-end tests run the real graph and
  the real MCP server at zero cost.
- **Model:** `anthropic.claude-haiku-5-5` (cheapest current model with tool use and
  structured output), configurable with `BEDROCK_MODEL_ID`. It does not accept a
  `temperature` parameter, so none is set.

## Open questions

- Whether Haiku 5.5 is accurate enough, or a larger model is needed (Stage 4 evals).
- Vector store choice for Stage 7 deployment.
