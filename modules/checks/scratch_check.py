"""
Scratch Detection Check - Menggunakan hasil dari VideoAnalyzer
"""

from .base_check import BaseCheck
from utils.time_utils import sec_to_tc


class ScratchCheck(BaseCheck):
    """
    Scratch Detection Check
    Mendeteksi garis vertikal/horizontal putih/hitam
    """
    
    name = "Scratch Detection"
    
    def run(self, file_path, log_callback, progress_callback):
        """
        file_path: path ke raw YUV file
        TAPI scratch sudah dideteksi oleh VideoAnalyzer di pipeline
        Check ini hanya sebagai wrapper, hasil akan diisi oleh pipeline
        """
        log_callback("Scratch detection check ready...")
        
        # Hasil akan diisi oleh pipeline berdasarkan VideoAnalyzer
        return {
            "status": "PASS",  # Akan di-update pipeline
            "details": {
                "scratch_frames": []  # Akan diisi pipeline
            },
            "error": ""
        }