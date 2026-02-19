import os
import time
import csv
import threading
import subprocess
import queue
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import tkinter as tk
from tkinter import ttk
import psutil
import json
import numpy as np

# =====================================================
# CONFIG
# =====================================================

WATCH_FOLDERS = [r"D:\test_vid"]   # nanti tinggal tambah 3 folder SAS
LOG_FOLDER = r"C:\MNC_QC_LOG"
os.makedirs(LOG_FOLDER, exist_ok=True)

FFPROBE_PATH = os.path.join(os.getcwd(), "ffprobe.exe")
FFMPEG_PATH  = os.path.join(os.getcwd(), "ffmpeg.exe")

MAX_WORKERS = max(1, os.cpu_count() - 1)

# QC THRESHOLDS
FREEZE_MIN_FRAMES = 2
FREEZE_MAX_FRAMES = 6
MOTION_GATE = 0.6
BLACK_GATE = 5

DOWNSCALE_W = 640
DOWNSCALE_H = 360
ASSUMED_FPS = 25

COOLDOWN_SECONDS = 60

# =====================================================
# GLOBAL STATE
# =====================================================

file_queue = queue.Queue()
result_queue = queue.Queue()

lock = threading.Lock()
processing_files = set()
processed_recently = {}

# =====================================================
# UTILITIES
# =====================================================

def sec_to_tc(seconds):
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m:02d}:{s:05.2f}"

# =====================================================
# LOGGING
# =====================================================

def write_csv_row(row):
    log_file = os.path.join(LOG_FOLDER, "qc_log.csv")
    file_exists = os.path.isfile(log_file)

    with open(log_file, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "Date", "File", "Status",
                "Freeze_Timestamps", "Error"
            ])
        writer.writerow(row)

# =====================================================
# GUI SAFE UPDATE
# =====================================================

def log_message(msg):
    root.after(0, lambda: append_text(msg))

def append_text(msg):
    textbox.insert(tk.END, msg + "\n")
    textbox.see(tk.END)

def set_progress(value):
    root.after(0, lambda: progress_var.set(value))

# =====================================================
# FILE STABILITY CHECK
# =====================================================

def wait_until_file_released(path):
    while True:
        try:
            with open(path, 'rb'):
                return
        except:
            time.sleep(2)

def wait_until_copy_complete(path):
    stable = 0
    last_size = -1

    while stable < 5:
        try:
            size = os.path.getsize(path)
            if size == last_size:
                stable += 1
            else:
                stable = 0
            last_size = size
            time.sleep(2)
        except:
            return False
    return True

# =====================================================
# METADATA ENGINE
# =====================================================

