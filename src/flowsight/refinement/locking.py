"""Short, reentrant filesystem transactions and local process identities."""

import os
import threading
import time
from pathlib import Path


class ProcessLock:
    """Serialize store instances/processes; the OS releases locks on exit."""

    def __init__(self, path: Path):
        self.path = path
        self._thread_lock = threading.RLock()
        self._depth = 0
        self._file = None

    def __enter__(self):
        self._thread_lock.acquire()
        try:
            if self._depth == 0:
                self._file = self.path.open("a+b")
                try:
                    if os.fstat(self._file.fileno()).st_size == 0:
                        self._file.write(b"\0")
                        self._file.flush()
                    if os.name == "nt":
                        import msvcrt

                        deadline = time.monotonic() + 10
                        while True:
                            self._file.seek(0)
                            try:
                                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
                                break
                            except OSError:
                                if time.monotonic() >= deadline:
                                    raise TimeoutError("refinement store transaction is busy")
                                time.sleep(0.01)
                    else:
                        import fcntl

                        fcntl.flock(self._file.fileno(), fcntl.LOCK_EX)
                except BaseException:
                    self._file.close()
                    self._file = None
                    raise
            self._depth += 1
            return self
        except BaseException:
            self._thread_lock.release()
            raise

    def __exit__(self, *exc):
        try:
            self._depth -= 1
            if self._depth == 0:
                try:
                    if os.name == "nt":
                        import msvcrt

                        self._file.seek(0)
                        msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
                finally:
                    self._file.close()
                    self._file = None
        finally:
            self._thread_lock.release()


def process_identity(pid: int) -> str | None:
    """Return a creation token, None for exited, or 'unknown' if inaccessible."""

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return None if ctypes.get_last_error() == 87 else "unknown"
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                return "unknown"
            if code.value != 259:
                return None
            times = [wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
                return "unknown"
            return str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        return "unknown"
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except OSError:
        return "unknown"
