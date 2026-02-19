"""
Video Analyzer - Menganalisis video YUV dalam SATU KALI BACA
Menangani: 
- Freeze Detection
- Scratch Detection
- Flicker Detection (umum)
- Frame Drop Detection
- Illegal Luminance Detection
- Jitter Detection
- LED Flicker Detection (khusus, via FFT)

Semua bersifat WARNING (tidak mengubah status final)
"""

import numpy as np
import numpy.fft as fft
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
    ILLEGAL_PIXEL_THRESHOLD,
    JITTER_AMPLITUDE_THRESHOLD, JITTER_FREQUENCY_THRESHOLD,
    JITTER_MIN_DURATION, JITTER_ROI_SIZE,
    JITTER_SEARCH_RANGE,
    LED_FLICKER_FREQS_50HZ, LED_FLICKER_FREQS_60HZ,
    LED_FLICKER_AMPLITUDE_THRESHOLD, LED_FLICKER_MIN_DURATION,
    LED_FLICKER_DETECT_BOTH, LED_FLICKER_POWER_RATIO
)


class VideoAnalyzer:
    """
    Menganalisis video YUV dalam SATU KALI BACA
    Menghasilkan: freeze_events, scratch_events, flicker_events, drop_events, 
                 illegal_events, jitter_events, led_flicker_events
    Semua events bersifat warning (tidak mempengaruhi status final)
    """
    
    def __init__(self, file_path, original_file_path=None):
        """
        Inisialisasi VideoAnalyzer dengan file YUV hasil downscale
        
        Args:
            file_path: path ke file YUV (640x360 grayscale)
            original_file_path: path ke file asli (untuk ffprobe timestamp)
        """
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
        self.jitter_events = []        # list of dict {start, end, duration, max_amplitude, frequency}
        self.led_flicker_events = []   # list of dict {start, end, duration, frequency, power_ratio, type}
        
        # Scratch thresholds
        self.contrast_threshold = SCRATCH_CONTRAST_THRESHOLD
        self.min_scratch_width = MIN_SCRATCH_WIDTH
        self.max_scratch_width = MAX_SCRATCH_WIDTH
        self.min_vertical_length = int(self.height * MIN_SCRATCH_LENGTH_RATIO)
        self.min_horizontal_length = int(self.width * MIN_SCRATCH_LENGTH_RATIO)
        
        # Flicker thresholds (umum)
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
        
        # Jitter thresholds
        self.jitter_amplitude = JITTER_AMPLITUDE_THRESHOLD
        self.jitter_frequency = JITTER_FREQUENCY_THRESHOLD
        self.jitter_min_duration = JITTER_MIN_DURATION
        self.jitter_roi_size = JITTER_ROI_SIZE
        self.jitter_search_range = JITTER_SEARCH_RANGE
        self.shift_history = []           # list of (timestamp, shift_x)
        self.reference_roi = None         # ROI dari frame pertama
        self.reference_roi_pos = None     # Posisi ROI di frame pertama
        
        # LED Flicker thresholds
        self.led_freqs_50hz = LED_FLICKER_FREQS_50HZ
        self.led_freqs_60hz = LED_FLICKER_FREQS_60HZ
        self.led_amplitude_threshold = LED_FLICKER_AMPLITUDE_THRESHOLD
        self.led_min_duration = LED_FLICKER_MIN_DURATION
        self.led_detect_both = LED_FLICKER_DETECT_BOTH
        self.led_power_ratio = LED_FLICKER_POWER_RATIO
        
    def analyze(self, progress_callback=None):
        """
        Analisis video dalam SATU KALI BACA
        
        Args:
            progress_callback: function(percent) untuk update progress (0-100)
            
        Returns:
            tuple: (freeze_events, scratch_events, flicker_events, drop_events, 
                    illegal_events, jitter_events, led_flicker_events)
        """
        
        if self.total_frames == 0:
            return [], [], [], [], [], [], []
        
        # Untuk flicker detection (umum) dan LED flicker
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
                
                # Simpan untuk flicker detection (umum) dan LED flicker
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
                
                # =============================================
                # 5. JITTER DETECTION
                # =============================================
                if frame_number == 0:
                    # Frame pertama: pilih ROI
                    self.reference_roi, self.reference_roi_pos = self._select_roi(frame)
                elif self.reference_roi is not None:
                    # Frame berikutnya: cross-correlation
                    shift_x, shift_y, confidence = self._cross_correlate(
                        frame, self.reference_roi, self.reference_roi_pos
                    )
                    # Hanya simpan jika confident
                    if confidence > 0.7:  # Threshold confidence
                        self.shift_history.append((timestamp, shift_x))
                
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
        # 6. FLICKER DETECTION (umum) - setelah semua frame terbaca
        # =============================================
        self._detect_flicker(brightness_history, frame_timestamps)
        
        # =============================================
        # 7. FRAME DROP DETECTION - TAHAP 2 (VERIFIKASI TIMESTAMP)
        # =============================================
        if self.drop_candidates:
            self._verify_drop_candidates()
        
        # =============================================
        # 8. JITTER DETECTION - ANALISIS
        # =============================================
        self._detect_jitter()
        
        # =============================================
        # 9. LED FLICKER DETECTION (khusus, via FFT)
        # =============================================
        if len(brightness_history) >= int(self.led_min_duration * self.fps):
            self.led_flicker_events = self._detect_led_flicker(brightness_history, frame_timestamps)
        
        # =============================================
        # PROGRESS 100% - SELESAI
        # =============================================
        if progress_callback:
            progress_callback(100)
        
        return (self.freeze_events, self.scratch_events, self.flicker_events, 
                self.drop_events, self.illegal_events, self.jitter_events,
                self.led_flicker_events)
    
    def _select_roi(self, frame):
        """
        Pilih region of interest (ROI) dengan tekstur terkuat
        
        Args:
            frame: numpy array (height, width) dengan nilai 0-255
            
        Returns:
            tuple: (roi, position) dimana position = (x, y)
        """
        h, w = frame.shape
        best_score = -1
        best_roi = None
        best_pos = None
        
        # Coba beberapa posisi, pilih yang variance tertinggi
        step = self.jitter_roi_size // 2
        for y in range(0, h - self.jitter_roi_size, step):
            for x in range(0, w - self.jitter_roi_size, step):
                roi = frame[y:y+self.jitter_roi_size, x:x+self.jitter_roi_size]
                variance = np.var(roi)
                if variance > best_score:
                    best_score = variance
                    best_roi = roi.copy()
                    best_pos = (x, y)
        
        return best_roi, best_pos
    
    def _cross_correlate(self, frame, ref_roi, ref_pos):
        """
        Cari posisi ROI di frame baru menggunakan cross-correlation
        
        Args:
            frame: numpy array (height, width)
            ref_roi: numpy array (roi_size, roi_size) referensi
            ref_pos: tuple (x, y) posisi ROI di frame referensi
            
        Returns:
            tuple: (shift_x, shift_y, confidence)
        """
        h, w = frame.shape
        roi_h, roi_w = ref_roi.shape
        ref_x, ref_y = ref_pos
        
        # Batasi area pencarian
        x_min = max(0, ref_x - self.jitter_search_range)
        x_max = min(w - roi_w, ref_x + self.jitter_search_range)
        y_min = max(0, ref_y - self.jitter_search_range)
        y_max = min(h - roi_h, ref_y + self.jitter_search_range)
        
        best_corr = -1
        best_x, best_y = ref_x, ref_y
        
        # Normalisasi referensi ROI
        ref_mean = np.mean(ref_roi)
        ref_std = np.std(ref_roi) + 1e-6
        ref_norm = (ref_roi - ref_mean) / ref_std
        
        # Lakukan pencarian sederhana
        for y in range(y_min, y_max):
            for x in range(x_min, x_max):
                roi = frame[y:y+roi_h, x:x+roi_w]
                
                # Normalisasi ROI
                roi_mean = np.mean(roi)
                roi_std = np.std(roi) + 1e-6
                roi_norm = (roi - roi_mean) / roi_std
                
                # Hitung cross-correlation
                corr = np.sum(roi_norm * ref_norm) / (roi_h * roi_w)
                
                if corr > best_corr:
                    best_corr = corr
                    best_x, best_y = x, y
        
        shift_x = best_x - ref_x
        shift_y = best_y - ref_y
        
        return shift_x, shift_y, best_corr
    
    def _detect_jitter(self):
        """
        Analisis history pergeseran untuk mendeteksi jitter
        Jitter = pergeseran horizontal dengan amplitude >= threshold,
                frekuensi >= threshold, durasi >= threshold
        """
        if len(self.shift_history) < int(self.jitter_min_duration * self.fps):
            return
        
        timestamps = [t for t, _ in self.shift_history]
        shifts = [s for _, s in self.shift_history]
        
        i = 0
        while i < len(shifts) - 1:
            start_idx = i
            jitter_count = 0
            changes = []
            directions = []
            prev_shift = shifts[i]
            
            # Cari segmen dengan perubahan arah
            while i < len(shifts) - 1:
                current_shift = shifts[i + 1]
                
                # Hitung perubahan
                if current_shift != prev_shift:
                    change = abs(current_shift - prev_shift)
                    if change > 0:
                        jitter_count += 1
                        changes.append(change)
                        directions.append(np.sign(current_shift - prev_shift))
                        i += 1
                        prev_shift = current_shift
                    else:
                        break
                else:
                    i += 1
                    prev_shift = current_shift
            
            # Analisis segmen
            if jitter_count >= int(self.jitter_frequency * self.jitter_min_duration):
                start_time = timestamps[start_idx]
                end_time = timestamps[i] if i < len(timestamps) else timestamps[-1]
                duration = end_time - start_time
                
                if duration >= self.jitter_min_duration:
                    # Hitung amplitude maksimum
                    max_amplitude = max(changes) if changes else 0
                    
                    if max_amplitude >= self.jitter_amplitude:
                        # Hitung frekuensi aktual
                        frequency = jitter_count / duration if duration > 0 else 0
                        
                        if frequency >= self.jitter_frequency:
                            self.jitter_events.append({
                                "start": round(start_time, 2),
                                "end": round(end_time, 2),
                                "duration": round(duration, 2),
                                "max_amplitude": int(max_amplitude),
                                "frequency": round(frequency, 2),
                                "direction": "horizontal"
                            })
            else:
                i += 1
    
    def _detect_flicker(self, brightness_history, timestamps):
        """
        Deteksi flicker UMUM dari history brightness
        Flicker = perubahan brightness cepat yang berulang (tidak spesifik frekuensi)
        
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
    
    def _detect_led_flicker(self, brightness_history, timestamps):
        """
        Deteksi LED FLICKER (khusus) menggunakan FFT
        Mencari frekuensi spesifik: 50Hz, 100Hz, 60Hz, 120Hz
        
        Args:
            brightness_history: list of float (brightness per frame)
            timestamps: list of float (timestamp per frame)
            
        Returns:
            list: led_flicker_events
        """
        if len(brightness_history) < int(self.led_min_duration * self.fps):
            return []
        
        events = []
        
        # Bagi video menjadi segmen-segmen dengan overlap
        segment_duration = self.led_min_duration
        segment_frames = int(segment_duration * self.fps)
        step_frames = segment_frames // 2  # 50% overlap
        
        for start_idx in range(0, len(brightness_history) - segment_frames, step_frames):
            end_idx = start_idx + segment_frames
            segment = brightness_history[start_idx:end_idx]
            
            # FFT untuk segmen ini
            freqs, power = self._compute_fft(segment)
            
            if len(freqs) == 0:
                continue
            
            # Normalisasi power
            total_power = np.sum(power)
            if total_power == 0:
                continue
            
            start_time = timestamps[start_idx]
            end_time = timestamps[end_idx - 1] if end_idx - 1 < len(timestamps) else timestamps[-1]
            
            # Cek frekuensi 50Hz dan 100Hz
            for freq_target in self.led_freqs_50hz:
                # Cari frekuensi terdekat
                idx = np.argmin(np.abs(freqs - freq_target))
                if np.abs(freqs[idx] - freq_target) < 2:  # Tolerance ±2Hz
                    power_ratio = power[idx] / total_power
                    
                    if power_ratio > self.led_power_ratio:
                        events.append({
                            "start": round(start_time, 2),
                            "end": round(end_time, 2),
                            "duration": round(end_time - start_time, 2),
                            "frequency": freq_target,
                            "power_ratio": round(power_ratio, 3),
                            "type": "50hz_system"
                        })
            
            # Cek frekuensi 60Hz dan 120Hz
            if self.led_detect_both:
                for freq_target in self.led_freqs_60hz:
                    idx = np.argmin(np.abs(freqs - freq_target))
                    if np.abs(freqs[idx] - freq_target) < 2:
                        power_ratio = power[idx] / total_power
                        
                        if power_ratio > self.led_power_ratio:
                            events.append({
                                "start": round(start_time, 2),
                                "end": round(end_time, 2),
                                "duration": round(end_time - start_time, 2),
                                "frequency": freq_target,
                                "power_ratio": round(power_ratio, 3),
                                "type": "60hz_system"
                            })
        
        # Merge events yang berdekatan
        merged_events = self._merge_led_events(events)
        
        return merged_events
    
    def _compute_fft(self, signal_data):
        """
        Hitung FFT dari sinyal brightness
        
        Args:
            signal_data: list of float (brightness values)
            
        Returns:
            tuple: (frequencies, power_spectrum)
        """
        n = len(signal_data)
        if n < 2 * self.fps:  # Minimal 2 detik untuk resolusi frekuensi cukup
            return [], []
        
        # Detrend (hilangkan DC offset)
        signal = np.array(signal_data)
        signal = signal - np.mean(signal)
        
        # Windowing (Hann window untuk kurangi spectral leakage)
        window = np.hanning(n)
        signal_windowed = signal * window
        
        # FFT
        fft_result = fft.fft(signal_windowed)
        power = np.abs(fft_result[:n//2]) ** 2
        
        # Frekuensi
        freqs = fft.fftfreq(n, 1/self.fps)[:n//2]
        
        return freqs, power
    
    def _merge_led_events(self, events):
        """
        Gabungkan event LED flicker yang berdekatan
        
        Args:
            events: list of dict
            
        Returns:
            list: merged events
        """
        if not events:
            return []
        
        # Urutkan berdasarkan start time
        events.sort(key=lambda x: x["start"])
        
        merged = []
        current = events[0].copy()
        
        for next_event in events[1:]:
            # Jika frekuensi sama dan gap < 0.5 detik, merge
            if (next_event["frequency"] == current["frequency"] and 
                next_event["start"] - current["end"] < 0.5):
                current["end"] = next_event["end"]
                current["duration"] = current["end"] - current["start"]
                # Ambil power ratio tertinggi
                current["power_ratio"] = max(current["power_ratio"], next_event["power_ratio"])
            else:
                merged.append(current)
                current = next_event.copy()
        
        merged.append(current)
        
        return merged
    
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
            'jitter_count': len(self.jitter_events),
            'led_flicker_count': len(self.led_flicker_events),
            'freeze_events': self.freeze_events,
            'scratch_events': self.scratch_events,
            'flicker_events': self.flicker_events,
            'drop_events': self.drop_events,
            'illegal_events': self.illegal_events,
            'jitter_events': self.jitter_events,
            'led_flicker_events': self.led_flicker_events
        }