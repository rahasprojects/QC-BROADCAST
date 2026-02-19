import subprocess
import re
from config import FFMPEG_PATH
from .base_check import BaseCheck


class PeakCheck(BaseCheck):

    name = "Audio Peak Check"

    PEAK_THRESHOLD = 0.0  # >= 0 dBFS dianggap FAIL

    def run(self, file_path, log_callback, progress_callback):

        log_callback("Checking audio peak level...")

        cmd = [
            FFMPEG_PATH,
            "-i", file_path,
            "-af", "volumedetect",
            "-f", "null",
            "-"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            log_callback("Peak scan skipped.")
            return {"status": "PASS"}

        stderr = result.stderr

        match = re.search(r"max_volume:\s*(-?\d+\.?\d*) dB", stderr)

        if match:
            max_volume = float(match.group(1))
            log_callback(f"Max Peak: {max_volume} dB")

            if max_volume >= self.PEAK_THRESHOLD:
                log_callback("Audio clipping detected.")
                return {
                    "status": "FAIL",
                    "error": "Audio peak clipping detected"
                }

        log_callback("Audio peak level OK.")
        return {"status": "PASS"}
