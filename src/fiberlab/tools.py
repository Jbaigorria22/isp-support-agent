"""Business logic behind the agent's tools.

Pure functions over the FiberLab database, so they can be unit-tested without MCP.
Rules enforced here (in code, not in the prompt):
  - Account tools require a valid session token, bound to one customer.
  - Verification answers are generic, so callers cannot discover which IDs exist.
  - After MAX_FAILED_ATTEMPTS wrong answers, verification is locked for a while.
"""

import hashlib
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from fiberlab.auth import AuthError, issue_token, verify_token

# Healthy optical receive power for a GPON ONT, in dBm.
RX_POWER_MIN_DBM = -27.0
RX_POWER_MAX_DBM = -8.0

# Line is "OK" if today's wired speed reaches 80% of the plan.
LINE_OK_RATIO = 0.8
# A change of 15% or more vs. the previous days counts as a trend.
TREND_THRESHOLD = 0.15

# Line Health Score (ADR-0002): 0-100, green from this value up.
HEALTH_GREEN_MIN = 75
HEALTH_WEIGHTS = {"signal": 35, "errors": 25, "stability": 20, "speed": 20}

MAX_FAILED_ATTEMPTS = 3
LOCKOUT_MINUTES = 15

VALID_CATEGORIES = {"no_service", "slow_internet", "wifi", "intermittent", "out_of_scope", "outage"}
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
    if not tests:
        return {"ok": True, "plan_mbps": plan, "tests": [], "line_delivers_plan": None, "trend": "unknown"}

    latest_down = tests[0]["down_mbps"]  # day_offset 0 = today
    avg_down = round(sum(t["down_mbps"] for t in tests) / len(tests), 1)
    return {
        "ok": True,
        "plan_mbps": plan,
        "measured_at": "ONT (wired, before the customer's WiFi)",
        "tests": tests,
        "latest_down_mbps": latest_down,
        "avg_down_mbps": avg_down,
        # Decide on TODAY's measurement: an average hides a line that is degrading.
        "line_delivers_plan": latest_down >= LINE_OK_RATIO * plan,
        "trend": _trend(tests),
    }


def _trend(tests: list[dict]) -> str:
    """Compare today's speed with the average of the previous days."""
    if len(tests) < 2:
        return "unknown"
    previous = [t["down_mbps"] for t in tests[1:]]
    baseline = sum(previous) / len(previous)
    change = (tests[0]["down_mbps"] - baseline) / baseline
    if change <= -TREND_THRESHOLD:
        return "degrading"
    if change >= TREND_THRESHOLD:
        return "improving"
    return "stable"


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


# --------------------------------------------------------------------------- #
# Line Health Score (FiberLab's own formula, see ADR-0002)
# --------------------------------------------------------------------------- #

def _health_components(rx: float, fec_errors: int, drops: int, speed_ratio: float | None) -> dict:
    """Score each component from 0 to its weight. Higher is healthier."""
    w = HEALTH_WEIGHTS

    # Optical signal: full points in the comfortable band, fading to 0 at the range limit.
    if rx > RX_POWER_MAX_DBM or rx < RX_POWER_MIN_DBM:
        signal = 0.0
    elif rx >= -24.0:
        signal = float(w["signal"])
    else:  # marginal zone between -24 and -27 dBm
        signal = 15 + (w["signal"] - 15) * (rx - RX_POWER_MIN_DBM) / (-24.0 - RX_POWER_MIN_DBM)

    # Uncorrected FEC errors in 24 h: up to 50 is normal, 2000 or more scores 0.
    errors = w["errors"] * max(0.0, min(1.0, (2000 - fec_errors) / (2000 - 50)))

    # Stability: each connection drop in 7 days costs 4 points.
    stability = max(0.0, w["stability"] - 4.0 * drops)

    # Speed: today's wired speed vs. the plan. Neutral (half) when there is no test.
    speed = w["speed"] * (min(1.0, speed_ratio) if speed_ratio is not None else 0.5)

    return {k: round(v, 1) for k, v in
            {"signal": signal, "errors": errors, "stability": stability, "speed": speed}.items()}


