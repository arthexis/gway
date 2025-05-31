from gway import gw


def extract(data_dir, *, 
        add_days=0, output_csv=None, after=None, before=None, batch=None):
    r"""Load data from EV IOCHARGER to CSV format.
        > gsol etron extract-records "temp\etron\san_pedro" 
        > gsol etron extract-records "temp\etron\calzada_del_valle"   
    """
    import os
    import json
    import csv
    from datetime import datetime, timedelta

    dir_name = os.path.split(data_dir.strip('/').strip('\\'))[-1]
    data_dir = gw.resource(data_dir)
    output_csv = output_csv or gw.resource("work", f"{dir_name}_records.csv")
    gw.info(f"Reading data files from {data_dir}")

    # Define the columns for the CSV
    # columns = ["Connector ID", "Start Time", "Stop Time", "Meter Start", "Meter Stop", 
    #               "Energy Consumed", "Start SoC", "Stop SoC", "Reason for Stopping", 
    #               "Total Energy Offered", "File Name"]

    columns = ["LOCACION", "CONECTOR", "FECHA INICIO", "FECHA FINAL", 
               "WH INICIO", "WH FINAL", "WH USADOS", 
               r"% INICIAL", r"% FINAL", "RAZON FINAL", 
               "ARCHIVO FUENTE", "SISTEMA ORIGEN", "LOTE"]
    
    if batch:
        columns.append("BATCH")

    if after and isinstance(after, (str, int)):
        after = datetime.strptime(str(after), "%Y%m%d").date()

    if before and isinstance(before, (str, int)):
        before = datetime.strptime(str(before), "%Y%m%d").date()

    # Create and open the CSV file
    with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=columns)
        writer.writeheader()

        # Process each .dat file in the data_dir
        for filename in os.listdir(data_dir):
            if not filename.endswith(".dat"):
                continue
            # gsol.logger.debug(f"Loading {filename}")
            file_path = os.path.join(data_dir, filename)
            try:
                with open(file_path, 'r') as file:
                    data = json.load(file)

                    # Convert and adjust Start Time and Stop Times
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

                    # Extract the relevant data
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
                        "ARCHIVO FUENTE": filename,
                        "SISTEMA ORIGEN": dir_name, 
                        "LOTE": batch,
                    }

                    # Write the record to the CSV file
                    writer.writerow(record)
            except Exception as e:
                gw.error(f"Error processing {filename}: {e}")

    gw.info(f"Data successfully written to {output_csv}")
    return {"status": "success", "output_csv": output_csv}
