import os
from pathlib import Path


TOKEN_KEYS = {"HF_TOKEN", "HUGGINGFACE_HUB_TOKEN"}


def _clean_env_value(value):
    """Provide clean env value behavior."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_file(path=".env"):
    """Load env file."""
    env_path = Path(path or ".env")
    loaded = []
    skipped_existing = []
    if not env_path.exists():
        return {"path": str(env_path), "exists": False, "loaded": loaded, "skipped_existing": skipped_existing}

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        if key in os.environ:
            skipped_existing.append(key)
            continue
        os.environ[key] = _clean_env_value(value)
        loaded.append(key)
    return {"path": str(env_path), "exists": True, "loaded": loaded, "skipped_existing": skipped_existing}


def hf_token_status():
    """Provide hf token status behavior."""
    return "found" if any(os.environ.get(key) for key in TOKEN_KEYS) else "not found"


def env_status_message(status):
    """Provide env status message behavior."""
    exists = "found" if status.get("exists") else "missing"
    loaded = ", ".join(_safe_key(key) for key in status.get("loaded", [])) or "none"
    skipped = ", ".join(_safe_key(key) for key in status.get("skipped_existing", [])) or "none"
    return f"Env file {exists}: {status.get('path', '')} | loaded: {loaded} | kept existing: {skipped} | HF token: {hf_token_status()}"


def _safe_key(key):
    """Provide safe key behavior."""
    return key if key not in TOKEN_KEYS else key


def friendly_hf_error(error):
    """Provide friendly hf error behavior."""
    text = str(error)
    lowered = text.lower()
    if any(marker in lowered for marker in ("401", "403", "unauthorized", "forbidden", "gated", "private")):
        return (
            "Hugging Face denied access to this model. Set HF_TOKEN in your .env file "
            "or use a public model that your account can access."
        )
    return text
