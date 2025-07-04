# file: projects/ocpp/data.py
"""OCPP data helpers using gw.sql for storage."""

import time
from datetime import datetime
from typing import Iterable, Optional

from gway import gw

_db_conn = None

def open_db():
    """Return connection to the OCPP database, initializing tables."""
    global _db_conn
    if _db_conn is None:
        _db_conn = gw.sql.open_connection("work/ocpp.sqlite")
        _init_db(_db_conn)
    return _db_conn

def _init_db(conn):
    gw.sql.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions(
            charger_id TEXT,
            transaction_id INTEGER,
            start_time INTEGER,
            stop_time INTEGER,
            id_tag TEXT,
            meter_start REAL,
            meter_stop REAL,
            reason TEXT,
            charger_start_ts INTEGER,
            charger_stop_ts INTEGER
        )
        """,
        connection=conn,
    )
    gw.sql.execute(
        """
        CREATE TABLE IF NOT EXISTS meter_values(
            charger_id TEXT,
            transaction_id INTEGER,
            timestamp INTEGER,
            measurand TEXT,
            value REAL,
            unit TEXT,
            context TEXT
        )
        """,
        connection=conn,
    )
    gw.sql.execute(
        """
        CREATE TABLE IF NOT EXISTS errors(
            charger_id TEXT,
            status TEXT,
            error_code TEXT,
            info TEXT,
            timestamp INTEGER
        )
        """,
        connection=conn,
    )

def record_transaction_start(
    charger_id: str,
    transaction_id: int,
    start_time: int,
    *,
    id_tag: Optional[str] = None,
    meter_start: Optional[float] = None,
    charger_timestamp: Optional[int] = None,
):
    conn = open_db()
    gw.sql.execute(
        "INSERT INTO transactions(charger_id, transaction_id, start_time, id_tag, meter_start, charger_start_ts) VALUES (?,?,?,?,?,?)",
        connection=conn,
        args=(
            charger_id,
            transaction_id,
            int(start_time),
            id_tag,
            meter_start,
            charger_timestamp,
        ),
    )

def record_transaction_stop(
    charger_id: str,
    transaction_id: int,
    stop_time: int,
    *,
    meter_stop: Optional[float] = None,
    reason: Optional[str] = None,
    charger_timestamp: Optional[int] = None,
):
    conn = open_db()
    gw.sql.execute(
        "UPDATE transactions SET stop_time=?, meter_stop=?, reason=?, charger_stop_ts=? WHERE charger_id=? AND transaction_id=?",
        connection=conn,
        args=(
            int(stop_time),
            meter_stop,
            reason,
            charger_timestamp,
            charger_id,
            transaction_id,
        ),
    )

def record_meter_value(charger_id: str, transaction_id: int, timestamp: int, measurand: str, value: float, unit: str = "", context: str = ""):
    conn = open_db()
    gw.sql.execute(
        "INSERT INTO meter_values(charger_id, transaction_id, timestamp, measurand, value, unit, context) VALUES (?,?,?,?,?,?,?)",
        connection=conn,
        args=(charger_id, transaction_id, int(timestamp), measurand, float(value), unit, context),
    )

def record_error(charger_id: str, status: str, error_code: str = "", info: str = ""):
    conn = open_db()
    ts = int(time.time())
    gw.sql.execute(
        "INSERT INTO errors(charger_id, status, error_code, info, timestamp) VALUES (?,?,?,?,?)",
        connection=conn,
        args=(charger_id, status, error_code, info, ts),
    )

def get_summary():
    """Return summary rows per charger."""
    conn = open_db()
    rows = gw.sql.execute(
        """
        SELECT t.charger_id AS cid,
               COUNT(t.transaction_id) AS sessions,
               SUM(COALESCE(t.meter_stop,0) - COALESCE(t.meter_start,0)) AS energy,
               MAX(t.stop_time) AS last_stop,
               (
                 SELECT e.error_code FROM errors e
                 WHERE e.charger_id=t.charger_id
                 ORDER BY e.timestamp DESC LIMIT 1
               ) AS last_error
        FROM transactions t
        GROUP BY t.charger_id
        """,
        connection=conn,
    )
    summary = []
    for cid, sessions, energy, last_stop, last_error in rows:
        summary.append({
            "charger_id": cid,
            "sessions": sessions,
            "energy": round((energy or 0.0) / 1000.0, 3),
            "last_stop": last_stop,
            "last_error": last_error,
        })
    return summary

def _fmt_time(ts: Optional[int]) -> str:
    if not ts:
        return "-"
    try:
        return datetime.utcfromtimestamp(int(ts)).isoformat() + "Z"
    except Exception:
        return str(ts)

def view_charger_summary(**_):
    """Simple HTML summary of charger data."""
    rows = get_summary()
    html = ["<h1>OCPP Charger Summary</h1>"]
    if not rows:
        html.append("<p>No data.</p>")
        return "\n".join(html)
    html.append("<table class='ocpp-summary'>")
    html.append("<tr><th>Charger</th><th>Sessions</th><th>Energy(kWh)</th><th>Last Stop</th><th>Last Error</th></tr>")
    for r in rows:
        html.append(
            f"<tr><td>{r['charger_id']}</td><td>{r['sessions']}</td><td>{r['energy']}</td>"
            f"<td>{_fmt_time(r['last_stop'])}</td><td>{r['last_error'] or '-'}" + "</td></tr>"
        )
    html.append("</table>")
    return "\n".join(html)
