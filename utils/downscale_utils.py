import os
import subprocess
import tempfile
import math
from config import FFMPEG_PATH, DOWNSCALE_W, DOWNSCALE_H, ASSUMED_FPS, TEMP_FOLDER

def downscale_video_with_progress(file_path, progress_callback):
    """
    Downscale video ke 640x360 grayscale dengan progress bar
    Returns: path ke file temporary hasil downscale
    """
    file_name = os.path.basename(file_path)
    base_name = os.path.splitext(file_name)[0]
    
    # Buat folder temp jika belum ada
    os.makedirs(TEMP_FOLDER, exist_ok=True)
    
    # File temporary output
    temp_file = os.path.join(TEMP_FOLDER, f"{base_name}_downscale.yuv")
    
    # Hapus jika sudah ada
    if os.path.exists(temp_file):
        os.remove(temp_file)
    
    # Dapatkan total frames untuk progress
    cmd_info = [
        FFMPEG_PATH,
        "-i", file_path,
        "-map", "0:v:0",
        "-f", "null",
        "-"
    ]
    
    result = subprocess.run(cmd_info, capture_output=True, text=True)
    
    # Parse duration dari stderr (cara kotor tapi jalan)
    duration = 0
    for line in result.stderr.split('\n'):
        if "Duration:" in line:
            time_parts = line.split("Duration:")[1].split(",")[0].strip().split(":")
            if len(time_parts) == 3:
                duration = int(time_parts[0]) * 3600 + int(time_parts[1]) * 60 + float(time_parts[2])
            break
    
    if duration == 0:
        # Fallback: asumsi 25fps dan coba estimate
        duration = 60  # default 1 menit
    
    total_frames = int(duration * ASSUMED_FPS)
    frames_processed = 0
    
    # Command ffmpeg untuk downscale
    cmd = [
        FFMPEG_PATH,
        "-i", file_path,
        "-vf", f"scale={DOWNSCALE_W}:{DOWNSCALE_H},format=gray",
        "-f", "rawvideo",
        "-pix_fmt", "gray",
        "-y",  # overwrite output
        temp_file
    ]
    
    # Jalankan ffmpeg dan baca progress dari stderr
    process = subprocess.Popen(
        cmd, 
        stderr=subprocess.PIPE, 
        stdout=subprocess.DEVNULL,
        universal_newlines=True
    )
    
    # Parse progress dari output ffmpeg
    for line in process.stderr:
        if "frame=" in line and "fps=" in line:
            # Extract frame number
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "frame=":
                    try:
                        frame_num = int(parts[i+1])
                        if total_frames > 0:
                            progress = min(100, int((frame_num / total_frames) * 100))
                            progress_callback(progress)
                    except:
                        pass
    
    process.wait()
    
    # Pastikan progress 100% di akhir
    progress_callback(100)
    
    return temp_file


def cleanup_temp_file(temp_file):
    """Hapus file temporary"""
    try:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    except:
        pass


def get_video_info(file_path):
    """Dapatkan info video seperti duration, fps, dll"""
    cmd = [
        FFMPEG_PATH,
        "-i", file_path,
        "-f", "null",
        "-"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    info = {
        "duration": 0,
        "bitrate": 0,
        "fps": ASSUMED_FPS
    }
    
    for line in result.stderr.split('\n'):
        if "Duration:" in line:
            time_parts = line.split("Duration:")[1].split(",")[0].strip().split(":")
            if len(time_parts) == 3:
                info["duration"] = int(time_parts[0]) * 3600 + int(time_parts[1]) * 60 + float(time_parts[2])
        if "fps" in line and "tb" in line:
            # Extract fps dari stream
            pass
    
    return info