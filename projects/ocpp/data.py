# file: projects/ocpp/data.py
"""OCPP data helpers using gw.sql for storage."""

import time
import json
from datetime import datetime
from typing import Iterable, Optional, Sequence
from gway import gw

DBFILE = "work/ocpp.db"
ENGINE = "duckdb"

TRANSACTIONS = """transactions(
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
 )"""

METER_VALUES = """meter_values(
    charger_id TEXT,
    transaction_id INTEGER,
    timestamp INTEGER,
    measurand TEXT,
    value REAL,
    unit TEXT,
    context TEXT
 )"""

ERRORS = """errors(
    charger_id TEXT,
    status TEXT,
    error_code TEXT,
    info TEXT,
    timestamp INTEGER
 )"""

CONNECTIONS = """connections(
    charger_id TEXT PRIMARY KEY,
    connected INTEGER,
    last_heartbeat TEXT,
    status TEXT,
    error_code TEXT,
    info TEXT,
    last_msg INTEGER
 )"""

# Database connections are opened lazily via ``gw.sql.model`` when needed.  The
# helper ensures tables exist and are migrated to include any new columns.

def record_transaction_start(
    charger_id: str,
    transaction_id: int,
    start_time: int,
    *,
    id_tag: Optional[str] = None,
    meter_start: Optional[float] = None,
    charger_timestamp: Optional[int] = None,
):
    gw.sql.model(TRANSACTIONS, project="ocpp").create(
        charger_id=charger_id,
        transaction_id=transaction_id,
        start_time=int(start_time),
        id_tag=id_tag,
        meter_start=meter_start,
        charger_start_ts=charger_timestamp,
    )
    record_last_msg(charger_id, start_time)

def record_transaction_stop(
    charger_id: str,
    transaction_id: int,
    stop_time: int,
    *,
    meter_stop: Optional[float] = None,
    reason: Optional[str] = None,
    charger_timestamp: Optional[int] = None,
):
    conn = gw.sql.open_db(project="ocpp")
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
    record_last_msg(charger_id, stop_time)

def record_meter_value(charger_id: str, transaction_id: int, timestamp: int, measurand: str, value: float, unit: str = "", context: str = ""):
    gw.sql.model(METER_VALUES, project="ocpp").create(
        charger_id=charger_id,
        transaction_id=transaction_id,
        timestamp=int(timestamp),
        measurand=measurand,
        value=float(value),
        unit=unit,
        context=context,
    )
    record_last_msg(charger_id, timestamp)

def record_error(charger_id: str, status: str, error_code: str = "", info: str = ""):
    ts = int(time.time())
    gw.sql.model(ERRORS, project="ocpp").create(
        charger_id=charger_id,
        status=status,
        error_code=error_code,
        info=info,
        timestamp=ts,
    )
    record_last_msg(charger_id, ts)

def set_connection_status(charger_id: str, connected: bool):
    """Mark charger connection as active or inactive."""
    gw.sql.model(CONNECTIONS, project="ocpp").delete(charger_id, id_col="charger_id")
    gw.sql.model(CONNECTIONS, project="ocpp").create(
        charger_id=charger_id, connected=1 if connected else 0
    )

def record_heartbeat(charger_id: str, timestamp: str):
    gw.sql.model(CONNECTIONS, project="ocpp").update(
        charger_id, id_col="charger_id", last_heartbeat=timestamp
    )
    record_last_msg(charger_id)

def update_status(charger_id: str, status: str = None, error_code: str = None, info: str = None):
    gw.sql.model(CONNECTIONS, project="ocpp").update(
        charger_id,
        id_col="charger_id",
        status=status,
        error_code=error_code,
        info=info,
    )

def clear_status(charger_id: str):
    gw.sql.model(CONNECTIONS, project="ocpp").update(
        charger_id,
        id_col="charger_id",
        status=None,
        error_code=None,
        info=None,
    )

def record_last_msg(charger_id: str, timestamp: int | None = None):
    """Update the last_msg timestamp for a charger."""
    gw.sql.model(CONNECTIONS, project="ocpp")  # ensure table exists
    conn = gw.sql.open_db(project="ocpp")
    ts = int(timestamp or time.time())
    gw.sql.execute(
        "UPDATE connections SET last_msg=? WHERE charger_id=?",
        connection=conn,
        args=(ts, charger_id),
    )

