"""
Video Analyzer - Menganalisis video YUV dalam SATU KALI BACA
Menangani: Freeze Detection, Scratch Detection, Flicker Detection
Semua bersifat WARNING (tidak mengubah status final)
"""

import numpy as np
import os
from config import (
    DOWNSCALE_W, DOWNSCALE_H, ASSUMED_FPS,
    MOTION_GATE, BLACK_GATE,
    FREEZE_MIN_FRAMES, FREEZE_MAX_FRAMES,
    SCRATCH_CONTRAST_THRESHOLD,
    MIN_SCRATCH_WIDTH, MAX_SCRATCH_WIDTH,
    MIN_SCRATCH_LENGTH_RATIO,
    FLICKER_THRESHOLD, FLICKER_MIN_DURATION,
    FLICKER_MIN_AMPLITUDE, FLICKER_MIN_FREQUENCY
)


class VideoAnalyzer:
    """
    Menganalisis video YUV dalam SATU KALI BACA
    Menghasilkan: freeze_events, scratch_events, flicker_events
    Semua events bersifat warning (tidak mempengaruhi status final)
    """
    
    def __init__(self, file_path):
        """
        Inisialisasi VideoAnalyzer dengan file YUV hasil downscale
        
        Args:
            file_path: path ke file YUV (640x360 grayscale)
        """
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
        self.flicker_events = []      # list of dict {start, end, duration, amplitude, frequency}
        
        # Scratch thresholds
        self.contrast_threshold = SCRATCH_CONTRAST_THRESHOLD
        self.min_scratch_width = MIN_SCRATCH_WIDTH
        self.max_scratch_width = MAX_SCRATCH_WIDTH
        self.min_vertical_length = int(self.height * MIN_SCRATCH_LENGTH_RATIO)
        self.min_horizontal_length = int(self.width * MIN_SCRATCH_LENGTH_RATIO)
        
        # Flicker thresholds
        self.flicker_threshold = FLICKER_THRESHOLD
        self.flicker_min_duration = FLICKER_MIN_DURATION
        self.flicker_min_amplitude = FLICKER_MIN_AMPLITUDE
        self.flicker_min_frequency = FLICKER_MIN_FREQUENCY
        self.flicker_min_frames = int(self.flicker_min_duration * self.fps)
        
    def analyze(self, progress_callback=None):
        """
        Analisis video dalam SATU KALI BACA
        
        Args:
            progress_callback: function(frame_number, total_frames) untuk update progress
            
        Returns:
            tuple: (freeze_events, scratch_events, flicker_events)
        """
        
        if self.total_frames == 0:
            return [], [], []
        
        # Untuk flicker detection
        brightness_history = []  # Simpan brightness tiap frame
        frame_timestamps = []     # Simpan timestamp tiap frame
        
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
                
                # Hitung brightness rata-rata frame ini
                frame_mean = np.mean(frame)
                timestamp = frame_number / self.fps
                
                # Simpan untuk flicker detection
                brightness_history.append(frame_mean)
                frame_timestamps.append(timestamp)
                
                # =============================================
                # 1. FREEZE DETECTION (WARNING)
                # =============================================
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
                # 2. SCRATCH DETECTION (WARNING)
                # =============================================
                if self._has_scratch(frame):
                    self.scratch_events.append(timestamp)
                
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
        
        # =============================================
        # 3. FLICKER DETECTION (setelah semua frame terbaca)
        # =============================================
        self._detect_flicker(brightness_history, frame_timestamps)
        
        return self.freeze_events, self.scratch_events, self.flicker_events
    
    def _detect_flicker(self, brightness_history, timestamps):
        """
        Deteksi flicker dari history brightness
        Flicker = perubahan brightness cepat yang berulang
        
        Args:
            brightness_history: list of float (nilai brightness tiap frame)
            timestamps: list of float (timestamp tiap frame)
        """
        if len(brightness_history) < self.flicker_min_frames:
            return
        
        i = 0
        while i < len(brightness_history) - 1:
            start_idx = i
            flicker_count = 0
            changes = []
            
            # Cari segmen dengan perubahan cepat
            while i < len(brightness_history) - 1:
                # Hitung perubahan relatif
                if brightness_history[i] > 0:
                    change = abs(brightness_history[i+1] - brightness_history[i]) / brightness_history[i]
                else:
                    change = 0
                
                if change >= self.flicker_threshold:
                    flicker_count += 1
                    changes.append(change)
                    i += 1
                else:
                    break
            
            # Jika flicker_count cukup banyak dalam durasi tertentu
            if flicker_count >= self.flicker_min_frames:
                start_time = timestamps[start_idx]
                end_time = timestamps[i] if i < len(timestamps) else timestamps[-1]
                duration = end_time - start_time
                
                if duration >= self.flicker_min_duration:
                    # Hitung amplitude rata-rata
                    avg_amplitude = np.mean(changes) if changes else 0
                    
                    if avg_amplitude >= self.flicker_min_amplitude:
                        # Hitung frekuensi flicker (perubahan per detik)
                        frequency = flicker_count / duration if duration > 0 else 0
                        
                        if frequency >= self.flicker_min_frequency:
                            self.flicker_events.append({
                                "start": round(start_time, 2),
                                "end": round(end_time, 2),
                                "duration": round(duration, 2),
                                "amplitude": round(avg_amplitude, 2),
                                "frequency": round(frequency, 2)
                            })
            else:
                i += 1
    
    def _has_scratch(self, frame):
        """
        Deteksi scratch dalam satu frame
        Scratch = garis vertikal/horizontal putih/hitam
        
        Args:
            frame: numpy array (height, width) dengan nilai 0-255
            
        Returns:
            bool: True jika ada scratch
        """
        h, w = frame.shape
        
        # =============================================
        # Deteksi garis VERTIKAL
        # =============================================
        for col in range(w - self.max_scratch_width + 1):
            for width in range(self.min_scratch_width, self.max_scratch_width + 1):
                if col + width > w:
                    continue
                
                # Rata-rata nilai kolom yang diduga scratch
                scratch_cols = frame[:, col:col+width].mean(axis=1)
                
                # Background (kolom kiri dan kanan)
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
                
                # Hitung rasio perbedaan
                diff_ratio = np.abs(scratch_cols - bg_mean) / bg_mean
                
                # Cek apakah ada segmen vertikal dengan panjang minimal
                if self._has_long_segment(diff_ratio > self.contrast_threshold, 
                                         self.min_vertical_length):
                    return True
        
        # =============================================
        # Deteksi garis HORIZONTAL
        # =============================================
        for row in range(h - self.max_scratch_width + 1):
            for height in range(self.min_scratch_width, self.max_scratch_width + 1):
                if row + height > h:
                    continue
                
                # Rata-rata nilai baris yang diduga scratch
                scratch_rows = frame[row:row+height, :].mean(axis=0)
                
                # Background (baris atas dan bawah)
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
                
                # Cek apakah ada segmen horizontal dengan panjang minimal
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
        """
        Dapatkan ringkasan hasil analisis
        
        Returns:
            dict: ringkasan semua deteksi
        """
        return {
            'total_frames': self.total_frames,
            'duration_seconds': self.total_frames / self.fps if self.total_frames > 0 else 0,
            'freeze_count': len(self.freeze_events),
            'scratch_count': len(self.scratch_events),
            'flicker_count': len(self.flicker_events),
            'freeze_events': self.freeze_events,
            'scratch_events': self.scratch_events,
            'flicker_events': self.flicker_events
        }