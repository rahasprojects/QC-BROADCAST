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


# =====================================================
# FLICKER DETECTION CONFIG - TAMBAHKAN INI
# =====================================================

FLICKER_THRESHOLD = 0.3          # 30% perubahan brightness
FLICKER_MIN_DURATION = 2.0       # minimal 2 detik
FLICKER_MIN_AMPLITUDE = 0.3      # 30% amplitude dari rata-rata
FLICKER_ALWAYS_WARNING = True    # Selalu warning, bukan fail
FLICKER_MIN_FREQUENCY = 8        # minimal 8 perubahan per detik

# =====================================================
# FRAME DROP DETECTION CONFIG
# =====================================================

DROP_MOTION_THRESHOLD = 15.0       # Perbedaan motion yang mencurigakan
DROP_TIMESTAMP_GAP = 1.5            # 1.5x interval normal dianggap drop
DROP_VERIFY_SEGMENTS = True         # Verifikasi dengan ffprobe
DROP_MIN_GAP_FRAMES = 1              # Minimal 1 frame drop

# =====================================================
# ILLEGAL LUMINANCE DETECTION CONFIG
# =====================================================

ILLEGAL_LOWER_BOUND = 16           # Pixel < 16 = too dark
ILLEGAL_UPPER_BOUND = 235          # Pixel > 235 = too bright
ILLEGAL_PIXEL_THRESHOLD = 0.01     # 1% pixel illegal per frame dianggap warning
ILLEGAL_MIN_DURATION = 1           # Minimal 1 frame (langsung warning)
ILLEGAL_ALWAYS_WARNING = True      # Warning, bukan fail