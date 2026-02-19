

import os
import time
import csv
import threading
import subprocess
import queue
import tkinter as tk
from tkinter import ttk
import psutil
import json
import numpy as np
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from config import *
from utils.time_utils import sec_to_tc
from utils.file_utils import wait_until_file_released, wait_until_copy_complete
from utils.ffmpeg_utils import check_metadata, get_video_duration
from modules.freeze import detect_freeze
from core.watcher import MXFHandler
from core.worker import worker_loop
from core.logger import result_writer_loop
from core.pipeline import qc_process_file
from core.runtime_logger import setup_logger
from tkinter import messagebox, filedialog
from datetime import datetime
import shutil
import os
import csv
import json  # Tambah ini




# =====================================================
# SETUP RUNTIME LOGGER
# =====================================================

runtime_logger = setup_logger()


# =====================================================
# GLOBAL STATE
# =====================================================

file_queue = queue.Queue()
result_queue = queue.Queue()

lock = threading.Lock()
processing_files = set()
processed_recently = {}


# =====================================================
# GUI SAFE UPDATE
# =====================================================

def log_message(msg):
    runtime_logger.info(msg)
    root.after(0, lambda: append_text(msg))


def append_text(msg):
    textbox.insert(tk.END, msg + "\n")
    textbox.see(tk.END)

def set_progress(value):
    root.after(0, lambda: progress_var.set(value))


# =====================================================
# DASHBOARD
# =====================================================

def update_dashboard():
    cpu_label.config(text=f"CPU: {psutil.cpu_percent()}%")
    worker_label.config(text=f"Workers: {MAX_WORKERS}")
    queue_label.config(text=f"Queue: {file_queue.qsize()} | Results: {result_queue.qsize()}")
    root.after(1000, update_dashboard)

# =====================================================
# VALIDATION
# =====================================================

def validate_environment():
    errors = []
    for folder in WATCH_FOLDERS:
        if not os.path.exists(folder):
            errors.append(f"Folder not found: {folder}")
    if not os.path.isfile(FFPROBE_PATH):
        errors.append("ffprobe.exe not found")
    if not os.path.isfile(FFMPEG_PATH):
        errors.append("ffmpeg.exe not found")
    return errors


# =====================================================
# EXPORT FUNCTION
# =====================================================

