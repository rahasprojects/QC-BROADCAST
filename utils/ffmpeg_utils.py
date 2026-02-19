import subprocess
import json
from config import FFPROBE_PATH


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
        video_stream = next(
            (s for s in data["streams"] if s["codec_type"] == "video"),
            None
        )

        if not video_stream:
            return False, "No video stream"

        if video_stream.get("width") != 1920 or video_stream.get("height") != 1080:
            return False, "Resolution not 1920x1080"

        return True, ""

    except Exception as e:
        return False, str(e)


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
