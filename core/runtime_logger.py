import logging
import os
from logging.handlers import RotatingFileHandler
from config import LOG_FOLDER


def setup_logger():

    os.makedirs(LOG_FOLDER, exist_ok=True)

    log_file = os.path.join(LOG_FOLDER, "qc_runtime.log")

    logger = logging.getLogger("QC_RUNTIME")
    logger.setLevel(logging.INFO)

    handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8"   # TAMBAHKAN INI
    )

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
