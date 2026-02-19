from utils.ffmpeg_utils import resolve_ffprobe
import subprocess
import json


FFPROBE = resolve_ffprobe()


def scan_type_check(file_path, logger):
    logger.log("Checking scan type (progressive/interlace)...")

    cmd = [
        FFPROBE,
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        file_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return False, "FFPROBE ERROR"

    data = json.loads(result.stdout)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    if not video:
        return False, "No video stream"

    field_order = video.get("field_order", "").lower()

    if field_order in ("tt", "bb", "tb", "bt"):
        return False, "Interlaced content detected"

    return True, ""
