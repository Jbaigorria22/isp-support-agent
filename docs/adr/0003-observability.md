# ADR-0003: Observability — Prometheus metrics and Grafana dashboards

- **Status:** accepted
- **Date:** 2026-11-19
- **Supersedes:** none

## Context

Stages 3 and 4 gave the agent two safety nets:

| Net | Question it answers | When it runs |
|---|---|---|
| 52 unit tests | Does the code do what it says? | Before a commit |
| 30-case intent eval | Does the agent *decide* well? | Before a commit |

Neither answers the question an on-call engineer asks: **how is the system
behaving right now, in aggregate?** A test suite is green while production
burns money on a retry loop; an eval scores 100% while p95 latency is twelve
seconds.

This is the third pillar of observability (metrics), next to traces (already
covered by LangSmith) and logs.

## Decision

Instrument the agent with **Prometheus metrics**, scraped into **Prometheus**
and displayed in **Grafana**, both running locally via Docker Compose.

### What we measure

Nine metrics across four categories. Each one has to answer a question
somebody would actually ask.

| Metric | Type | Labels | Question |
|---|---|---|---|
| `fiberlab_conversations_total` | Counter | `outcome` | How many conversations does L1 close without L2? |
| `fiberlab_conversation_duration_seconds` | Histogram | — | How long does a customer spend with the agent? |
| `fiberlab_intents_total` | Counter | `intent` | What do customers actually ask about? |
| `fiberlab_llm_calls_total` | Counter | `operation`, `status` | Which LLM operations run, and do they fail? |
| `fiberlab_llm_duration_seconds` | Histogram | `operation` | Where is the latency? |
| `fiberlab_llm_tokens_total` | Counter | `operation`, `kind` | Which part of the agent costs money? |
| `fiberlab_tool_calls_total` | Counter | `tool`, `status` | Which MCP tools carry the load? |
| `fiberlab_tool_duration_seconds` | Histogram | `tool` | Is the slowness the model or the backend? |
| `fiberlab_security_events_total` | Counter | `event` | Is somebody probing the verification step? |

### Design decisions and their reasons

**1. Record tokens, not dollars.**
Model prices change; a `cost_usd` counter would silently rewrite history every
time Bedrock adjusts its price list. We store the raw fact (tokens) and let
Grafana multiply by the current price in the panel. General principle: store
raw facts, compute derived values at the presentation layer.

**2. `prometheus_client` rather than OpenTelemetry.**
OpenTelemetry is the vendor-neutral standard, but its metrics path to
Prometheus needs an extra component (the OTel Collector). For a project whose
explicit goal is that every line can be explained, three more moving parts buy
nothing: the concepts that matter (counter / histogram / gauge, labels,
cardinality) are identical in both. OpenTelemetry's real advantage is
distributed tracing, and tracing is already covered by LangSmith. Revisit in
Stage 7, when a deployed web service makes a Collector worth its weight.

**3. Pull model, endpoint inside the agent process.**
The agent exposes `/metrics` on port 8000; Prometheus scrapes it every 15s.
Rejected alternatives:
- *Pushgateway*: the usual answer for short-lived jobs, but it holds state
  outside the process and turns one component into two. Not worth it for a
  demo CLI that becomes a long-lived service in Stage 7.
- *Writing metrics to a file*: no standard scrape path, no histograms.

**Known limitation:** the CLI is a short-lived process. Counters reset on every
run and Prometheus reports the target as down between runs. This is inherent to
pull-based metrics over short-lived processes, not a bug. Stage 7 removes it by
turning the agent into a long-running web service.

**4. LLM metrics via a LangChain callback handler, not per-method code.**
`BedrockBrain` has five methods that call the model, and `with_structured_output`
hides the raw response (and therefore the token usage) behind a Pydantic object.
Instrumenting each method would mean five copies of the same timing code and a
change to the structured-output call signature. Instead one
`BaseCallbackHandler` subclass receives `on_llm_start` / `on_llm_end` /
`on_llm_error` for every call the framework makes, including token usage.
This is the same mechanism LangSmith uses. One class, five methods covered,
and new LLM calls are instrumented for free.

**5. Instrument the MCP client, not the MCP server.**
The MCP server runs as a separate OS process with its own metric registry;
exposing a second scrape target would double the infrastructure. Measuring in
`Toolbox.call` is also more honest: it includes the JSON-RPC round trip, which
is what the customer waits for.

**6. No PII and no secrets in labels, ever.**
Every label value comes from a fixed, small set defined in code
(`intent`, `tool`, `outcome`, `operation`, `event`). No `customer_id`, no free
text, no passwords. Two reasons, and both matter:
- Privacy: metrics are usually the least protected surface in a system.
- Cardinality: one unbounded label (10,000 customer IDs × 9 buckets) is how a
  Prometheus server runs out of memory.

**7. The metrics server starts explicitly, never on import.**
`metrics.py` only declares metrics. `start_metrics_server()` is called from the
CLI. If importing the module bound a port, the 52 tests would fight over port
8000 and `pytest` would fail in parallel.

## Consequences

**Good**
- Latency, cost and resolution rate become visible instead of anecdotal.
- Security counters surface probing attempts that no test would catch.
- The Grafana dashboard is a portfolio artifact a hiring manager can read in
  ten seconds.

**Bad / accepted**
- Counters reset between CLI runs (see limitation above).
- `prometheus-client` and a Docker Compose stack are new dependencies.
- The callback handler couples us to LangChain's callback contract; if that
  contract changes, token accounting breaks silently. Mitigated by a test that
  asserts the handler records a call.

## Alternatives considered

| Alternative | Why not |
|---|---|
| LangSmith only | Excellent per-trace detail, no aggregate dashboards, no custom business metrics, and no self-hosted story |
| CloudWatch metrics | The natural choice once deployed on AWS, but costs money per metric and cannot be shown offline in a portfolio demo |
| OpenTelemetry + Collector | Right answer for a distributed system; three components to explain for a single-process agent |
| Pushgateway | Solves the short-lived-process problem, adds a stateful component we remove again in Stage 7 |
