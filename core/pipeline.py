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
from modules.checks.frame_drop_check import FrameDropCheck
from modules.checks.scan_type_check import ScanTypeCheck
from modules.checks.black_check import BlackCheck
from modules.checks.silence_check import SilenceCheck
from modules.checks.peak_check import PeakCheck
from modules.checks.phase_check import PhaseCheck
from modules.checks.illegal_luminance_check import IllegalLuminanceCheck
from config import DELETE_TEMP


def qc_process_file(file_path, log_callback, progress_callback):
    """
    Proses QC untuk satu file MXF
    Status:
    - PASS: Tidak ada masalah sama sekali
    - WARNING: Ada warning dari salah satu check (freeze, scratch, flicker, drop, dll)
    - FAIL: Metadata error atau error kritis
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
            log_callback(f"❌ METADATA ERROR: {err}")
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
        # ANALISIS VIDEO SATU KALI (DENGAN PROGRESS BAR)
        # =====================================================
        log_callback("Analyzing video (freeze + scratch + flicker + frame drop + illegal luminance)...")

        # Buat wrapper untuk progress analyzing
        def analyzing_progress(percent):
            progress_callback(percent)  # Pakai progress bar yang sama

        analyzer = VideoAnalyzer(temp_file, file_path)  # Pass file asli untuk timestamp
        freeze_events, scratch_events, flicker_events, drop_events, illegal_events = analyzer.analyze(analyzing_progress)

        # Konversi ke timecode untuk display
        freeze_tc = [sec_to_tc(x) for x in freeze_events]
        scratch_tc = [sec_to_tc(x) for x in scratch_events]
        
        # =====================================================
        # TENTUKAN STATUS AWAL DAN KUMPULKAN WARNING
        # =====================================================
        has_warning = False
        error_msg = ""

        # Tampilkan warning di log dan tandai has_warning
        if freeze_events:
            has_warning = True
            log_callback(f"⚠️ FREEZE DETECTED @ {freeze_tc}")
            
        if scratch_events:
            has_warning = True
            log_callback(f"⚠️ SCRATCH DETECTED @ {scratch_tc}")
            
        if flicker_events:
            has_warning = True
            log_callback(f"⚠️ FLICKER DETECTED: {len(flicker_events)} segment(s)")
            for evt in flicker_events:
                log_callback(f"   {evt['start']}s - {evt['end']}s (dur: {evt['duration']}s, amp: {evt['amplitude']}, freq: {evt['frequency']}Hz)")
                
        if drop_events:
            has_warning = True
            log_callback(f"⚠️ FRAME DROP DETECTED: {len(drop_events)} kejadian")
            for evt in drop_events[:5]:  # Tampilkan maksimal 5
                log_callback(f"   @{evt['timestamp']}s: {evt['dropped_frames']} frame drop")
        
        if illegal_events:
            has_warning = True
            log_callback(f"⚠️ ILLEGAL LUMINANCE DETECTED: {len(illegal_events)} frame(s)")
            
            # Kelompokkan berdasarkan tipe
            dark_frames = [e for e in illegal_events if e["type"] == "too_dark"]
            bright_frames = [e for e in illegal_events if e["type"] == "too_bright"]
            
            if dark_frames:
                log_callback(f"   Too dark: {len(dark_frames)} frame(s)")
                for evt in dark_frames[:3]:  # Tampilkan max 3
                    log_callback(f"     @{evt['timestamp']}s: {evt['percentage']*100:.1f}% pixel < {evt['below']}")
            
            if bright_frames:
                log_callback(f"   Too bright: {len(bright_frames)} frame(s)")
                for evt in bright_frames[:3]:  # Tampilkan max 3
                    log_callback(f"     @{evt['timestamp']}s: {evt['percentage']*100:.1f}% pixel > {evt['above']}")
        
        # =====================================================
        # RUN QC CHECKS
        # =====================================================
        log_callback("Running QC checks...")

        # Video checks - PAKAI TEMP FILE
        video_checks = [
            FreezeCheck(),
            ScratchCheck(),
            FlickerCheck(),
            FrameDropCheck(),
            IllegalLuminanceCheck(),
            BlackCheck(),      # Masih pakai ffmpeg
        ]
        
        # Audio/Metadata checks - PAKAI FILE ASLI
        other_checks = [
            ScanTypeCheck(),   # metadata
            SilenceCheck(),    # audio
            PeakCheck(),       # audio
            PhaseCheck(),      # audio
        ]

        all_details = {}
        all_freeze = freeze_tc  # Langsung dari analyzer

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
        
        all_details["Frame Drop Detection"] = {
            "drop_events": drop_events,
            "warning": True if drop_events else False
        }
        
        all_details["Illegal Luminance Detection"] = {
        "illegal_events": illegal_events,
        "dark_frames": len([e for e in illegal_events if e["type"] == "too_dark"]),
        "bright_frames": len([e for e in illegal_events if e["type"] == "too_bright"]),
        "warning": True if illegal_events else False
        }

        # =============================================
        # JALANKAN VIDEO CHECKS LAINNYA (Black)
        # =============================================
        for check in video_checks:
            # Skip freeze, scratch, flicker, drop karena sudah dari analyzer
            if check.name in ["Freeze Detection", "Scratch Detection", "Flicker Detection", 
                  "Frame Drop Detection", "Illegal Luminance Detection"]:
                continue
                
            log_callback(f"Running {check.name} on downscaled video...")
            result = check.run(temp_file, log_callback, lambda x: None)
            all_details[check.name] = result.get("details", {})
            
            # Cek apakah check ini menghasilkan warning
            if result.get("details") and result["status"] == "FAIL":
                all_details[check.name]["warning"] = True
                has_warning = True
                if not error_msg:
                    error_msg = f"{check.name} issue detected"

        # =============================================
        # JALANKAN AUDIO/METADATA CHECKS
        # =============================================
        for check in other_checks:
            log_callback(f"Running {check.name} on original file...")
            result = check.run(file_path, log_callback, lambda x: None)
            all_details[check.name] = result.get("details", {})
            
            # Cek apakah check ini menghasilkan warning
            if result.get("details") and result["status"] == "FAIL":
                all_details[check.name]["warning"] = True
                has_warning = True
                if not error_msg:
                    error_msg = f"{check.name} issue detected"

        # =============================================
        # TENTUKAN STATUS FINAL (PASS, WARNING, FAIL)
        # =============================================
        
        # Tentukan final_status
        if error_msg and ("metadata" in error_msg.lower() or "corrupt" in error_msg.lower()):
            final_status = "FAIL"  # Metadata error atau corrupt = FAIL
        elif has_warning:
            final_status = "WARNING"  # Ada warning dari check manapun
        else:
            final_status = "PASS"  # Bersih semua

        # =============================================
        # RETURN HASIL
        # =============================================
        return {
            "file": file_name,
            "status": final_status,
            "freeze": all_freeze,
            "details": all_details,
            "error": error_msg
        }

    except Exception as e:
        log_callback(f"❌ CRITICAL ERROR: {str(e)}")
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
            log_callback("══════════════════════════════════════════════════")