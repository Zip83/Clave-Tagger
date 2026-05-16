import logging
import traceback
from pathlib import Path

from .app_paths import DEFAULT_LOG_FILE, ensure_runtime_dirs


def configure_logging(log_file=DEFAULT_LOG_FILE):
    """Provide configure logging behavior."""
    ensure_runtime_dirs()
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_path),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
        force=False,
    )
    return log_path


def log_info(message):
    """Provide log info behavior."""
    configure_logging()
    logging.getLogger("clavetagger").info(message)


def log_exception(message, error):
    """Provide log exception behavior."""
    configure_logging()
    logging.getLogger("clavetagger").error("%s: %s\n%s", message, error, traceback.format_exc())
