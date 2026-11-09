# Project brief: ISP Support Agent

## Problem

Level-1 (L1) support at an internet service provider spends most of its time on a
small set of repetitive cases: "no service", "slow internet", "WiFi drops". Each case
follows a known diagnostic path, yet customers wait in queues, and when a case is
escalated, Level 2 often receives a vague note instead of a usable summary.

## Goal

Build an AI agent that handles L1 technical support for a **fictional ISP
("FiberLab")**: it diagnoses with real tools, guides the customer step by step,
and, when it cannot solve the case, escalates to a human with a structured ticket.

This is a learning and portfolio project focused on **agent engineering
(LangGraph, MCP, RAG, evals) with a security-first design**.

## Users

- **Customer:** a home internet subscriber reporting a technical problem (Spanish).
- **L2 technician:** receives escalated tickets with a clear summary.

## Scope (v1)

| In scope | Out of scope |
|----------|--------------|
| No service / connection down | Billing, payments, plan changes |
| Slow internet | Technician visits scheduling |
| WiFi problems (coverage, drops, password) | Voice / phone channel |
| Escalation to L2 with a ticket | Real customer data or real ISP procedures |
| Identity verification before account actions | Multi-language support |

## Data policy

All data is **synthetic or public**. No internal procedures, scripts or customer data
from any real ISP or call center. FiberLab, its customers and its knowledge base are
invented, so the repository can be public.

## Success criteria (v1)

- Intent classification ≥ 90% correct on a synthetic evaluation set (≥ 30 conversations).
- Correct escalation decision (solve vs. escalate) in ≥ 90% of evaluation cases.
- **Zero** account tool calls before identity verification.
- Prompt-injection test suite passes (the agent never reveals other customers' data,
  never skips verification, never calls tools outside its allowlist).
- Every escalation produces a ticket with: customer ID, symptom, steps tried,
  diagnostic results, suggested next action.

## Stages

| Stage | Deliverable |
|-------|-------------|
| 0 | This brief + ADR-0001 |
| 1 | Simulated ISP backend + MCP server with diagnostic tools |
| 2 | LangGraph agent running in the console |
| 3 | RAG over the FiberLab troubleshooting knowledge base |
| 4 | Evaluation set + LangSmith tracing and evals |
| 5 | Observability: OpenTelemetry + Prometheus + Grafana |
| 6 | Guardrails + security tests (prompt injection, PII) |
| 7 | Web UI + AWS deployment with Terraform |