def export_report():
    """Export laporan QC ke CSV dengan kolom per check"""
    from tkinter import filedialog
    import csv
    import json
    
    # Source file
    source_file = os.path.join(LOG_FOLDER, "qc_log.csv")
    
    if not os.path.exists(source_file):
        return  # Diam saja, tidak ada notifikasi
    
    # Minta user pilih lokasi simpan
    dest_file = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        title="Save Report As",
        initialfile=f"qc_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )
    
    if not dest_file:  # User cancel
        return
    
    try:
        # Baca source CSV
        with open(source_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        if not rows:
            return
        
        # Kumpulkan semua key dari JSON Details
        all_detail_keys = set()
        for row in rows:
            try:
                details = json.loads(row.get('Details', '{}'))
                # Flatten nested dict jadi key seperti "ScanType_scan_type"
                flatten_details(details, all_detail_keys)
            except:
                pass
        
        # Siapkan header baru
        base_headers = ['Date', 'File', 'Status', 'Freeze', 'Error']
        detail_headers = sorted(list(all_detail_keys))  # Urut biar rapi
        new_headers = base_headers + detail_headers
        
        # Tulis ke file tujuan
        with open(dest_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=new_headers)
            writer.writeheader()
            
            for row in rows:
                new_row = {
                    'Date': row.get('Date', ''),
                    'File': row.get('File', ''),
                    'Status': row.get('Status', ''),
                    'Freeze': row.get('Freeze', ''),
                    'Error': row.get('Error', '')
                }
                
                # Parse Details dan flatten
                try:
                    details = json.loads(row.get('Details', '{}'))
                    flat_details = flatten_details_to_dict(details)
                    new_row.update(flat_details)
                except:
                    pass
                
                writer.writerow(new_row)
        
        # SELESAI - diam saja, tidak ada notifikasi
        
    except Exception as e:
        # Diam saja kalau error, tidak usah notifikasi
        pass


def flatten_details(details, key_set):
    """Kumpulkan semua key dari nested dict untuk header"""
    if isinstance(details, dict):
        for key, value in details.items():
            if isinstance(value, dict):
                # Recursive untuk nested dict
                for sub_key, sub_value in value.items():
                    composite_key = f"{key}_{sub_key}"
                    key_set.add(composite_key)
            else:
                key_set.add(key)
    elif isinstance(details, list):
        for item in details:
            flatten_details(item, key_set)


def flatten_details_to_dict(details, prefix=''):
    """Flatten nested dict jadi satu level dictionary"""
    result = {}
    if isinstance(details, dict):
        for key, value in details.items():
            new_key = f"{prefix}_{key}" if prefix else key
            if isinstance(value, dict):
                result.update(flatten_details_to_dict(value, new_key))
            elif isinstance(value, list):
                result[new_key] = str(value)  # List jadi string
            else:
                result[new_key] = value
    return result



# =====================================================
# MAIN GUI
# =====================================================

root = tk.Tk()
root.title("MNC QC Scanner")
root.geometry("750x550")

cpu_label = tk.Label(root, text="")
cpu_label.pack()

worker_label = tk.Label(root, text="")
worker_label.pack()

queue_label = tk.Label(root, text="")
queue_label.pack()

progress_var = tk.IntVar()
progress_bar = ttk.Progressbar(root, variable=progress_var, maximum=100)
progress_bar.pack(fill="x", padx=10, pady=5)

# =====================================================
# BUTTON FRAME
# =====================================================
button_frame = tk.Frame(root)
button_frame.pack(fill="x", padx=10, pady=5)

export_btn = tk.Button(
    button_frame,
    text="Export Report to CSV",
    command=export_report,
    bg="#4CAF50",
    fg="white",
    padx=10,
    pady=5
)
export_btn.pack(side="left")

# Progress bar tetap di bawah
progress_bar.pack(fill="x", padx=10, pady=5)



textbox = tk.Text(root, height=22)
textbox.pack(fill="both", expand=True, padx=10, pady=5)

scrollbar = tk.Scrollbar(textbox)
scrollbar.pack(side="right", fill="y")
textbox.config(yscrollcommand=scrollbar.set)
scrollbar.config(command=textbox.yview)

errors = validate_environment()

if errors:
    append_text("SYSTEM ERROR:")
    for e in errors:
        append_text(e)
else:
    append_text("MNC QC Scanner Started...")
    append_text("------------------------------------")

    observer = Observer()
    handler = MXFHandler(
        file_queue=file_queue,
        lock=lock,
        processing_files=processing_files,
        processed_recently=processed_recently,
        log_callback=log_message
    )

    for folder in WATCH_FOLDERS:
        observer.schedule(handler, folder, recursive=False)
    observer.start()

    threading.Thread(
        target=worker_loop,
        args=(
            file_queue,
            result_queue,
            lambda path: qc_process_file(path, log_message, set_progress),
            lock,
            processing_files,
            processed_recently,
            set_progress
            ),
            daemon=True
        ).start()


    threading.Thread(
        target=result_writer_loop,
        args=(result_queue, log_message),
        daemon=True
    ).start()

    update_dashboard()







try:
    root.mainloop()
except KeyboardInterrupt:
    print("\nProgram stopped by user (Ctrl+C)")
    # Bersih-bersih sebelum exit
    if 'observer' in locals():
        observer.stop()
        observer.join()
    print("Shutdown complete.")
except Exception as e:
    print(f"Unexpected error: {e}")

