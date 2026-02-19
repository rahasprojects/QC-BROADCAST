class BaseCheck:
    name = "BaseCheck"

    def run(self, file_path, log_callback, progress_callback):
        raise NotImplementedError("run() harus diimplementasikan di subclass")
