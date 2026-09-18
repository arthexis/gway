# file: projects/etron.py

import os
import json
import csv
from datetime import datetime, timedelta
from gway import gw


def extract_records(location, *, 
        add_days=0, after=None, before=None, batch=None):
    r"""Load data from EV IOCHARGER .json files to CSV format.
        > gway etron extract_records san-pedro
        > gway etron extract_records calzada-del-valle
        > gway etron extract_records porsche-centre
        This assumes the files are at work/etron/records/<location>.
    """
    # This function has been tested with real eTRON EVCS OCPP 1.6 for CSS2 (modify with care.)
    location = location.replace("-", "_")
    dir_name = os.path.split(location.strip('/').strip('\\'))[-1]
    location = gw.resource("work", "etron", "records", location)
    output_csv = gw.resource("work", "etron", "reports", f"{dir_name}_records.csv")
    gw.info(f"Reading data files from {location}")

    columns = ["LOCACION", "CONECTOR", "FECHA INICIO", "FECHA FINAL", 
               "WH INICIO", "WH FINAL", "WH USADOS", 
               r"% INICIAL", r"% FINAL", "RAZON FINAL", 
               "FECHA REGISTRO", "ARCHIVO FUENTE",  # "SISTEMA ORIGEN", "LOTE"
            ]
    
    if batch:
        columns.append("BATCH")

    if after and isinstance(after, (str, int)):
        after = datetime.strptime(str(after), "%Y%m%d").date()

    if before and isinstance(before, (str, int)):
        before = datetime.strptime(str(before), "%Y%m%d").date()

    with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=columns)
        writer.writeheader()

        for filename in os.listdir(location):
            if not filename.endswith(".dat"):
                continue

            file_path = os.path.join(location, filename)
            try:
                with open(file_path, 'r') as file:
                    data = json.load(file)

                    try:
                        start_time = datetime.strptime(
                            data.get("startTimeStr", ""), "%Y-%m-%dT%H:%M:%SZ")
                        stop_time = datetime.strptime(
                            data.get("stopTimeStr", ""), "%Y-%m-%dT%H:%M:%SZ")
                        start_time += timedelta(days=add_days)
                        stop_time += timedelta(days=add_days)

                        if after and start_time.date() < after:
                            continue
                        if before and stop_time.date() > before:
                            continue

                        formatted_start_time = start_time.strftime("%Y-%m-%d %H:%M:%S")
                        formatted_stop_time = stop_time.strftime("%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        gw.error(f"Invalid time format in {filename}. Skipping")
                        continue

                    # Get file modification time
                    try:
                        mtime = os.path.getmtime(file_path)
                        fecha_registro = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                    except Exception as e:
                        gw.warn(f"Could not get mtime for {filename}, setting FECHA REGISTRO to empty.")
                        fecha_registro = ""

                    record = {
                        "LOCACION": dir_name.title(),
                        "CONECTOR": data.get("connectorId", ""),
                        "FECHA INICIO": formatted_start_time,
                        "FECHA FINAL": formatted_stop_time,
                        "WH INICIO": data.get("meterStart", 0),
                        "WH FINAL": data.get("meterStop", 0),
                        "WH USADOS": data.get("meterStop", 0) - data.get("meterStart", 0),
                        r"% INICIAL": data.get("startSoC", 0),
                        r"% FINAL": data.get("stopSoC", 0),
                        "RAZON FINAL": data.get("reasonStr", ""),
                        "FECHA REGISTRO": fecha_registro,
                        "ARCHIVO FUENTE": filename,
                        # "SISTEMA ORIGEN": dir_name,
                        # "LOTE": batch,
                    }

                    if batch:
                        record["BATCH"] = batch

                    writer.writerow(record)
            except Exception as e:
                gw.error(f"Error processing {filename}: {e}")
                gw.exception(e)

    gw.info(f"Data successfully written to {output_csv}")
    return {"status": "success", "output_csv": output_csv}

def summary_report(report_path, *, output_path=None):
    """
    Generate a summary CSV from a detailed EVCS report.
    Columns: DIA, KWH_TOTAL, TRANSACCIONES, KWH_MAX
    """
    import pandas as pd

    # If given a name like 'san-pedro', assume report file is work/etron/reports/<name>_records.csv
    if not report_path.endswith(".csv"):
        dir_name = os.path.split(report_path.strip('/').strip('\\'))[-1]
        report_path = gw.resource("work", "etron", "reports", f"{dir_name}_records.csv")

    if output_path is None:
        dir_name = os.path.splitext(os.path.basename(report_path))[0].replace("_records", "")
        output_path = gw.resource("work", "etron", "reports", f"{dir_name}_summary.csv")

    # Load the CSV
    df = pd.read_csv(report_path, encoding="utf-8")

    # Create DIA column (date of FECHA INICIO)
    df["DIA"] = pd.to_datetime(df["FECHA INICIO"]).dt.date

    # Group and aggregate
    grouped = df.groupby("DIA").agg(
        KWH_TOTAL = ("WH USADOS", lambda x: round(x.sum() / 1000, 3)),
        TRANSACCIONES = ("WH USADOS", "count"),
        KWH_MAX = ("WH USADOS", lambda x: round(x.max() / 1000, 3))
    ).reset_index()

    # Write summary CSV
    grouped.to_csv(output_path, index=False, encoding="utf-8")

    gw.info(f"Summary written to {output_path}")
    return {"status": "success", "output_csv": output_path}


def view_extract_records(
    *,
    location: str = None,
    add_days: int = 0,
    after: str = None,
    before: str = None,
    batch: str = None,
):
    """Simple web form to run :func:`extract_records`."""
    from bottle import request
    import html

    msg = ""
    if request.method == "POST":
        location = request.forms.get("location") or location
        add_days = int(request.forms.get("add_days") or 0)
        after = request.forms.get("after") or None
        before = request.forms.get("before") or None
        batch = request.forms.get("batch") or None

        if not location:
            msg = "<p class='error'>Location is required.</p>"
        else:
            try:
                result = extract_records(
                    location,
                    add_days=add_days,
                    after=after,
                    before=before,
                    batch=batch,
                )
                out = html.escape(result.get("output_csv", ""))
                msg = f"<p>Records written to {out}</p>"
            except Exception as exc:
                gw.exception(exc)
                msg = f"<p class='error'>Error: {html.escape(str(exc))}</p>"

    location_val = html.escape(location or "")
    after_val = html.escape(after or "")
    before_val = html.escape(before or "")
    batch_val = html.escape(batch or "")

    return (
        "<h1>Extract eTRON Records</h1>"
        f"{msg}"
        "<form method='post'>"
        f"<input name='location' placeholder='Location' required value='{location_val}'> "
        f"<input type='number' name='add_days' value='{add_days}' placeholder='Add Days'> "
        f"<input name='after' placeholder='After YYYYMMDD' value='{after_val}'> "
        f"<input name='before' placeholder='Before YYYYMMDD' value='{before_val}'> "
        f"<input name='batch' placeholder='Batch' value='{batch_val}'> "
        "<button type='submit'>Extract</button>"
        "</form>"
    )
