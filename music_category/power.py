import ctypes
import platform


ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def is_windows():
    return platform.system().lower() == "windows"


def prevent_sleep():
    if not is_windows():
        return False
    result = ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    return bool(result)


def allow_sleep():
    if not is_windows():
        return False
    result = ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    return bool(result)
