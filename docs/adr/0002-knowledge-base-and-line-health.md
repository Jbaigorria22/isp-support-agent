# ADR-0002: Knowledge base as a decision tree, hybrid retrieval and Line Health Score

- **Status:** Accepted
- **Date:** 2026-11-10

## Context

Stage 2 guided customers with three hard-coded steps per problem. Real L1 support
does not work that way. Agents follow a **troubleshooting intranet organized as a
decision tree** (area → service → category → problem → line condition → steps), and
one number summarizes the line: if it is healthy, guide the customer at home; if it
is not, send a technician. The design below reproduces that *pattern*. All content,
names, formulas and thresholds are FiberLab's own (synthetic).

## Decision

### 1. Line Health Score (0–100)

Fiber operators and their diagnostics platforms build a per-ONT health index from
optical power, error counters (BIP/FEC) and stability. FiberLab's formula:

| Component | Weight | Full score | Zero |
|-----------|--------|------------|------|
| Optical Rx power | 35 | −8 to −24 dBm | outside −8 to −27 dBm (marginal zone fades from 35 to 15) |
| Uncorrected FEC errors (24 h) | 25 | ≤ 50 | ≥ 2000 |
| Stability (drops in 7 days) | 20 | 0 drops | 5 or more (−4 per drop) |
| Speed (today, wired, vs. plan) | 20 | ≥ 100% of plan | proportional |

**Green ≥ 75, red < 75.** Red escalates immediately with the weakest component in
the ticket. Offline ONT → `unknown` (handled by the restart flow). Exposed as the
MCP tool `get_line_health`. The decision stays in `rules.py`, not in the LLM.

### 2. Knowledge base as a tree

One Markdown file per guide in `src/fiberlab/knowledge_base/`, with front matter:

```yaml
id: wf-01
path: technical/internet/support/wifi/green
problem: wifi          # no_service | slow_internet | intermittent | wifi
health: green          # green | red | any
title: WiFi - el dispositivo no ve la red
```

Guides are in Spanish (customer language). v1 covers Technical → Internet → Support.

### 3. Hybrid retrieval: filter by the tree, then rank by similarity

Pure semantic search can return a well-matching guide from the *wrong branch*
(e.g. WiFi tips for a degraded line). So retrieval has two steps:

1. **Filter** with facts the diagnosis already has: `problem` and `health`.
2. **Rank** the remaining guides against the customer's own words.

The embedder is pluggable, like the Brain: `BedrockEmbedder` (Titan Text
Embeddings V2, cached on disk) or `LexicalEmbedder` (bag of words; free and
deterministic, used by tests and offline mode). If Bedrock embeddings are not
reachable the agent falls back to lexical search and says so. With ~10 guides an
in-memory index is enough; no vector database yet.

**Grounding:** the LLM receives one guide and may only rephrase its approved steps.
Guide IDs are stored in the state (`guides_used`) and in the ticket for audit.
A second attempt retrieves a *different* guide.

### 4. WiFi password change

New intent `wifi_password` and tools `get_wifi_info` / `change_wifi_password`.

- Consent first (interrupt): the customer is told every device will disconnect.
- The new password goes **from the customer straight to the tool**. It is never
  sent to the LLM, never written to the transcript (`[redacted]`), never echoed by
  the tool, and stored only as a hash.
- Policy enforced in the tool: 10–63 chars, letters and digits, no spaces, must not
  contain the network name. Three invalid attempts cancel the change.

## Consequences

- Guidance depends on the diagnosis *and* on what the customer said.
- A red line no longer wastes the customer's time with home checks.
- Lexical fallback matches words, not meaning; quality differences between both
  embedders are measured in Stage 4 (evals).
- Known gap: with LangSmith tracing on, the raw resume value of the password step
  can appear in trace inputs. Masking is part of Stage 6 (guardrails). Until then,
  use test passwords when tracing is enabled.
- The retrieval query is the customer's message; LLM query rewriting is deferred
  until evals show it is needed.
