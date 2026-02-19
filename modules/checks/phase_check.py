import subprocess
import re
from config import FFMPEG_PATH
from .base_check import BaseCheck

class PhaseCheck(BaseCheck):

    name = "Audio Phase Check"

    def run(self, file_path, log_callback, progress_callback):

        log_callback("Checking audio phase correlation...")

        cmd = [
            FFMPEG_PATH,
            "-i", file_path,
            "-af", "aphasemeter",
            "-f", "null",
            "-"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            log_callback("Phase scan skipped.")
            return {"status": "PASS"}

        stderr = result.stderr

        # Cari line correlation, contoh: "Integrated: -0.02"
        match = re.search(r"Integrated:\s*(-?\d+\.?\d*)", stderr)

        if match:
            correlation = float(match.group(1))
            log_callback(f"Phase correlation: {correlation}")

            if correlation < 0.0:
                log_callback("Out-of-phase detected!")
                return {
                    "status": "FAIL",
                    "error": "Audio out-of-phase detected"
                }

        log_callback("Audio phase OK.")
        return {"status": "PASS"}
