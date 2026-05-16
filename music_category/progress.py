import json
from pathlib import Path


def load_progress(path):
    progress_path = Path(path)
    if not progress_path.exists():
        return {}
    return json.loads(progress_path.read_text(encoding="utf-8"))


def save_progress(path, progress):
    Path(path).write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")


def format_duration(seconds):
    seconds = int(round(seconds))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"
