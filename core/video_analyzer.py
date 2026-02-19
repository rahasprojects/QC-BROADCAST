"""

Video Analyzer - Menganalisis video YUV dalam SATU KALI BACA
Menangani: Freeze Detection, Scratch Detection, Flicker Detection, Frame Drop Detection, Illegal Luminance

"""

import numpy as np
import os
import subprocess
import json
from config import (
    DOWNSCALE_W, DOWNSCALE_H, ASSUMED_FPS,
    MOTION_GATE, BLACK_GATE,
    FREEZE_MIN_FRAMES, FREEZE_MAX_FRAMES,
    SCRATCH_CONTRAST_THRESHOLD,
    MIN_SCRATCH_WIDTH, MAX_SCRATCH_WIDTH,
    MIN_SCRATCH_LENGTH_RATIO,
    FLICKER_THRESHOLD, FLICKER_MIN_DURATION,
    FLICKER_MIN_AMPLITUDE, FLICKER_MIN_FREQUENCY,
    DROP_MOTION_THRESHOLD, DROP_TIMESTAMP_GAP,
    FFPROBE_PATH,
    ILLEGAL_LOWER_BOUND, ILLEGAL_UPPER_BOUND,
    ILLEGAL_PIXEL_THRESHOLD
)


class VideoAnalyzer:
    """
    Menganalisis video YUV dalam SATU KALI BACA
    Menghasilkan: freeze_events, scratch_events, flicker_events, drop_events, illegal_events
    Semua events bersifat warning (tidak mempengaruhi status final)
    """
    
    def __init__(self, file_path, original_file_path=None):
        self.file_path = file_path
        self.original_file_path = original_file_path or file_path
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
        self.drop_events = []          # list of dict {timestamp, dropped_frames, gap}
        self.illegal_events = []       # list of dict {timestamp, type, percentage}
        
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
        
        # Frame drop thresholds
        self.drop_motion_threshold = DROP_MOTION_THRESHOLD
        self.drop_timestamp_gap = DROP_TIMESTAMP_GAP
        self.drop_candidates = []      # list of frame numbers mencurigakan

        # Illegal luminance thresholds
        self.illegal_lower = ILLEGAL_LOWER_BOUND
        self.illegal_upper = ILLEGAL_UPPER_BOUND
        self.illegal_threshold = ILLEGAL_PIXEL_THRESHOLD
        
    def analyze(self, progress_callback=None):
        """
        Analisis video dalam SATU KALI BACA
        
        Args:
            progress_callback: function(percent) untuk update progress (0-100)
            
        Returns:
            tuple: (freeze_events, scratch_events, flicker_events, drop_events, illegal_events)
        """
        
        if self.total_frames == 0:
            return [], [], [], [], []
        
        # Untuk flicker detection
        brightness_history = []  # Simpan brightness tiap frame
        frame_timestamps = []     # Simpan timestamp tiap frame (estimasi)
        
        with open(self.file_path, 'rb') as f:
            prev_frame = None
            freeze_counter = 0
            frame_number = 0
            last_progress = 0
            
            while True:
                raw = f.read(self.frame_size)
                if len(raw) < self.frame_size:
                    break
                
                # Konversi ke numpy array (grayscale)
                frame = np.frombuffer(raw, dtype=np.uint8).reshape(self.height, self.width)
                
                # Hitung brightness rata-rata frame ini
                frame_mean = np.mean(frame)
                timestamp = frame_number / self.fps  # Estimasi timestamp
                
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
                
                # =============================================
                # 3. FRAME DROP DETECTION - TAHAP 1 (MOTION)
                # =============================================
                if prev_frame is not None:
                    diff = np.mean(np.abs(frame.astype(np.int16) - prev_frame.astype(np.int16)))
                    
                    # Jika perbedaan sangat besar, curiga ada drop
                    if diff > self.drop_motion_threshold:
                        self.drop_candidates.append(frame_number)
                
                # =============================================
                # 4. ILLEGAL LUMINANCE DETECTION
                # =============================================
                illegal_dark_pct, illegal_bright_pct = self._check_illegal_luminance(frame)

                if illegal_dark_pct > self.illegal_threshold:
                    self.illegal_events.append({
                        "timestamp": round(timestamp, 2),
                        "type": "too_dark",
                        "percentage": round(illegal_dark_pct, 4),
                        "below": self.illegal_lower
                    })

                if illegal_bright_pct > self.illegal_threshold:
                    self.illegal_events.append({
                        "timestamp": round(timestamp, 2),
                        "type": "too_bright",
                        "percentage": round(illegal_bright_pct, 4),
                        "above": self.illegal_upper
                    })
                
                # Update untuk frame berikutnya
                prev_frame = frame
                frame_number += 1
                
                # =============================================
                # PROGRESS CALLBACK - UPDATE SETIAP FRAME
                # =============================================
                if progress_callback and self.total_frames > 0:
                    progress = int((frame_number / self.total_frames) * 100)
                    # Update hanya jika berubah (kurangi frekuensi callback)
                    if progress != last_progress:
                        progress_callback(progress)
                        last_progress = progress
            
            # Cek tail freeze (freeze di akhir video)
            if FREEZE_MIN_FRAMES <= freeze_counter <= FREEZE_MAX_FRAMES:
                sec = (frame_number - freeze_counter//2) / self.fps
                self.freeze_events.append(sec)
        
        # =============================================
        # 5. FLICKER DETECTION (setelah semua frame terbaca)
        # =============================================
        self._detect_flicker(brightness_history, frame_timestamps)
        
        # =============================================
        # 6. FRAME DROP DETECTION - TAHAP 2 (VERIFIKASI TIMESTAMP)
        # =============================================
        if self.drop_candidates:
            self._verify_drop_candidates()
        
        # =============================================
        # PROGRESS 100% - SELESAI
        # =============================================
        if progress_callback:
            progress_callback(100)
        
        return self.freeze_events, self.scratch_events, self.flicker_events, self.drop_events, self.illegal_events
    
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
    
    def _verify_drop_candidates(self):
        """
        Verifikasi kandidat drop dengan ffprobe (timestamp)
        """
        # Ambil sample kandidat (maksimal 50 untuk efisiensi)
        candidates = self.drop_candidates[:50]
        
        # Dapatkan timestamp dari ffprobe
        timestamps = self._get_frame_timestamps()
        
        if not timestamps or len(timestamps) < 2:
            return
        
        interval_normal = 1.0 / self.fps
        
        for frame_num in candidates:
            if frame_num >= len(timestamps) - 1 or frame_num < 1:
                continue
            
            # Cek gap ke frame berikutnya
            ts_curr = timestamps[frame_num]
            ts_next = timestamps[frame_num + 1]
            
            gap = ts_next - ts_curr
            if gap > interval_normal * self.drop_timestamp_gap:
                # Ada drop setelah frame ini
                dropped_frames = round(gap / interval_normal) - 1
                if dropped_frames >= 1:  # Minimal 1 frame drop
                    self.drop_events.append({
                        "timestamp": round(ts_curr, 2),
                        "next_timestamp": round(ts_next, 2),
                        "gap": round(gap, 3),
                        "dropped_frames": int(dropped_frames),
                        "method": "timestamp"
                    })
                    continue
            
            # Cek gap dari frame sebelumnya
            ts_prev = timestamps[frame_num - 1]
            gap = ts_curr - ts_prev
            if gap > interval_normal * self.drop_timestamp_gap:
                dropped_frames = round(gap / interval_normal) - 1
                if dropped_frames >= 1:
                    self.drop_events.append({
                        "timestamp": round(ts_prev, 2),
                        "next_timestamp": round(ts_curr, 2),
                        "gap": round(gap, 3),
                        "dropped_frames": int(dropped_frames),
                        "method": "timestamp"
                    })
    
    def _get_frame_timestamps(self):
        """
        Ambil timestamp semua frame menggunakan ffprobe dari file asli
        """
        cmd = [
            FFPROBE_PATH,
            "-i", self.original_file_path,
            "-select_streams", "v:0",
            "-show_entries", "frame=pkt_pts_time",
            "-of", "json"
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            data = json.loads(result.stdout)
            
            timestamps = []
            for frame in data.get("frames", []):
                if "pkt_pts_time" in frame:
                    timestamps.append(float(frame["pkt_pts_time"]))
            
            # Jika jumlah timestamp tidak sesuai, gunakan estimasi
            if len(timestamps) != self.total_frames:
                return [i / self.fps for i in range(self.total_frames)]
            
            return timestamps
        except Exception as e:
            # Fallback: gunakan timestamp estimasi dari frame number
            return [i / self.fps for i in range(self.total_frames)]
    
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

    def _check_illegal_luminance(self, frame):
        """
        Cek persentase pixel illegal dalam frame
        
        Args:
            frame: numpy array (height, width) dengan nilai 0-255
            
        Returns:
            tuple: (dark_percentage, bright_percentage)
        """
        total_pixels = frame.size
        
        # Hitung pixel terlalu gelap (< lower bound)
        dark_pixels = np.sum(frame < self.illegal_lower)
        dark_percentage = dark_pixels / total_pixels if total_pixels > 0 else 0
        
        # Hitung pixel terlalu terang (> upper bound)
        bright_pixels = np.sum(frame > self.illegal_upper)
        bright_percentage = bright_pixels / total_pixels if total_pixels > 0 else 0
        
        return dark_percentage, bright_percentage
    
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
            'drop_count': len(self.drop_events),
            'illegal_count': len(self.illegal_events),
            'freeze_events': self.freeze_events,
            'scratch_events': self.scratch_events,
            'flicker_events': self.flicker_events,
            'drop_events': self.drop_events,
            'illegal_events': self.illegal_events
        }