def check_metadata(file_path):
    try:
        cmd = [
            FFPROBE_PATH,
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return False, "FFPROBE ERROR"

        data = json.loads(result.stdout)
        video_stream = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
        if not video_stream:
            return False, "No video stream"

        if video_stream.get("width") != 1920 or video_stream.get("height") != 1080:
            return False, "Resolution not 1920x1080"

        return True, ""

    except Exception as e:
        return False, str(e)

# =====================================================
# VIDEO ENGINE CORE
# =====================================================

def get_video_duration(file_path):
    cmd = [
        FFPROBE_PATH,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except:
        return 0

# =====================================================
# FREEZE DETECTION ENGINE
# =====================================================

def detect_freeze(file_path):
    duration = get_video_duration(file_path)
    if duration == 0:
        return []

    cmd = [
        FFMPEG_PATH,
        "-loglevel", "quiet",
        "-nostats",
        "-i", file_path,
        "-vf", f"yadif=0:-1:0,scale={DOWNSCALE_W}:{DOWNSCALE_H}",
        "-f", "rawvideo",
        "-pix_fmt", "gray",
        "-"
    ]

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    frame_size = DOWNSCALE_W * DOWNSCALE_H
    prev_frame = None
    freeze_counter = 0
    frame_number = 0
    freeze_events = []

    total_frames = int(duration * ASSUMED_FPS)

    while True:
        raw = process.stdout.read(frame_size)
        if len(raw) < frame_size:
            break

        frame = np.frombuffer(raw, dtype=np.uint8)

        # Skip fade-to-black / near-black
        if np.mean(frame) < BLACK_GATE:
            freeze_counter = 0
            prev_frame = frame
            frame_number += 1
            continue

        if prev_frame is not None:
            diff = np.mean(np.abs(frame - prev_frame))

            # Motion gate
            if diff < MOTION_GATE:
                freeze_counter += 1
            else:
                if FREEZE_MIN_FRAMES <= freeze_counter <= FREEZE_MAX_FRAMES:
                    sec = frame_number / ASSUMED_FPS
                    freeze_events.append(sec)
                freeze_counter = 0

        prev_frame = frame
        frame_number += 1

        if total_frames > 0:
            set_progress(int((frame_number / total_frames) * 100))

    # Handle freeze at tail
    if FREEZE_MIN_FRAMES <= freeze_counter <= FREEZE_MAX_FRAMES:
        sec = frame_number / ASSUMED_FPS
        freeze_events.append(sec)

    process.stdout.close()
    process.wait()
    set_progress(100)

    return freeze_events

# =====================================================
# QC PIPELINE (PER FILE)
# =====================================================

def qc_process_file(file_path):
    file_name = os.path.basename(file_path)
    folder = os.path.dirname(file_path)

    log_message(f"Detected : {file_name}")
    log_message(f"Folder   : {folder}")
    log_message("Waiting file release...")
    wait_until_file_released(file_path)
    time.sleep(1)

    log_message("Checking metadata...")
    valid, err = check_metadata(file_path)
    if not valid:
        return {
            "file": file_name,
            "status": "FAIL",
            "freeze": [],
            "error": err
        }

    log_message("Metadata OK")
    log_message("Starting freeze scan...")

    freezes = detect_freeze(file_path)

    if freezes:
        tc_list = [sec_to_tc(x) for x in freezes]
        log_message(f"FREEZE DETECTED @ {tc_list}")
        return {
            "file": file_name,
            "status": "FAIL",
            "freeze": tc_list,
            "error": "Freeze detected"
        }
    else:
        log_message("No freeze detected.")
        return {
            "file": file_name,
            "status": "PASS",
            "freeze": [],
            "error": ""
        }

# =====================================================
# RESULT WRITER (SINGLE THREAD, SAFE)
# =====================================================

def result_writer_loop():
    while True:
        result = result_queue.get()
        if result is None:
            break

        write_csv_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            result["file"],
            result["status"],
            ",".join(result["freeze"]),
            result["error"]
        ])

        log_message(f"RESULT: {result['file']} → {result['status']}")

# =====================================================
# WORKER LOOP
# =====================================================

def worker_loop():
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        while True:
            path = file_queue.get()
            executor.submit(process_wrapper, path)

def process_wrapper(path):
    try:
        result = qc_process_file(path)
        result_queue.put(result)
    finally:
        with lock:
            processing_files.discard(path)
            processed_recently[path] = time.time()
        set_progress(0)

# =====================================================
# WATCHDOG HANDLER
# =====================================================

class MXFHandler(FileSystemEventHandler):

    def process(self, path):
        if not path.lower().endswith(".mxf"):
            return

        now = time.time()
        with lock:
            if path in processed_recently and now - processed_recently[path] < COOLDOWN_SECONDS:
                return
            if path in processing_files:
                return
            processing_files.add(path)

        threading.Thread(target=self.wait_until_complete, args=(path,), daemon=True).start()

    def on_created(self, event):
        if not event.is_directory:
            self.process(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self.process(event.src_path)

    def wait_until_complete(self, path):
        log_message(f"Waiting copy complete: {os.path.basename(path)}")
        if wait_until_copy_complete(path):
            log_message("Copy complete. Start QC.")
            file_queue.put(path)
        else:
            with lock:
                processing_files.discard(path)

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
    handler = MXFHandler()
    for folder in WATCH_FOLDERS:
        observer.schedule(handler, folder, recursive=False)
    observer.start()

    threading.Thread(target=worker_loop, daemon=True).start()
    threading.Thread(target=result_writer_loop, daemon=True).start()
    update_dashboard()

root.mainloop()
