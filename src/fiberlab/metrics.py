"""Prometheus metrics for the FiberLab agent (ADR-0003).

This module only DECLARES metrics. Nothing here binds a port: the HTTP
endpoint is started explicitly by start_metrics_server(), which the CLI
calls. If importing this module opened a socket, the test suite would
fight over port 8000.

Label rule (ADR-0003, decision 6): every label value comes from a small,
fixed set defined in code. No customer IDs, no free text, no secrets.
An unbounded label is how a Prometheus server runs out of memory.
"""

from prometheus_client import Counter, Histogram, start_http_server

METRICS_PORT = 8000

# --------------------------------------------------------------------------- #
# Business: did the agent do its job?
# --------------------------------------------------------------------------- #

conversations = Counter(
    "fiberlab_conversations_total",
    "Conversations that reached a terminal state.",
    ["outcome"],  # solved | escalated | outage | unverified | cancelled
)

conversation_duration = Histogram(
    "fiberlab_conversation_duration_seconds",
    "Wall-clock time from greeting to terminal state.",
    buckets=(10, 30, 60, 120, 300, 600),
)

intents = Counter(
    "fiberlab_intents_total",
    "Problems as classified by the agent.",
    ["intent"],  # no_service | slow_internet | intermittent | wifi | wifi_password | out_of_scope
)

# --------------------------------------------------------------------------- #
# LLM: latency and cost
# --------------------------------------------------------------------------- #

llm_calls = Counter(
    "fiberlab_llm_calls_total",
    "Calls to the language model.",
    ["operation", "status"],  # operation: extract|classify|affirmative|guidance|ticket ; status: ok|error
)

llm_duration = Histogram(
    "fiberlab_llm_duration_seconds",
    "Time spent waiting for the language model.",
    ["operation"],
    buckets=(0.25, 0.5, 1, 2, 3, 5, 8, 15),
)

llm_tokens = Counter(
    "fiberlab_llm_tokens_total",
    "Tokens billed by the model. Price is applied in Grafana, not here (ADR-0003).",
    ["operation", "kind"],  # kind: input | output
)

# --------------------------------------------------------------------------- #
# Tools: the MCP round trip
# --------------------------------------------------------------------------- #

tool_calls = Counter(
    "fiberlab_tool_calls_total",
    "MCP tool invocations, measured on the client side (includes the JSON-RPC round trip).",
    ["tool", "status"],  # status: ok | error
)

tool_duration = Histogram(
    "fiberlab_tool_duration_seconds",
    "Time spent in an MCP tool call.",
    ["tool"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1),
)

# --------------------------------------------------------------------------- #
# Security: the differentiator
# --------------------------------------------------------------------------- #

security_events = Counter(
    "fiberlab_security_events_total",
    "Security-relevant events during a conversation.",
    ["event"],  # verification_failed | verification_exhausted | weak_wifi_password | wifi_attempts_exhausted
)


def start_metrics_server(port: int = METRICS_PORT) -> None:
    """Expose /metrics over HTTP so Prometheus can scrape this process."""
    start_http_server(port)
