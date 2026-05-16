from pathlib import Path

APP_NAME = "ClaveTagger"

REPORTS_DIR = Path("reports")
PROGRESS_DIR = Path("progress")
MODELS_DIR = Path("models")
LOGS_DIR = Path("logs")
SETTINGS_DIR = Path("settings")

DEFAULT_MAIN_CSV = REPORTS_DIR / "report_main.csv"
DEFAULT_DETAILS_CSV = REPORTS_DIR / "report_details.csv"
DEFAULT_MODEL_COMPARISON_CSV = REPORTS_DIR / "model_comparison.csv"
DEFAULT_PLAYLIST_MATCHES_CSV = REPORTS_DIR / "playlist_label_matches.csv"
DEFAULT_PROGRESS_JSON = PROGRESS_DIR / "music_category_report_progress.json"
DEFAULT_LIGHT_CLASSIFIER = MODELS_DIR / "learned_light.joblib"
DEFAULT_HEAVY_CLASSIFIER = MODELS_DIR / "learned_heavy.pt"
DEFAULT_OVERRIDES_CSV = REPORTS_DIR / "manual_overrides.csv"
DEFAULT_LOG_FILE = LOGS_DIR / "clavetagger.log"
DEFAULT_GUI_SETTINGS = SETTINGS_DIR / "gui_settings.json"


def ensure_runtime_dirs():
    for path in (REPORTS_DIR, PROGRESS_DIR, MODELS_DIR, LOGS_DIR, SETTINGS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def as_posixish(path):
    return str(path).replace("\\", "/")
