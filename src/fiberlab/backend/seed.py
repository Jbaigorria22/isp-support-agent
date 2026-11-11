"""Schema and synthetic data for the fictional ISP "FiberLab".

Every customer, zone and outage here is invented. Each customer represents
one test scenario for the agent.
"""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE zones (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE customers (
    customer_id  TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    doc_last3    TEXT NOT NULL,          -- verification factor (synthetic)
    zone_code    TEXT NOT NULL REFERENCES zones(code),
    plan_mbps    INTEGER NOT NULL
);

CREATE TABLE modems (
    customer_id       TEXT PRIMARY KEY REFERENCES customers(customer_id),
    status            TEXT NOT NULL,     -- online | offline
    rx_power_dbm      REAL,              -- optical power received by the ONT
    uptime_hours      INTEGER NOT NULL,
    restart_fixes     INTEGER NOT NULL,  -- 1 if a remote restart brings it back
    fec_errors_24h    INTEGER NOT NULL,  -- uncorrected FEC errors in the last 24 h
    drops_7d          INTEGER NOT NULL   -- connection drops in the last 7 days
);

CREATE TABLE wifi (
    customer_id    TEXT PRIMARY KEY REFERENCES customers(customer_id),
    ssid           TEXT NOT NULL,
    password_hash  TEXT NOT NULL         -- never stored or returned in clear text
);

CREATE TABLE wifi_devices (
    customer_id  TEXT NOT NULL REFERENCES customers(customer_id),
    name         TEXT NOT NULL,
    band         TEXT NOT NULL           -- 2.4GHz | 5GHz
);

CREATE TABLE outages (
    outage_id    TEXT PRIMARY KEY,
    zone_code    TEXT NOT NULL REFERENCES zones(code),
    description  TEXT NOT NULL,
    eta_hours    INTEGER NOT NULL,
    active       INTEGER NOT NULL
);

CREATE TABLE speed_tests (
    customer_id  TEXT NOT NULL REFERENCES customers(customer_id),
    day_offset   INTEGER NOT NULL,       -- 0 = today, 1 = yesterday...
    down_mbps    REAL NOT NULL,
    up_mbps      REAL NOT NULL
);

CREATE TABLE tickets (
    ticket_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id  TEXT NOT NULL REFERENCES customers(customer_id),
    category     TEXT NOT NULL,
    priority     TEXT NOT NULL,
    summary      TEXT NOT NULL,
    steps_tried  TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE verification_failures (
    customer_id  TEXT NOT NULL,
    failed_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

ZONES = [
    ("NORTE", "Zona Norte"),
    ("CENTRO", "Centro"),
    ("SUR", "Zona Sur"),
]

# (customer_id, name, doc_last3, zone, plan_mbps)  -- scenario in comment
CUSTOMERS = [
    ("C1001", "Ana Gómez",      "482", "CENTRO", 300),  # area outage
    ("C1002", "Bruno Díaz",     "137", "NORTE",  500),  # modem hung, restart fixes it
    ("C1003", "Carla Ruiz",     "905", "SUR",    300),  # optical signal out of range
    ("C1004", "Diego Pérez",    "268", "NORTE",  1000), # slow speeds (WiFi-limited)
    ("C1005", "Elena Torres",   "551", "SUR",    300),  # everything healthy
    ("C1006", "Facundo López",  "319", "NORTE",  500),  # modem offline, restart does NOT fix
    ("C1007", "Gabriela Sosa",  "774", "NORTE",  300),  # intermittent: many drops and errors
]

# (customer_id, status, rx_power_dbm, uptime_hours, restart_fixes, fec_errors_24h, drops_7d)
MODEMS = [
    ("C1001", "offline", None,  0,   0, 0,    0),
    ("C1002", "offline", -18.5, 0,   1, 0,    1),
    ("C1003", "online",  -29.4, 72,  0, 4200, 3),
    ("C1004", "online",  -17.2, 410, 0, 0,    0),
    ("C1005", "online",  -16.8, 120, 0, 12,   0),
    ("C1006", "offline", None,  0,   0, 0,    0),
    ("C1007", "online",  -24.5, 6,   0, 1800, 9),
]

OUTAGES = [
    ("OUT-2026-0042", "CENTRO", "Fiber cut on the main trunk line", 4, 1),
    ("OUT-2026-0031", "SUR", "Scheduled maintenance (finished)", 0, 0),
]

# (customer_id, [(down, up) for the last 7 days, today first])
SPEEDS = {
    "C1002": [(480, 240)] * 7,
    "C1003": [(150, 70), (210, 95), (260, 140), (290, 145), (295, 150), (298, 150), (300, 150)],
    "C1004": [(935, 480), (941, 476), (928, 482), (939, 479), (944, 481), (931, 478), (937, 480)],  # line OK: slowness is in-home WiFi
    "C1005": [(298, 150)] * 7,
    "C1007": [(290, 148)] * 7,
}

DEVICES = ["Celular", "Notebook", "Smart TV"]


def create_database(path: str | Path) -> Path:
    """Create a fresh FiberLab database at `path` with synthetic data."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.executemany("INSERT INTO zones VALUES (?, ?)", ZONES)
        conn.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?)", CUSTOMERS)
        conn.executemany("INSERT INTO modems VALUES (?, ?, ?, ?, ?, ?, ?)", MODEMS)
        for customer_id, *_ in CUSTOMERS:
            conn.execute("INSERT INTO wifi VALUES (?, ?, ?)", (customer_id, f"FiberLab-{customer_id[1:]}", "unset"))
            conn.executemany(
                "INSERT INTO wifi_devices VALUES (?, ?, ?)",
                [(customer_id, name, "5GHz" if i else "2.4GHz") for i, name in enumerate(DEVICES)],
            )
        conn.executemany("INSERT INTO outages VALUES (?, ?, ?, ?, ?)", OUTAGES)
        for customer_id, days in SPEEDS.items():
            conn.executemany(
                "INSERT INTO speed_tests VALUES (?, ?, ?, ?)",
                [(customer_id, offset, down, up) for offset, (down, up) in enumerate(days)],
            )
    return path


if __name__ == "__main__":
    import os

    db = create_database(os.environ.get("FIBERLAB_DB", "data/fiberlab.db"))
    print(f"FiberLab database created at {db}")