def get_connection(charger_id: str):
    gw.sql.model(CONNECTIONS, project="ocpp")  # ensure table exists
    conn = gw.sql.open_db(project="ocpp")
    rows = gw.sql.execute(
        "SELECT connected, last_heartbeat, status, error_code, info, last_msg FROM connections WHERE charger_id=?",
        connection=conn,
        args=(charger_id,),
    )
    if rows:
        c, hb, st, ec, info, lm = rows[0]
        return {
            "connected": bool(c),
            "last_heartbeat": hb,
            "status": st,
            "error_code": ec,
            "info": info,
            "last_msg": lm,
        }
    return None

def get_summary():
    """Return summary rows per charger."""
    conn = gw.sql.open_db(project="ocpp")
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

def _parse_date(date_str: str) -> Optional[int]:
    """Parse YYYY-MM-DD or ISO datetime to epoch seconds."""
    if not date_str:
        return None
    try:
        if len(date_str) == 10:
            dt = datetime.fromisoformat(date_str)
        else:
            dt = datetime.fromisoformat(date_str.replace("Z", ""))
        return int(dt.timestamp())
    except Exception:
        return None

def iter_transactions(
    charger_id: str = None,
    *,
    start: int = None,
    end: int = None,
    sort: str = "start_time",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> Iterable[tuple]:
    """Iterate transaction rows with optional filtering and sorting."""
    conn = gw.sql.open_db(project="ocpp")
    sql = (
        "SELECT charger_id, transaction_id, start_time, stop_time, meter_start, meter_stop, reason, id_tag "
        "FROM transactions WHERE 1=1"
    )
    args: list = []
    if charger_id:
        sql += " AND charger_id=?"
        args.append(charger_id)
    if start:
        sql += " AND start_time>=?"
        args.append(int(start))
    if end:
        sql += " AND start_time<=?"
        args.append(int(end))
    valid = {"start_time", "stop_time", "meter_start", "meter_stop"}
    if sort not in valid:
        sort = "start_time"
    order_sql = "DESC" if str(order).lower() != "asc" else "ASC"
    sql += f" ORDER BY {sort} {order_sql}"
    sql += " LIMIT ? OFFSET ?"
    args.extend([int(limit), int(offset)])
    return gw.sql.execute(sql, connection=conn, args=tuple(args))

def get_active_transaction(charger_id: str):
    conn = gw.sql.open_db(project="ocpp")
    rows = gw.sql.execute(
        "SELECT charger_id, transaction_id, start_time, meter_start, id_tag FROM transactions WHERE charger_id=? AND stop_time IS NULL ORDER BY start_time DESC LIMIT 1",
        connection=conn,
        args=(charger_id,),
    )
    if rows:
        c, tid, st, ms, tag = rows[0]
        return {
            "charger_id": c,
            "transactionId": tid,
            "startTime": st,
            "meterStart": ms,
            "idTag": tag,
        }
    return None

def get_active_transactions():
    conn = gw.sql.open_db(project="ocpp")
    rows = gw.sql.execute(
        "SELECT charger_id, transaction_id, start_time, meter_start, id_tag FROM transactions WHERE stop_time IS NULL",
        connection=conn,
    )
    result = {}
    for c, tid, st, ms, tag in rows:
        result[c] = {
            "charger_id": c,
            "transactionId": tid,
            "startTime": st,
            "meterStart": ms,
            "idTag": tag,
        }
    return result

def get_active_chargers() -> list[str]:
    """Return list of charger IDs currently marked as connected."""
    gw.sql.model(CONNECTIONS, project="ocpp")  # ensure table exists
    conn = gw.sql.open_db(project="ocpp")
    rows = gw.sql.execute(
        "SELECT charger_id FROM connections WHERE connected=1",
        connection=conn,
    )
    return [r[0] for r in rows]

def get_meter_values(charger_id: str, transaction_id: int):
    conn = gw.sql.open_db(project="ocpp")
    rows = gw.sql.execute(
        "SELECT timestamp, measurand, value, unit, context FROM meter_values WHERE charger_id=? AND transaction_id=? ORDER BY timestamp",
        connection=conn,
        args=(charger_id, transaction_id),
    )
    grouped = {}
    for ts, meas, val, unit, ctx in rows:
        entry = grouped.setdefault(
            ts,
            {
                "timestamp": ts,
                "timestampStr": datetime.utcfromtimestamp(int(ts)).isoformat() + "Z",
                "sampledValue": [],
            },
        )
        entry["sampledValue"].append(
            {
                "measurand": meas,
                "value": val,
                "unit": unit,
                "context": ctx,
            }
        )
    return list(grouped.values())

def get_latest_meter_value(charger_id: str, transaction_id: int):
    """Return the most recent Energy.Active.Import.Register value in kWh."""
    conn = gw.sql.open_db(project="ocpp")
    rows = gw.sql.execute(
        """
        SELECT value, unit FROM meter_values
        WHERE charger_id=? AND transaction_id=?
          AND measurand='Energy.Active.Import.Register'
        ORDER BY timestamp DESC LIMIT 1
        """,
        connection=conn,
        args=(charger_id, transaction_id),
    )
    if rows:
        val, unit = rows[0]
        try:
            fval = float(val)
            if unit == 'Wh':
                fval /= 1000.0
            return fval
        except Exception:
            try:
                return float(val)
            except Exception:
                return None
    return None

def get_meter_series(chargers: Sequence[str], *, start: int = None, end: int = None):
    """Return dict of charger_id -> list of (timestamp, kWh)."""
    conn = gw.sql.open_db(project="ocpp")
    data = {}
    for cid in chargers:
        sql = (
            "SELECT timestamp, value FROM meter_values "
            "WHERE charger_id=? AND measurand='Energy.Active.Import.Register'"
        )
        args = [cid]
        if start:
            sql += " AND timestamp>=?"
            args.append(int(start))
        if end:
            sql += " AND timestamp<=?"
            args.append(int(end))
        sql += " ORDER BY timestamp"
        rows = gw.sql.execute(sql, connection=conn, args=tuple(args))
        data[cid] = [(int(ts), float(val)) for ts, val in rows]
    return data

def list_chargers() -> list[str]:
    """Return list of distinct charger_ids."""
    gw.sql.model(CONNECTIONS, project="ocpp")  # ensure table exists
    conn = gw.sql.open_db(project="ocpp")
    rows = gw.sql.execute(
        "SELECT charger_id FROM connections UNION SELECT DISTINCT charger_id FROM transactions ORDER BY charger_id",
        connection=conn,
    )
    return [r[0] for r in rows]

def view_charger_summary(**_):
    """Simple HTML summary of charger data."""
    rows = get_summary()
    html = [
        '<link rel="stylesheet" href="/static/ocpp/csms/charger_status.css">',
        "<h1>OCPP Charger Summary</h1>",
    ]
    if not rows:
        html.append("<p>No data.</p>")
        return "\n".join(html)
    html.append("<table class='ocpp-summary'>")
    html.append(
        "<tr><th>Charger</th><th>Sessions</th><th>Energy(kWh)</th><th>Last Stop</th><th>Last Error</th></tr>"
    )
    for r in rows:
        html.append(
            f"<tr><td>{r['charger_id']}</td><td>{r['sessions']}</td><td>{r['energy']}</td>"
            f"<td>{_fmt_time(r['last_stop'])}</td><td>{r['last_error'] or '-'}" + "</td></tr>"
        )
    html.append("</table>")
    return "\n".join(html)

def view_charger_details(
    *,
    charger_id: str = None,
    page: int = 1,
    sort: str = "start_time",
    order: str = "desc",
    since: str = None,
    until: str = None,
    **_,
):
    """Paginated table of transactions for a specific charger."""
    page = int(page or 1)
    offset = (page - 1) * 50
    start_ts = _parse_date(since)
    end_ts = _parse_date(until)
    chargers = list_chargers()
    if not charger_id and chargers:
        charger_id = chargers[0]
    rows = list(
        iter_transactions(
            charger_id,
            start=start_ts,
            end=end_ts,
            sort=sort,
            order=order,
            limit=50,
            offset=offset,
        )
    )
    html = [f"<h1>Transactions for {charger_id or 'All'}</h1>"]
    html.append("<form method='get' style='margin-bottom:1em;'>")
    html.append("<label>Charger: <select name='charger_id'>")
    for cid in chargers:
        sel = " selected" if cid == charger_id else ""
        html.append(f"<option value='{cid}'{sel}>{cid}</option>")
    html.append("</select></label> ")
    html.append(
        f"<label>Since: <input type='date' name='since' value='{since or ''}'></label> "
    )
    html.append(
        f"<label>Until: <input type='date' name='until' value='{until or ''}'></label> "
    )
    html.append("<label>Sort: <select name='sort'>")
    for f in ["start_time", "stop_time", "meter_start", "meter_stop"]:
        sel = " selected" if f == sort else ""
        html.append(f"<option value='{f}'{sel}>{f}</option>")
    html.append("</select></label> ")
    html.append("<label>Order: <select name='order'>")
    for o in ["asc", "desc"]:
        sel = " selected" if o == order else ""
        html.append(f"<option value='{o}'{sel}>{o}</option>")
    html.append("</select></label> ")
    html.append("<button type='submit'>Apply</button></form>")
    html.append("<table class='ocpp-details'>")
    html.append(
        "<tr><th>ID</th><th>Start</th><th>Stop</th><th>Meter Δ(kWh)</th><th>Reason</th></tr>"
    )
    for r in rows:
        delta = (r[5] or 0) - (r[4] or 0)
        html.append(
            f"<tr><td>{r[1]}</td><td>{_fmt_time(r[2])}</td><td>{_fmt_time(r[3])}</td>"
            f"<td>{round(delta/1000.0,3)}</td><td>{r[6] or ''}</td></tr>"
        )
    html.append("</table>")
    next_page = page + 1 if len(rows) >= 50 else None
    if page > 1 or next_page:
        html.append("<div class='pager'>")
        if page > 1:
            html.append(
                f"<a href='?charger_id={charger_id}&page={page-1}&sort={sort}&order={order}'>Prev</a>"
            )
        if next_page:
            html.append(
                f" <a href='?charger_id={charger_id}&page={next_page}&sort={sort}&order={order}'>Next</a>"
            )
        html.append("</div>")
    return "\n".join(html)

def view_time_series(*, chargers: list = None, start: str = None, end: str = None, **_):
    """Graph of energy usage over time for selected chargers."""
    chargers_all = list_chargers()
    chargers = gw.cast.to_list(chargers) if chargers else chargers_all
    start_ts = _parse_date(start)
    end_ts = _parse_date(end)
    series = get_meter_series(chargers, start=start_ts, end=end_ts)
    html = ["<h1>Energy Time Series</h1>"]
    html.append("<form method='get' style='margin-bottom:1em;'>")
    for cid in chargers_all:
        checked = "checked" if cid in chargers else ""
        html.append(
            f"<label style='margin-right:.6em;'><input type='checkbox' name='chargers' value='{cid}' {checked}> {cid}</label>"
        )
    html.append(
        f"<label>Start: <input type='date' name='start' value='{start or ''}'></label> "
    )
    html.append(
        f"<label>End: <input type='date' name='end' value='{end or ''}'></label> "
    )
    html.append("<button type='submit'>Show</button></form>")
    html.append('<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>')
    html.append('<canvas id="tschart" height="320"></canvas>')
    html.append('<script>')
    html.append(f"const series = {json.dumps(series)};")
    html.append(
        "const datasets = Object.entries(series).map(([cid, vals]) => ({label: cid, data: vals.map(v => ({x:v[0]*1000,y:v[1]}))}));"
    )
    html.append(
        "new Chart(document.getElementById('tschart'), {type:'line', data:{datasets}, options:{parsing:false, scales:{x:{type:'time',time:{unit:'day'}}, y:{title:{display:true,text:'kWh'}}}}});"
    )
    html.append('</script>')
    return "\n".join(html)

