"""Deterministic decision rules (ADR-0001: escalation is decided by code, not the LLM).

Pure functions over the diagnostic facts, so every rule is unit-testable.
"""

from dataclasses import dataclass

# Outcomes the graph can route to.
OUTAGE = "outage"
OFFER_RESTART = "offer_restart"
GUIDE = "guide"
ESCALATE = "escalate"

MAX_GUIDE_ATTEMPTS = 2


@dataclass(frozen=True)
class Decision:
    outcome: str
    reason: str


def decide(intent: str, facts: dict, already_restarted: bool = False) -> Decision:
    """Pick the next step from the intent and the diagnostic facts."""
    if intent == "out_of_scope":
        return Decision(ESCALATE, "request is outside L1 technical support scope")

    if facts.get("outages"):
        return Decision(OUTAGE, "active outage in the customer's zone")

    modem = facts.get("modem", {})
    if modem.get("status") == "offline":
        if already_restarted:
            return Decision(ESCALATE, "ONT still offline after a remote restart")
        return Decision(OFFER_RESTART, "ONT offline, a remote restart may recover it")

    if modem and not modem.get("signal_in_range", True):
        return Decision(ESCALATE, f"optical signal out of range ({modem.get('rx_power_dbm')} dBm)")

    if intent == "slow_internet":
        speeds = facts.get("speeds", {})
        if speeds.get("line_delivers_plan") and speeds.get("trend") != "degrading":
            return Decision(GUIDE, "line delivers the plan speed: the bottleneck is inside the home (WiFi/devices)")
        if speeds.get("trend") == "degrading":
            return Decision(ESCALATE, f"line speed degrading: {speeds.get('latest_down_mbps')} Mbps today "
                                      f"vs. plan {speeds.get('plan_mbps')} Mbps")
        return Decision(ESCALATE, "line does not deliver the plan speed")

    return Decision(GUIDE, "no fault detected on the line: guide the customer through home checks")


def after_failed_guidance(attempts: int) -> Decision | None:
    """Escalate after MAX_GUIDE_ATTEMPTS unsuccessful guided attempts."""
    if attempts >= MAX_GUIDE_ATTEMPTS:
        return Decision(ESCALATE, f"{attempts} guided attempts did not solve the problem")
    return None
