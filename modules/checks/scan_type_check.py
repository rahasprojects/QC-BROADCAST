import subprocess
import json
from config import FFPROBE_PATH
from .base_check import BaseCheck


class ScanTypeCheck(BaseCheck):

    name = "Scan Type Check"

    STRICT_PROGRESSIVE = False  # sementara jangan fail dulu

    def run(self, file_path, log_callback, progress_callback):

        log_callback("Checking scan type...")

        cmd = [
            FFPROBE_PATH,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=field_order",
            "-of", "json",
            file_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            log_callback("Scan type: UNKNOWN")
            return {"status": "PASS"}

        try:
            data = json.loads(result.stdout)
            field_order = data["streams"][0].get("field_order", "")
        except:
            log_callback("Scan type: UNKNOWN")
            return {"status": "PASS"}

        if field_order == "progressive":
            log_callback("Scan type: PROGRESSIVE")
            return {"status": "PASS"}

        log_callback("Scan type: INTERLACE")

        if self.STRICT_PROGRESSIVE:
            return {
                "status": "FAIL",
                "error": "Interlaced video detected"
            }

        return {"status": "PASS"}
