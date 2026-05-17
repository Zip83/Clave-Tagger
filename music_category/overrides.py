import csv
from datetime import datetime, timezone
from pathlib import Path

from . import config

FIELDNAMES = ["file_path", "file_name", "artist", "title", "manual_grouping", "manual_color", "note", "updated_at"]


def read_overrides(path):
    """Read overrides."""
    override_path = Path(path)
    if not override_path.exists():
        return {}
    with override_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {row.get("file_path", ""): row for row in rows if row.get("file_path")}


def apply_overrides(rows, path):
    """Apply overrides."""
    overrides = read_overrides(path)
    for row in rows:
        override = overrides.get(row.get("file_path", ""))
        if not override:
            continue
        grouping = override.get("manual_grouping", "")
        color = override.get("manual_color", "")
        if grouping:
            row["manual_grouping"] = config.normalize_value_to_category(grouping)
            row["target_grouping"] = row["manual_grouping"]
        if color:
            row["manual_color"] = color
            row["target_color"] = color
        row["manual_note"] = override.get("note", "")


def upsert_override(path, row, manual_grouping, manual_color="", note=""):
    """Upsert override."""
    overrides = read_overrides(path)
    file_path = row.get("file_path", "")
    overrides[file_path] = {
        "file_path": file_path,
        "file_name": row.get("file_name", ""),
        "artist": row.get("artist", ""),
        "title": row.get("title", ""),
        "manual_grouping": manual_grouping,
        "manual_color": manual_color,
        "note": note,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    write_overrides(path, overrides.values())


def write_overrides(path, rows):
    """Write overrides."""
    override_path = Path(path)
    override_path.parent.mkdir(parents=True, exist_ok=True)
    with override_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
