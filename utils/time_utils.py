def sec_to_tc(seconds):
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m:02d}:{s:05.2f}"
