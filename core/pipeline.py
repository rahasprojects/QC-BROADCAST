import os
import time
import traceback

from utils.file_utils import wait_until_file_released
from utils.ffmpeg_utils import check_metadata
from utils.downscale_utils import downscale_video_with_progress, cleanup_temp_file
from utils.time_utils import sec_to_tc
from core.video_analyzer import VideoAnalyzer
from modules.checks.freeze_check import FreezeCheck
from modules.checks.scratch_check import ScratchCheck
from modules.checks.flicker_check import FlickerCheck
from modules.checks.scan_type_check import ScanTypeCheck
from modules.checks.black_check import BlackCheck
from modules.checks.silence_check import SilenceCheck
from modules.checks.peak_check import PeakCheck
from modules.checks.phase_check import PhaseCheck
from config import DELETE_TEMP


def qc_process_file(file_path, log_callback, progress_callback):
    """
    Proses QC untuk satu file MXF
    Semua check bersifat WARNING (tidak mengubah status final)
    """
    temp_file = None
    
    try:
        file_name = os.path.basename(file_path)
        folder = os.path.dirname(file_path)

        log_callback(f"Detected : {file_name}")
        log_callback(f"Folder   : {folder}")
        log_callback("Waiting file release...")

        wait_until_file_released(file_path)
        time.sleep(1)

        log_callback("Checking metadata...")
        valid, err = check_metadata(file_path)

        if not valid:
            return {
                "file": file_name,
                "status": "FAIL",  # Metadata FAIL tetap FAIL
                "freeze": [],
                "details": {},
                "error": err
            }

        log_callback("Metadata OK")
        
        # =====================================================
        # DOWNCSCALE VIDEO (DENGAN PROGRESS BAR)
        # =====================================================
        log_callback("Starting downscale process...")
        temp_file = downscale_video_with_progress(file_path, progress_callback)
        log_callback(f"Downscale complete: {os.path.basename(temp_file)}")
        
        # =====================================================
        # ANALISIS VIDEO SATU KALI (FREEZE + SCRATCH + FLICKER)
        # =====================================================
        log_callback("Analyzing video (freeze + scratch + flicker)...")
        analyzer = VideoAnalyzer(temp_file)        
        freeze_events, scratch_events, flicker_events = analyzer.analyze()

        # Konversi ke timecode untuk display
        freeze_tc = [sec_to_tc(x) for x in freeze_events]
        scratch_tc = [sec_to_tc(x) for x in scratch_events]
        
        # Tampilkan warning di log
        if freeze_events:
            log_callback(f"⚠️ FREEZE DETECTED @ {freeze_tc}")
        if scratch_events:
            log_callback(f"⚠️ SCRATCH DETECTED @ {scratch_tc}")
        if flicker_events:
            log_callback(f"⚠️ FLICKER DETECTED: {len(flicker_events)} segment(s)")
            for evt in flicker_events:
                log_callback(f"   {evt['start']}s - {evt['end']}s (dur: {evt['duration']}s, amp: {evt['amplitude']}, freq: {evt['frequency']}Hz)")
        
        # =====================================================
        # RUN QC CHECKS
        # =====================================================
        log_callback("Running QC checks...")

        # Video checks - PAKAI TEMP FILE
        video_checks = [
            FreezeCheck(),
            ScratchCheck(),
            FlickerCheck(),
            BlackCheck(),      # Masih pakai ffmpeg
        ]
        
        # Audio/Metadata checks - PAKAI FILE ASLI
        other_checks = [
            ScanTypeCheck(),   # metadata
            SilenceCheck(),    # audio
            PeakCheck(),       # audio
            PhaseCheck(),      # audio
        ]

        # Status final tetap PASS selama metadata valid (karena semua warning)
        final_status = "PASS"
        all_details = {}
        all_freeze = freeze_tc  # Langsung dari analyzer
        error_msg = ""

        # =============================================
        # UPDATE DETAILS DARI ANALYZER
        # =============================================
        all_details["Freeze Detection"] = {
            "freeze_frames": freeze_tc,
            "freeze_timestamps": freeze_events,
            "warning": True if freeze_events else False
        }
        
        all_details["Scratch Detection"] = {
            "scratch_frames": scratch_tc,
            "scratch_timestamps": scratch_events,
            "warning": True if scratch_events else False
        }
        
        all_details["Flicker Detection"] = {
            "flicker_events": flicker_events,
            "warning": True if flicker_events else False
        }
        
        # =============================================
        # JALANKAN VIDEO CHECKS LAINNYA (Black)
        # =============================================
        for check in video_checks:
            # Skip freeze, scratch, flicker karena sudah dari analyzer
            if check.name in ["Freeze Detection", "Scratch Detection", "Flicker Detection"]:
                continue
                
            log_callback(f"Running {check.name} on downscaled video...")
            result = check.run(temp_file, log_callback, lambda x: None)
            all_details[check.name] = result.get("details", {})
            
            # Black check juga warning (tidak ubah status)
            if result.get("details") and result["status"] == "FAIL":
                all_details[check.name]["warning"] = True

        # =============================================
        # JALANKAN AUDIO/METADATA CHECKS
        # =============================================
        for check in other_checks:
            log_callback(f"Running {check.name} on original file...")
            result = check.run(file_path, log_callback, lambda x: None)
            all_details[check.name] = result.get("details", {})
            
            # Audio checks juga warning (tidak ubah status)
            if result.get("details") and result["status"] == "FAIL":
                all_details[check.name]["warning"] = True

        # =============================================
        # RETURN HASIL (Status tetap PASS)
        # =============================================
        return {
            "file": file_name,
            "status": final_status,  # Selalu PASS selama metadata valid
            "freeze": all_freeze,
            "details": all_details,
            "error": error_msg
        }

    except Exception as e:
        log_callback(f"CRITICAL ERROR: {str(e)}")
        traceback.print_exc()
        return {
            "file": os.path.basename(file_path),
            "status": "FAIL",
            "freeze": [],
            "details": {},
            "error": str(e)
        }
    
    finally:
        # =====================================================
        # CLEANUP TEMP FILE
        # =====================================================
        if temp_file and DELETE_TEMP:
            cleanup_temp_file(temp_file)
            log_callback("Temporary file cleaned up")
            log_callback(f"✅ {file_name} FINISH QC")
            log_callback("══════════════════════════════════════════════════")