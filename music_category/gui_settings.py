import json
from pathlib import Path

from . import app_paths


def load_settings(path=app_paths.DEFAULT_GUI_SETTINGS):
    settings_path = Path(path)
    if not settings_path.exists():
        return {}
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(settings, path=app_paths.DEFAULT_GUI_SETTINGS):
    settings_path = Path(path)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def collect_variables(variables):
    return {name: variable.get() for name, variable in variables.items()}


def apply_variables(settings, variables):
    for name, variable in variables.items():
        if name in settings:
            variable.set(settings[name])
