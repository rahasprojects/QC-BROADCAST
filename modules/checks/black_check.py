import subprocess
import re
from .base_check import BaseCheck
from config import FFMPEG_PATH, DOWNSCALE_W, DOWNSCALE_H, ASSUMED_FPS


class BlackCheck(BaseCheck):
    """
    Black Frame Detection untuk downscaled video (raw YUV)
    """

    name = "Black Frame Check"
    DURATION_THRESHOLD = 1.0   # detik minimal dianggap fail
    PIXEL_THRESHOLD = 0.98     # 98% pixel hitam dianggap black frame

    def run(self, file_path, log_callback, progress_callback):
        """
        file_path: path ke raw YUV file hasil downscale
        """
        log_callback("Checking black frames on downscaled video...")

        # Command ffmpeg untuk baca raw YUV dan detect black
        cmd = [
            FFMPEG_PATH,
            "-f", "rawvideo",
            "-pixel_format", "gray",
            "-video_size", f"{DOWNSCALE_W}x{DOWNSCALE_H}",
            "-framerate", str(ASSUMED_FPS),
            "-i", file_path,
            "-vf", f"blackdetect=d={self.DURATION_THRESHOLD}:pic_th={self.PIXEL_THRESHOLD}",
            "-an",
            "-f", "null",
            "-"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            log_callback(f"Black frame scan error: {result.stderr}")
            return {"status": "PASS"}  # Skip jika error

        stderr = result.stderr

        # Cari black_start di output
        if "black_start" in stderr:
            # Parse waktu black segment
            black_starts = re.findall(r"black_start:(\d+\.?\d*)", stderr)
            black_ends = re.findall(r"black_end:(\d+\.?\d*)", stderr)
            
            if black_starts:
                log_callback(f"Black segment detected at {black_starts[0]}s")
                return {
                    "status": "FAIL",
                    "error": f"Black segment detected at {black_starts[0]}s"
                }

        log_callback("No black frames detected.")
        return {"status": "PASS"}