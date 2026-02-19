import json
import os
from datetime import datetime
from config import LOG_FOLDER

TRACKING_FILE = os.path.join(LOG_FOLDER, "processed_files.json")

def load_processed_files():
    """Load daftar file yang sudah pernah diproses"""
    if os.path.exists(TRACKING_FILE):
        try:
            with open(TRACKING_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_processed_files(processed):
    """Simpan daftar file yang sudah diproses"""
    try:
        with open(TRACKING_FILE, 'w') as f:
            json.dump(processed, f, indent=2)
    except:
        pass

def is_file_processed(file_path, processed_files):
    """
    Cek apakah file sudah pernah diproses
    File dianggap sudah diproses jika:
    - Nama file SAMA
    - Ukuran file SAMA
    - Modified time SAMA
    """
    if not os.path.exists(file_path):
        return False
        
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    file_mtime = os.path.getmtime(file_path)
    
    if file_name in processed_files:
        prev = processed_files[file_name]
        # Cek apakah SEMUA kriteria sama
        if (prev.get('size') == file_size and 
            prev.get('mtime') == file_mtime):
            return True  # Sudah diproses (file sama persis)
    
    return False  # Belum diproses (ada kriteria yang beda)

def mark_file_processed(file_path, processed_files):
    """Tandai file sebagai sudah diproses"""
    if not os.path.exists(file_path):
        return
        
    file_name = os.path.basename(file_path)
    processed_files[file_name] = {
        'size': os.path.getsize(file_path),
        'mtime': os.path.getmtime(file_path),
        'processed_at': datetime.now().isoformat()
    }
    save_processed_files(processed_files)

def remove_from_tracking(file_path, processed_files):
    """Hapus file dari tracking (jika diperlukan)"""
    file_name = os.path.basename(file_path)
    if file_name in processed_files:
        del processed_files[file_name]
        save_processed_files(processed_files)