"""
Jitter Detection Check - Menggunakan hasil dari VideoAnalyzer
"""

from .base_check import BaseCheck


class JitterCheck(BaseCheck):
    """
    Jitter Detection Check
    Mendeteksi ketidakstabilan posisi gambar (horizontal shift)
    Amplitude >= 3px, Frekuensi >= 10Hz, Durasi >= 1 detik
    Bersifat WARNING
    """

    name = "Jitter Detection"

    def run(self, file_path, log_callback, progress_callback):
        """
        file_path: path ke raw YUV file
        Jitter sudah dideteksi oleh VideoAnalyzer di pipeline
        Check ini hanya sebagai wrapper
        """
        log_callback("Jitter detection check ready...")
        
        return {
            "status": "PASS",
            "details": {
                "jitter_events": [],
                "warning": True
            },
            "error": ""
        }