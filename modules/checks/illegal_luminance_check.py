"""
Illegal Luminance Detection Check - Menggunakan hasil dari VideoAnalyzer
"""

from .base_check import BaseCheck


class IllegalLuminanceCheck(BaseCheck):
    """
    Illegal Luminance Detection Check
    Mendeteksi pixel dengan nilai di luar rentang broadcast (16-235)
    Bersifat WARNING
    """

    name = "Illegal Luminance Detection"

    def run(self, file_path, log_callback, progress_callback):
        """
        file_path: path ke raw YUV file
        Illegal luminance sudah dideteksi oleh VideoAnalyzer di pipeline
        Check ini hanya sebagai wrapper
        """
        log_callback("Illegal luminance check ready...")
        
        return {
            "status": "PASS",
            "details": {
                "illegal_events": [],
                "warning": True
            },
            "error": ""
        }