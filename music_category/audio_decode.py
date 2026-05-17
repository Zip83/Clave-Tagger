import contextlib
import os
import tempfile
import warnings

from . import app_logging


@contextlib.contextmanager
def _capture_native_stderr():
    """Capture native stderr."""
    original_fd = None
    temp = None
    capture_failed = False
    try:
        original_fd = os.dup(2)
        temp = tempfile.TemporaryFile(mode="w+b")
        os.dup2(temp.fileno(), 2)
    except Exception:
        capture_failed = True
    try:
        yield None if capture_failed else temp
    finally:
        if original_fd is not None:
            try:
                os.dup2(original_fd, 2)
            finally:
                os.close(original_fd)


def _read_captured_stderr(temp):
    """Read captured stderr."""
    if temp is None:
        return ""
    temp.flush()
    temp.seek(0)
    output = temp.read().decode("utf-8", errors="replace").strip()
    temp.close()
    return output


def run_with_decode_capture(file_path, operation):
    """Run with decode capture."""
    caught = []
    stderr_output = ""
    stderr_temp = None
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with _capture_native_stderr() as captured:
                stderr_temp = captured
                result = operation()
    except Exception:
        stderr_output = _read_captured_stderr(stderr_temp)
        if stderr_output:
            app_logging.log_info(f"Audio decode stderr for {file_path}: {stderr_output}")
        if caught:
            app_logging.log_info(
                "Audio decode warnings for "
                f"{file_path}: " + " | ".join(str(item.message) for item in caught[:10])
            )
        raise
    stderr_output = _read_captured_stderr(stderr_temp)
    if stderr_output:
        app_logging.log_info(f"Audio decode stderr for {file_path}: {stderr_output}")
    if caught:
        app_logging.log_info(
            "Audio decode warnings for "
            f"{file_path}: " + " | ".join(str(item.message) for item in caught[:10])
        )
    return result, caught, stderr_output


def load_audio(file_path, sample_rate, mono=True, offset=0.0, duration=None):
    """Load audio."""
    import librosa

    return run_with_decode_capture(
        file_path,
        lambda: librosa.load(
            file_path,
            sr=sample_rate,
            mono=mono,
            offset=offset,
            duration=duration,
        ),
    )


def get_duration(file_path):
    """Get duration."""
    import librosa

    return run_with_decode_capture(file_path, lambda: float(librosa.get_duration(path=str(file_path))))
