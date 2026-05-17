import json
from pathlib import Path


CATALOG_PATH = Path(__file__).resolve().parent.parent / "audio_model_catalog.json"


def load_catalog(path=CATALOG_PATH):
    """Load catalog."""
    catalog_path = Path(path)
    if not catalog_path.exists():
        return []
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    models = data.get("models", [])
    return sorted(models, key=lambda item: int(item.get("rank", 999)))


def supported_models(path=CATALOG_PATH):
    """Supported models."""
    return [model for model in load_catalog(path) if model.get("status") == "supported"]


def preset_label(model):
    """Preset label."""
    model_id = model.get("model_id") or model.get("kind", "")
    suffix = f" - {model_id}" if model_id else ""
    return f"{model.get('rank', '?')}. {model.get('name', 'Unnamed model')}{suffix}"


def preset_labels(models=None):
    """Preset labels."""
    return [preset_label(model) for model in (models if models is not None else load_catalog())]


def find_by_label(label, models=None):
    """Find by label."""
    for model in models if models is not None else load_catalog():
        if label == preset_label(model):
            return model
    return None


def format_catalog(models=None):
    """Format catalog."""
    items = models if models is not None else load_catalog()
    if not items:
        return "No audio model presets found."

    headers = ("Rank", "Status", "Model", "ID", "Speed", "Expected use")
    rows = [
        (
            str(model.get("rank", "")),
            model.get("status", ""),
            model.get("name", ""),
            model.get("model_id", "") or "-",
            model.get("speed", ""),
            model.get("expected_accuracy", ""),
        )
        for model in items
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]

    def render(row):
        """Render."""
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))

    lines = [
        render(headers),
        render(tuple("-" * width for width in widths)),
    ]
    lines.extend(render(row) for row in rows)
    lines.append("")
    lines.append("Rank is ClaveTagger's practical preset order, not a universal benchmark.")
    lines.append("Future backend entries are documented options that are not wired into the current analysis path yet.")
    return "\n".join(lines)
