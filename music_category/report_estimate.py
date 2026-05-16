from . import progress
from .schemas import DEFAULT_FIRST_MODEL_SECONDS, DEFAULT_SECONDS_PER_MODEL_FILE, MODELS_THAT_USE_AUDIO


def estimate_remaining_seconds(rows, mode, progress_path):
    cached = 0
    if mode in MODELS_THAT_USE_AUDIO:
        cached_results = progress.load_progress(progress_path)
        cached = sum(1 for row in rows if row.get("file_path") in cached_results)
    remaining_model = max(0, len(rows) - cached) if mode in MODELS_THAT_USE_AUDIO else 0
    seconds = 2 + (DEFAULT_FIRST_MODEL_SECONDS if remaining_model else 0) + remaining_model * DEFAULT_SECONDS_PER_MODEL_FILE
    return cached, seconds


def print_estimate(rows, mode, progress_path):
    cached, estimated_seconds = estimate_remaining_seconds(rows, mode, progress_path)
    print(f"Files: {len(rows)}")
    print(f"Mode: {mode}")
    print(f"Cached model results: {cached}")
    print(f"Estimated remaining time: {progress.format_duration(estimated_seconds)}")
