"""Business logic behind the agent's tools.

Pure functions over the FiberLab database, so they can be unit-tested without MCP.
Rules enforced here (in code, not in the prompt):
  - Account tools require a valid session token, bound to one customer.
  - Verification answers are generic, so callers cannot discover which IDs exist.
  - After MAX_FAILED_ATTEMPTS wrong answers, verification is locked for a while.
"""

import os
import sqlite3
from contextlib import closing
from pathlib import Path

from fiberlab.auth import AuthError, issue_token, verify_token

# Healthy optical receive power for a GPON ONT, in dBm.
RX_POWER_MIN_DBM = -27.0
RX_POWER_MAX_DBM = -8.0

MAX_FAILED_ATTEMPTS = 3
LOCKOUT_MINUTES = 15

VALID_CATEGORIES = {"no_service", "slow_internet", "wifi", "out_of_scope", "outage"}
VALID_PRIORITIES = {"low", "medium", "high"}


def db_path() -> Path:
    return Path(os.environ.get("FIBERLAB_DB", "data/fiberlab.db"))


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _error(message: str) -> dict:
    return {"ok": False, "error": message}


def _customer_from_token(session_token: str) -> str:
    return verify_token(session_token)


# --------------------------------------------------------------------------- #
# Public tools (no verification needed)
# --------------------------------------------------------------------------- #

def verify_customer(customer_id: str, doc_last3: str) -> dict:
    """Verify a customer and return a session token for account tools."""
    customer_id = customer_id.strip().upper()
    generic_failure = _error("verification failed: check the customer ID and the last 3 digits")

    with closing(_connect()) as conn:
        recent_failures = conn.execute(
            "SELECT COUNT(*) FROM verification_failures "
            "WHERE customer_id = ? AND failed_at > datetime('now', ?)",
            (customer_id, f"-{LOCKOUT_MINUTES} minutes"),
        ).fetchone()[0]
        if recent_failures >= MAX_FAILED_ATTEMPTS:
            return _error(f"too many failed attempts, try again in {LOCKOUT_MINUTES} minutes")

        row = conn.execute(
            "SELECT customer_id, name, zone_code, plan_mbps, doc_last3 FROM customers WHERE customer_id = ?",
            (customer_id,),
        ).fetchone()

        if row is None or row["doc_last3"] != doc_last3.strip():
            conn.execute("INSERT INTO verification_failures (customer_id) VALUES (?)", (customer_id,))
            conn.commit()
            return generic_failure

    return {
        "ok": True,
        "session_token": issue_token(row["customer_id"]),
        "first_name": row["name"].split()[0],
        "zone": row["zone_code"],
        "plan_mbps": row["plan_mbps"],
    }


def get_area_outages(zone: str) -> dict:
    """Active outages in a zone (public information)."""
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT outage_id, description, eta_hours FROM outages WHERE zone_code = ? AND active = 1",
            (zone.strip().upper(),),
        ).fetchall()
    return {"ok": True, "zone": zone.upper(), "active_outages": [dict(r) for r in rows]}


# --------------------------------------------------------------------------- #
# Account tools (require a session token)
# --------------------------------------------------------------------------- #

def get_modem_status(session_token: str) -> dict:
    try:
        customer_id = _customer_from_token(session_token)
    except AuthError as exc:
        return _error(str(exc))

    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT status, rx_power_dbm, uptime_hours FROM modems WHERE customer_id = ?",
            (customer_id,),
        ).fetchone()

    rx = row["rx_power_dbm"]
    signal_in_range = rx is not None and RX_POWER_MIN_DBM <= rx <= RX_POWER_MAX_DBM
    return {
        "ok": True,
        "status": row["status"],
        "rx_power_dbm": rx,
        "signal_in_range": signal_in_range,
        "healthy_range_dbm": [RX_POWER_MIN_DBM, RX_POWER_MAX_DBM],
        "uptime_hours": row["uptime_hours"],
    }


def get_speed_history(session_token: str, days: int = 7) -> dict:
    try:
        customer_id = _customer_from_token(session_token)
    except AuthError as exc:
        return _error(str(exc))

    days = max(1, min(int(days), 7))
    with closing(_connect()) as conn:
        plan = conn.execute(
            "SELECT plan_mbps FROM customers WHERE customer_id = ?", (customer_id,)
        ).fetchone()["plan_mbps"]
        rows = conn.execute(
            "SELECT day_offset, down_mbps, up_mbps FROM speed_tests "
            "WHERE customer_id = ? AND day_offset < ? ORDER BY day_offset",
            (customer_id, days),
        ).fetchall()

    tests = [dict(r) for r in rows]
    avg_down = round(sum(t["down_mbps"] for t in tests) / len(tests), 1) if tests else None
    return {
        "ok": True,
        "plan_mbps": plan,
        "measured_at": "ONT (wired, before the customer's WiFi)",
        "tests": tests,
        "avg_down_mbps": avg_down,
        "line_delivers_plan": avg_down is not None and avg_down >= 0.8 * plan,
    }


def restart_modem(session_token: str) -> dict:
    """Remote restart. Side effect: the graph must get customer confirmation first."""
    try:
        customer_id = _customer_from_token(session_token)
    except AuthError as exc:
        return _error(str(exc))

    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT status, restart_fixes FROM modems WHERE customer_id = ?", (customer_id,)
        ).fetchone()
        if row["restart_fixes"]:
            conn.execute(
                "UPDATE modems SET status = 'online', uptime_hours = 0, restart_fixes = 0 WHERE customer_id = ?",
                (customer_id,),
            )
            conn.commit()
            new_status = "online"
        else:
            new_status = row["status"]

    return {"ok": True, "previous_status": row["status"], "status_after_restart": new_status}


def create_ticket(session_token: str, category: str, priority: str, summary: str, steps_tried: str) -> dict:
    """Escalate to Level 2 with a structured summary."""
    try:
        customer_id = _customer_from_token(session_token)
    except AuthError as exc:
        return _error(str(exc))

    if category not in VALID_CATEGORIES:
        return _error(f"category must be one of {sorted(VALID_CATEGORIES)}")
    if priority not in VALID_PRIORITIES:
        return _error(f"priority must be one of {sorted(VALID_PRIORITIES)}")
    if len(summary.strip()) < 20:
        return _error("summary too short: describe symptom, diagnostics and suggested next action")

    with closing(_connect()) as conn:
        cursor = conn.execute(
            "INSERT INTO tickets (customer_id, category, priority, summary, steps_tried) VALUES (?, ?, ?, ?, ?)",
            (customer_id, category, priority, summary.strip(), steps_tried.strip()),
        )
        conn.commit()
        ticket_id = cursor.lastrowid

    return {"ok": True, "ticket_id": f"TCK-{ticket_id:05d}", "category": category, "priority": priority}