def get_line_health(session_token: str) -> dict:
    """0-100 score that summarizes the line: green = home checks, red = technician."""
    try:
        customer_id = _customer_from_token(session_token)
    except AuthError as exc:
        return _error(str(exc))

    with closing(_connect()) as conn:
        modem = conn.execute(
            "SELECT status, rx_power_dbm, fec_errors_24h, drops_7d FROM modems WHERE customer_id = ?",
            (customer_id,),
        ).fetchone()
        plan = conn.execute("SELECT plan_mbps FROM customers WHERE customer_id = ?", (customer_id,)).fetchone()[0]
        latest = conn.execute(
            "SELECT down_mbps FROM speed_tests WHERE customer_id = ? AND day_offset = 0", (customer_id,)
        ).fetchone()

    if modem["status"] != "online" or modem["rx_power_dbm"] is None:
        return {"ok": True, "status": "unknown", "score": None, "reason": "ONT offline: the line cannot be measured"}

    components = _health_components(
        modem["rx_power_dbm"], modem["fec_errors_24h"], modem["drops_7d"], latest[0] / plan if latest else None
    )
    score = round(sum(components.values()))
    weakest = min(components, key=lambda k: components[k] / HEALTH_WEIGHTS[k])
    return {
        "ok": True,
        "score": score,
        "status": "green" if score >= HEALTH_GREEN_MIN else "red",
        "green_from": HEALTH_GREEN_MIN,
        "components": components,
        "max_per_component": HEALTH_WEIGHTS,
        "weakest": weakest,
    }


# --------------------------------------------------------------------------- #
# WiFi tools
# --------------------------------------------------------------------------- #

def get_wifi_info(session_token: str) -> dict:
    """Network name and connected devices. Never returns the password."""
    try:
        customer_id = _customer_from_token(session_token)
    except AuthError as exc:
        return _error(str(exc))

    with closing(_connect()) as conn:
        ssid = conn.execute("SELECT ssid FROM wifi WHERE customer_id = ?", (customer_id,)).fetchone()[0]
        devices = conn.execute(
            "SELECT name, band FROM wifi_devices WHERE customer_id = ?", (customer_id,)
        ).fetchall()
    return {"ok": True, "ssid": ssid, "devices": [dict(d) for d in devices], "device_count": len(devices)}


def _password_problem(password: str, ssid: str) -> str | None:
    if len(password) < 10:
        return "too_short"
    if len(password) > 63:
        return "too_long"
    if any(c.isspace() for c in password):
        return "has_spaces"
    if not (any(c.isalpha() for c in password) and any(c.isdigit() for c in password)):
        return "needs_letter_and_digit"
    if ssid.lower() in password.lower():
        return "contains_network_name"
    return None


def change_wifi_password(session_token: str, new_password: str) -> dict:
    """Change the WiFi password. Side effect: disconnects every device.

    The password is validated, applied and stored only as a hash. It is never
    returned, logged or included in error messages.
    """
    try:
        customer_id = _customer_from_token(session_token)
    except AuthError as exc:
        return _error(str(exc))

    with closing(_connect()) as conn:
        ssid = conn.execute("SELECT ssid FROM wifi WHERE customer_id = ?", (customer_id,)).fetchone()[0]
        problem = _password_problem(new_password, ssid)
        if problem:
            return {"ok": False, "error": "password rejected", "code": problem}

        digest = hashlib.sha256(f"{customer_id}:{new_password}".encode()).hexdigest()
        conn.execute("UPDATE wifi SET password_hash = ? WHERE customer_id = ?", (digest, customer_id))
        disconnected = conn.execute(
            "SELECT COUNT(*) FROM wifi_devices WHERE customer_id = ?", (customer_id,)
        ).fetchone()[0]
        conn.commit()

    return {"ok": True, "ssid": ssid, "devices_disconnected": disconnected}
