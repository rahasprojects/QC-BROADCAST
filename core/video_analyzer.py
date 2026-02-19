"""
Video Analyzer - Menganalisis video YUV dalam SATU KALI BACA
Menangani: Freeze Detection, Scratch Detection
"""

import numpy as np
import os
from config import (
    DOWNSCALE_W, DOWNSCALE_H, ASSUMED_FPS,
    MOTION_GATE, BLACK_GATE,
    FREEZE_MIN_FRAMES, FREEZE_MAX_FRAMES,
    SCRATCH_CONTRAST_THRESHOLD,
    MIN_SCRATCH_WIDTH, MAX_SCRATCH_WIDTH,
    MIN_SCRATCH_LENGTH_RATIO
)


class VideoAnalyzer:
    """
    Menganalisis video YUV dalam SATU KALI BACA
    Menghasilkan: freeze_events, scratch_events
    """
    
    def __init__(self, file_path):
        self.file_path = file_path
        self.width = DOWNSCALE_W
        self.height = DOWNSCALE_H
        self.fps = ASSUMED_FPS
        self.frame_size = self.width * self.height
        
        # Dapatkan total frames dari file size
        file_size = os.path.getsize(file_path)
        self.total_frames = file_size // self.frame_size if file_size > 0 else 0
        
        # Hasil analisis
        self.freeze_events = []      # list of timestamps (detik)
        self.scratch_events = []      # list of timestamps (detik)
        
        # Scratch thresholds
        self.contrast_threshold = SCRATCH_CONTRAST_THRESHOLD
        self.min_scratch_width = MIN_SCRATCH_WIDTH
        self.max_scratch_width = MAX_SCRATCH_WIDTH
        self.min_vertical_length = int(self.height * MIN_SCRATCH_LENGTH_RATIO)
        self.min_horizontal_length = int(self.width * MIN_SCRATCH_LENGTH_RATIO)
        
    def analyze(self, progress_callback=None):
        """
        Analisis video dalam SATU KALI BACA
        
        Args:
            progress_callback: function(frame_number, total_frames)
            
        Returns:
            tuple: (freeze_events, scratch_events)
        """
        
        if self.total_frames == 0:
            return [], []
        
        with open(self.file_path, 'rb') as f:
            prev_frame = None
            freeze_counter = 0
            frame_number = 0
            
            while True:
                raw = f.read(self.frame_size)
                if len(raw) < self.frame_size:
                    break
                
                # Konversi ke numpy array (grayscale)
                frame = np.frombuffer(raw, dtype=np.uint8).reshape(self.height, self.width)
                
                # =============================================
                # 1. FREEZE DETECTION
                # =============================================
                frame_mean = np.mean(frame)
                
                # Skip black frame
                if frame_mean < BLACK_GATE:
                    freeze_counter = 0
                elif prev_frame is not None:
                    # Hitung perbedaan dengan frame sebelumnya
                    diff = np.mean(np.abs(frame.astype(np.int16) - prev_frame.astype(np.int16)))
                    
                    if diff < MOTION_GATE:
                        freeze_counter += 1
                    else:
                        # Cek apakah freeze counter memenuhi kriteria
                        if FREEZE_MIN_FRAMES <= freeze_counter <= FREEZE_MAX_FRAMES:
                            # Hitung timestamp (ambil tengah-tengah freeze)
                            sec = (frame_number - freeze_counter//2) / self.fps
                            self.freeze_events.append(sec)
                        freeze_counter = 0
                
                # =============================================
                # 2. SCRATCH DETECTION
                # =============================================
                if self._has_scratch(frame):
                    sec = frame_number / self.fps
                    self.scratch_events.append(sec)
                
                # Update untuk frame berikutnya
                prev_frame = frame
                frame_number += 1
                
                # Progress callback
                if progress_callback and self.total_frames > 0:
                    progress_callback(int((frame_number / self.total_frames) * 100))
            
            # Cek tail freeze (freeze di akhir video)
            if FREEZE_MIN_FRAMES <= freeze_counter <= FREEZE_MAX_FRAMES:
                sec = (frame_number - freeze_counter//2) / self.fps
                self.freeze_events.append(sec)
        
        return self.freeze_events, self.scratch_events
    
    def _has_scratch(self, frame):
        """
        Deteksi scratch dalam satu frame
        
        Args:
            frame: numpy array (height, width) dengan nilai 0-255
            
        Returns:
            bool: True jika ada scratch
        """
        h, w = frame.shape
        
        # =============================================
        # DETEKSI GARIS VERTIKAL (per kolom)
        # =============================================
        for col in range(w - self.max_scratch_width + 1):
            for width in range(self.min_scratch_width, self.max_scratch_width + 1):
                if col + width > w:
                    continue
                
                # Rata-rata nilai kolom yang diduga scratch
                scratch_cols = frame[:, col:col+width].mean(axis=1)
                
                # Rata-rata background (kolom kiri dan kanan)
                left_bg = frame[:, max(0, col-2):col].mean() if col > 0 else None
                right_bg = frame[:, col+width:min(w, col+width+2)].mean() if col+width < w else None
                
                # Kombinasi background
                if left_bg is not None and right_bg is not None:
                    bg_mean = (left_bg + right_bg) / 2
                elif left_bg is not None:
                    bg_mean = left_bg
                elif right_bg is not None:
                    bg_mean = right_bg
                else:
                    continue
                
                # Hindari division by zero
                if bg_mean < 1:
                    bg_mean = 1
                
                # Hitung selisih relatif terhadap background
                diff_ratio = np.abs(scratch_cols - bg_mean) / bg_mean
                
                # Cek apakah ada segmen dengan panjang minimal
                if self._has_long_segment(diff_ratio > self.contrast_threshold, 
                                         self.min_vertical_length):
                    return True
        
        # =============================================
        # DETEKSI GARIS HORIZONTAL (per baris)
        # =============================================
        for row in range(h - self.max_scratch_width + 1):
            for height in range(self.min_scratch_width, self.max_scratch_width + 1):
                if row + height > h:
                    continue
                
                # Rata-rata nilai baris yang diduga scratch
                scratch_rows = frame[row:row+height, :].mean(axis=0)
                
                # Rata-rata background (baris atas dan bawah)
                top_bg = frame[max(0, row-2):row, :].mean() if row > 0 else None
                bottom_bg = frame[row+height:min(h, row+height+2), :].mean() if row+height < h else None
                
                if top_bg is not None and bottom_bg is not None:
                    bg_mean = (top_bg + bottom_bg) / 2
                elif top_bg is not None:
                    bg_mean = top_bg
                elif bottom_bg is not None:
                    bg_mean = bottom_bg
                else:
                    continue
                
                if bg_mean < 1:
                    bg_mean = 1
                
                diff_ratio = np.abs(scratch_rows - bg_mean) / bg_mean
                
                if self._has_long_segment(diff_ratio > self.contrast_threshold,
                                         self.min_horizontal_length):
                    return True
        
        return False
    
    def _has_long_segment(self, boolean_array, min_length):
        """
        Cek apakah ada segmen kontinu dengan panjang >= min_length
        
        Args:
            boolean_array: array of bool
            min_length: panjang minimal yang dianggap scratch
            
        Returns:
            bool: True jika ada segmen dengan panjang >= min_length
        """
        length = 0
        for val in boolean_array:
            if val:
                length += 1
                if length >= min_length:
                    return True
            else:
                length = 0
        return False
    
    def get_summary(self):
        """Dapatkan ringkasan hasil analisis"""
        return {
            'total_frames': self.total_frames,
            'freeze_count': len(self.freeze_events),
            'scratch_count': len(self.scratch_events),
            'freeze_events': self.freeze_events,
            'scratch_events': self.scratch_events
        }