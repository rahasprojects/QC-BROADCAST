import time
import threading
import os
from watchdog.events import FileSystemEventHandler

from config import COOLDOWN_SECONDS
from utils.file_utils import wait_until_copy_complete
from utils.tracking_utils import load_processed_files, is_file_processed


class MXFHandler(FileSystemEventHandler):

    def __init__(self, file_queue, lock, processing_files, processed_recently, log_callback):
        self.file_queue = file_queue
        self.lock = lock
        self.processing_files = processing_files
        self.processed_recently = processed_recently
        self.log = log_callback
        # Load tracking file sekali di awal
        self.processed_tracking = load_processed_files()

    def process(self, path):
        if not path.lower().endswith(".mxf"):
            return

        now = time.time()

        with self.lock:
            # CEK PERTAMA: Apakah file sudah pernah diproses (tracking permanen)?
            if is_file_processed(path, self.processed_tracking):
                self.log(f"File already processed permanently. Skipping: {os.path.basename(path)}")
                return

            # CEK KEDUA: Apakah file sedang dalam cooldown?
            if path in self.processed_recently and \
               now - self.processed_recently[path] < COOLDOWN_SECONDS:
                return

            # CEK KETIGA: Apakah file sedang diproses?
            if path in self.processing_files:
                return

            self.processing_files.add(path)

        # Proses di thread terpisah
        threading.Thread(
            target=self.wait_until_complete,
            args=(path,),
            daemon=True
        ).start()

    def on_created(self, event):
        if not event.is_directory:
            self.process(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self.process(event.src_path)

    def wait_until_complete(self, path):
        self.log(f"Waiting copy complete: {os.path.basename(path)}")

        if wait_until_copy_complete(path):
            # CEK LAGI sebelum masuk queue (antisipasi race condition)
            with self.lock:
                if is_file_processed(path, self.processed_tracking):
                    self.log(f"File already processed. Skipping queue.")
                    self.processing_files.discard(path)
                    return
                
                # Reload tracking file kalau-kalau ada perubahan dari thread lain
                self.processed_tracking = load_processed_files()
                
                # Cek sekali lagi setelah reload
                if is_file_processed(path, self.processed_tracking):
                    self.log(f"File already processed (after reload). Skipping.")
                    self.processing_files.discard(path)
                    return

            self.log("Copy complete. Start QC.")
            self.file_queue.put(path)
        else:
            with self.lock:
                self.processing_files.discard(path)