import os

# =====================================================
# CONFIG
# =====================================================

WATCH_FOLDERS = [r"D:\test_vid"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_FOLDER = os.path.join(BASE_DIR, "reports")
os.makedirs(LOG_FOLDER, exist_ok=True)

BIN_FOLDER = os.path.join(BASE_DIR, "bin")

FFPROBE_PATH = os.path.join(BIN_FOLDER, "ffprobe.exe")
FFMPEG_PATH  = os.path.join(BIN_FOLDER, "ffmpeg.exe")

# MAX_WORKERS = max(1, os.cpu_count() - 1)  ini jumlah file yang dikerjakan bersaan, ini berdasarkan perhitungan otomatis
MAX_WORKERS = 2

# =====================================================
# THRESHOLDS FREEZE & DOWNSCALE
# =====================================================

FREEZE_MIN_FRAMES = 3
FREEZE_MAX_FRAMES = 8
MOTION_GATE = 0.8
BLACK_GATE = 10

DOWNSCALE_W = 640
DOWNSCALE_H = 360
ASSUMED_FPS = 25

COOLDOWN_SECONDS = 60

# =====================================================
# DOWNCSCALE CONFIG 
# =====================================================

TEMP_FOLDER = os.path.join(BASE_DIR, "temp")
os.makedirs(TEMP_FOLDER, exist_ok=True)

DELETE_TEMP = True

DOWNSCALE_FORMAT = "gray"
DOWNSCALE_PIX_FMT = "gray"

# =====================================================
# TRACKING CONFIG
# =====================================================

TRACKING_FILE = os.path.join(LOG_FOLDER, "processed_files.json")

# =====================================================
# SCRATCH DETECTION CONFIG - VERSI FINAL
# =====================================================

SCRATCH_CONTRAST_THRESHOLD = 0.5      # 50% lebih terang/gelap (lebih toleran)
MIN_SCRATCH_WIDTH = 2                  # minimal 2 pixel (hindari noise)
MAX_SCRATCH_WIDTH = 5                  # maksimal 5 pixel
MIN_SCRATCH_LENGTH_RATIO = 0.3        # minimal 30% dari frame