"""
Flicker Detection Check - Menggunakan hasil dari VideoAnalyzer
"""

from .base_check import BaseCheck


class FlickerCheck(BaseCheck):
    """
    Flicker Detection Check
    Mendeteksi perubahan brightness cepat yang berulang
    Bersifat WARNING (tidak mengubah status ke FAIL)
    """

    name = "Flicker Detection"

    def run(self, file_path, log_callback, progress_callback):
        """
        file_path: path ke raw YUV file
        Flicker sudah dideteksi oleh VideoAnalyzer di pipeline
        Check ini hanya sebagai wrapper
        """
        log_callback("Flicker detection check ready...")
        
        # Return PASS dulu, nanti pipeline update berdasarkan analyzer
        return {
            "status": "PASS",
            "details": {
                "flicker_events": [],
                "warning": True
            },
            "error": ""
        }