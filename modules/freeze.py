import subprocess
import numpy as np
from config import FFMPEG_PATH, DOWNSCALE_W, DOWNSCALE_H, ASSUMED_FPS, MOTION_GATE, BLACK_GATE, FREEZE_MIN_FRAMES, FREEZE_MAX_FRAMES


def detect_freeze(file_path, progress_callback=None, is_raw=False, width=DOWNSCALE_W, height=DOWNSCALE_H, fps=ASSUMED_FPS):
    """
    Detect freeze frames in a video file.
    is_raw: True jika file_path adalah raw YUV, False jika file video biasa
    """
    
    if is_raw:
        # Untuk raw YUV file
        frame_size = width * height
        
        # Baca langsung dari file raw
        cmd = [
            FFMPEG_PATH,
            "-f", "rawvideo",
            "-pixel_format", "gray",
            "-video_size", f"{width}x{height}",
            "-framerate", str(fps),
            "-i", file_path,
            "-f", "rawvideo",
            "-pix_fmt", "gray",
            "-"
        ]
        
        # Dapatkan total frames dari file size
        import os
        file_size = os.path.getsize(file_path)
        total_frames = file_size // frame_size
        
    else:
        # Untuk file video biasa (seperti sebelumnya)
        # Get video duration
        cmd_duration = [
            FFMPEG_PATH,
            "-i", file_path,
            "-f", "null",
            "-"
        ]
        result = subprocess.run(cmd_duration, capture_output=True, text=True)
        
        # Parse duration
        duration = 0
        for line in result.stderr.split('\n'):
            if "Duration:" in line:
                time_parts = line.split("Duration:")[1].split(",")[0].strip().split(":")
                if len(time_parts) == 3:
                    duration = int(time_parts[0]) * 3600 + int(time_parts[1]) * 60 + float(time_parts[2])
                break
        
        total_frames = int(duration * fps)
        
        # Command untuk baca video biasa
        cmd = [
            FFMPEG_PATH,
            "-loglevel", "quiet",
            "-nostats",
            "-i", file_path,
            "-vf", f"yadif=0:-1:0,scale={width}:{height}",
            "-f", "rawvideo",
            "-pix_fmt", "gray",
            "-"
        ]

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    frame_size = width * height
    prev_frame = None
    freeze_counter = 0
    frame_number = 0
    freeze_events = []

    while True:
        raw = process.stdout.read(frame_size)
        if len(raw) < frame_size:
            break

        frame = np.frombuffer(raw, dtype=np.uint8)

        # Skip fade-to-black / near-black
        if np.mean(frame) < BLACK_GATE:
            freeze_counter = 0
            prev_frame = frame
            frame_number += 1
            if progress_callback and total_frames > 0:
                progress_callback(int((frame_number / total_frames) * 100))
            continue

        if prev_frame is not None:
            diff = np.mean(np.abs(frame - prev_frame))

            # Motion gate
            if diff < MOTION_GATE:
                freeze_counter += 1
            else:
                # Check limit 2-6 frames
                if FREEZE_MIN_FRAMES <= freeze_counter <= FREEZE_MAX_FRAMES:
                    sec = frame_number / fps
                    freeze_events.append(sec)
                freeze_counter = 0

        prev_frame = frame
        frame_number += 1

        if progress_callback and total_frames > 0:
            progress_callback(int((frame_number / total_frames) * 100))

    # Tail check
    if FREEZE_MIN_FRAMES <= freeze_counter <= FREEZE_MAX_FRAMES:
        sec = frame_number / fps
        freeze_events.append(sec)

    process.stdout.close()
    process.wait()
    
    if progress_callback:
        progress_callback(100)

    return freeze_events