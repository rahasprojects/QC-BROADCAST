import os
import csv
import json
from datetime import datetime

from config import LOG_FOLDER


def write_csv_row(row):
    """
    Write row ke CSV dengan format:
    Date, File, Status, Details (JSON), Freeze_Timestamps, Error
    """
    log_file = os.path.join(LOG_FOLDER, "qc_log.csv")
    file_exists = os.path.isfile(log_file)

    try:
        with open(log_file, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)

            if not file_exists:
                writer.writerow([
                    "Date",
                    "File",
                    "Status",
                    "Details",           # JSON string
                    "Freeze_Timestamps",
                    "Error"
                ])

            writer.writerow(row)
    except Exception as e:
        # Silent fail untuk writing CSV
        pass


def result_writer_loop(result_queue, log_callback):
    """
    Loop untuk menulis hasil QC ke CSV
    """
    while True:
        result = result_queue.get()

        if result is None:
            break

        # Convert details ke JSON string
        details_json = json.dumps(result.get("details", {}), indent=None)
        
        write_csv_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            result.get("file", "Unknown"),
            result.get("status", "UNKNOWN"),
            details_json,
            ",".join(result.get("freeze", [])),
            result.get("error", "")
        ])

        # Tampilkan di GUI dengan tanda SELESAI
        status = result.get("status", "UNKNOWN")
        file_name = result.get("file", "Unknown")
        
        if status == "PASS":
            log_callback(f"✅ SELESAI: {file_name} → {status}")
        else:
            log_callback(f"❌ SELESAI: {file_name} → {status}")
        
        # Tambah garis pemisah biar jelas
        log_callback("─" * 50)