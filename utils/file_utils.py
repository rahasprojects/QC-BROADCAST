import os
import time


def wait_until_file_released(path):
    while True:
        try:
            with open(path, 'rb'):
                return
        except:
            time.sleep(2)


def wait_until_copy_complete(path):
    stable = 0
    last_size = -1

    while stable < 5:
        try:
            size = os.path.getsize(path)
            if size == last_size:
                stable += 1
            else:
                stable = 0
            last_size = size
            time.sleep(2)
        except:
            return False
    return True
