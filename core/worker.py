import time
from concurrent.futures import ThreadPoolExecutor

from config import MAX_WORKERS
from utils.tracking_utils import mark_file_processed, load_processed_files


def worker_loop(file_queue, result_queue, process_function,
                lock, processing_files, processed_recently,
                progress_callback):

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        while True:
            path = file_queue.get()
            executor.submit(
                process_wrapper,
                path,
                result_queue,
                process_function,
                lock,
                processing_files,
                processed_recently,
                progress_callback
            )


def process_wrapper(path, result_queue, process_function,
                    lock, processing_files, processed_recently,
                    progress_callback):
    try:
        result = process_function(path)
        result_queue.put(result)
        
        with lock:
            tracking = load_processed_files()
            mark_file_processed(path, tracking)
            
    finally:
        with lock:
            processing_files.discard(path)
            processed_recently[path] = time.time()

        progress_callback(0)  # ← INI YANG RESET KE 0%