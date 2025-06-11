# projects/etron.py

import os
import json
import csv
from datetime import datetime, timedelta
from gway import gw


def report(data_dir, *, 
        add_days=0, after=None, before=None, batch=None):
    r"""Load data from EV IOCHARGER .json files to CSV format.
        > gway etron report san-pedro
        > gway etron report calzada-del-valle
        > gway etron report porsche-centre
        This assumes the files are at work/etron/records/<location>.
    """
    # This function has been tested with real eTRON EVCS OCPP 1.6 for CSS2 (modify with care.)
    data_dir = data_dir.replace("-", "_")
    dir_name = os.path.split(data_dir.strip('/').strip('\\'))[-1]
    data_dir = gw.resource("work", "etron", "records", data_dir)
    output_csv = gw.resource("work", "etron", "reports", f"{dir_name}_records.csv")
    gw.info(f"Reading data files from {data_dir}")

    columns = ["LOCACION", "CONECTOR",  # "FECHA INICIO", "FECHA FINAL", 
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

        for filename in os.listdir(data_dir):
            if not filename.endswith(".dat"):
                continue

            file_path = os.path.join(data_dir, filename)
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
                        # "FECHA INICIO": formatted_start_time,
                        # "FECHA FINAL": formatted_stop_time,
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
