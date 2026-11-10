"""Unit tests for the deterministic decision rules (no LLM, no MCP, no database)."""

from fiberlab.agent import rules

HEALTHY_MODEM = {"status": "online", "signal_in_range": True, "rx_power_dbm": -17.0}


def speeds(delivers: bool, trend: str = "stable") -> dict:
    return {"line_delivers_plan": delivers, "trend": trend, "latest_down_mbps": 150, "plan_mbps": 300}


def test_outage_wins_over_everything():
    facts = {"outages": [{"outage_id": "X"}], "modem": {"status": "offline"}}
    assert rules.decide("no_service", facts).outcome == rules.OUTAGE


def test_offline_modem_gets_a_restart_offer_once():
    facts = {"outages": [], "modem": {"status": "offline"}}
    assert rules.decide("no_service", facts).outcome == rules.OFFER_RESTART
    assert rules.decide("no_service", facts, already_restarted=True).outcome == rules.ESCALATE


def test_bad_signal_escalates():
    facts = {"outages": [], "modem": {**HEALTHY_MODEM, "signal_in_range": False}}
    assert rules.decide("wifi", facts).outcome == rules.ESCALATE


def test_slow_with_healthy_line_is_a_wifi_problem():
    facts = {"outages": [], "modem": HEALTHY_MODEM, "speeds": speeds(True)}
    assert rules.decide("slow_internet", facts).outcome == rules.GUIDE


def test_slow_with_degrading_line_escalates_even_if_today_passes():
    facts = {"outages": [], "modem": HEALTHY_MODEM, "speeds": speeds(True, trend="degrading")}
    decision = rules.decide("slow_internet", facts)
    assert decision.outcome == rules.ESCALATE
    assert "degrading" in decision.reason


def test_slow_with_line_below_plan_escalates():
    facts = {"outages": [], "modem": HEALTHY_MODEM, "speeds": speeds(False)}
    assert rules.decide("slow_internet", facts).outcome == rules.ESCALATE


def test_out_of_scope_escalates():
    assert rules.decide("out_of_scope", {}).outcome == rules.ESCALATE


def test_two_failed_guidance_attempts_escalate():
    assert rules.after_failed_guidance(1) is None
    assert rules.after_failed_guidance(2).outcome == rules.ESCALATE
