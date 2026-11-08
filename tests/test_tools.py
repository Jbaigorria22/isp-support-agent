"""Scenario and security tests for FiberLab tools."""

import time

from fiberlab import tools
from fiberlab.auth import issue_token


def login(customer_id: str, doc_last3: str) -> str:
    result = tools.verify_customer(customer_id, doc_last3)
    assert result["ok"], result
    return result["session_token"]


# --------------------------------------------------------------------------- #
# Verification and security rules
# --------------------------------------------------------------------------- #

def test_verify_ok_returns_token_and_no_sensitive_data():
    result = tools.verify_customer("c1002", "137")  # case-insensitive ID
    assert result["ok"]
    assert "session_token" in result
    assert "doc_last3" not in result


def test_unknown_id_and_wrong_digits_get_the_same_answer():
    unknown = tools.verify_customer("C9999", "000")
    wrong = tools.verify_customer("C1002", "000")
    assert unknown == wrong  # no account enumeration


def test_lockout_after_three_failures():
    for _ in range(3):
        assert not tools.verify_customer("C1002", "000")["ok"]
    locked = tools.verify_customer("C1002", "137")  # even the right answer
    assert not locked["ok"]
    assert "too many" in locked["error"]


def test_account_tools_reject_missing_or_forged_tokens():
    for bad in ["", "not-a-token", "QzEwMDI6OTk5OTk5OTk5OTpmYWtl"]:
        assert not tools.get_modem_status(bad)["ok"]
        assert not tools.restart_modem(bad)["ok"]
        assert not tools.create_ticket(bad, "no_service", "high", "x" * 30, "none")["ok"]


def test_expired_token_is_rejected():
    old = issue_token("C1002", now=time.time() - 3600)
    result = tools.get_modem_status(old)
    assert not result["ok"]
    assert "expired" in result["error"]


def test_token_is_bound_to_one_customer():
    token = login("C1005", "551")
    status = tools.get_modem_status(token)
    assert status["ok"] and status["status"] == "online"  # C1005's modem, not anyone else's


# --------------------------------------------------------------------------- #
# Scenarios
# --------------------------------------------------------------------------- #

def test_c1001_area_outage():
    outages = tools.get_area_outages("centro")
    assert outages["active_outages"][0]["outage_id"] == "OUT-2026-0042"
    assert tools.get_area_outages("SUR")["active_outages"] == []  # finished maintenance not listed


def test_c1002_restart_fixes_hung_modem():
    token = login("C1002", "137")
    assert tools.get_modem_status(token)["status"] == "offline"
    result = tools.restart_modem(token)
    assert result["status_after_restart"] == "online"
    assert tools.get_modem_status(token)["status"] == "online"


def test_c1003_signal_out_of_range():
    token = login("C1003", "905")
    status = tools.get_modem_status(token)
    assert status["status"] == "online"
    assert status["signal_in_range"] is False


def test_c1004_line_delivers_plan_so_problem_is_wifi():
    token = login("C1004", "268")
    history = tools.get_speed_history(token)
    assert history["line_delivers_plan"] is True


def test_c1006_restart_does_not_fix():
    token = login("C1006", "319")
    assert tools.restart_modem(token)["status_after_restart"] == "offline"


def test_create_ticket_validates_input():
    token = login("C1006", "319")
    assert not tools.create_ticket(token, "billing", "high", "x" * 30, "")["ok"]
    assert not tools.create_ticket(token, "no_service", "urgent", "x" * 30, "")["ok"]
    assert not tools.create_ticket(token, "no_service", "high", "too short", "")["ok"]

    ticket = tools.create_ticket(
        token,
        "no_service",
        "high",
        "ONT offline, remote restart did not recover it, no area outage. Suggest technician visit.",
        "Remote restart",
    )
    assert ticket["ok"]
    assert ticket["ticket_id"].startswith("TCK-")
