import subprocess
from config import FFMPEG_PATH
from .base_check import BaseCheck


class SilenceCheck(BaseCheck):

    name = "Silence Check"

    NOISE_THRESHOLD = "-40dB"   # di bawah ini dianggap silent
    DURATION_THRESHOLD = 1.0    # >= 1 detik dianggap FAIL

    def run(self, file_path, log_callback, progress_callback):

        log_callback("Checking audio silence...")

        cmd = [
            FFMPEG_PATH,
            "-i", file_path,
            "-af", f"silencedetect=noise={self.NOISE_THRESHOLD}:d={self.DURATION_THRESHOLD}",
            "-f", "null",
            "-"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            log_callback("Silence scan skipped.")
            return {"status": "PASS"}

        stderr = result.stderr

        if "silence_start" in stderr:
            log_callback("Silence segment detected.")
            return {
                "status": "FAIL",
                "error": "Audio silence detected"
            }

        log_callback("No silence detected.")
        return {"status": "PASS"}
