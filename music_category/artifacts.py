import csv
import shutil
from datetime import datetime
from pathlib import Path

from .schemas import empty_prediction_fields


ARTIFACT_POLICY_RESUME = "resume"
ARTIFACT_POLICY_FRESH = "fresh"
MERGE_REPORT_FIELDS = set(empty_prediction_fields()) | {
    "manual_grouping",
    "manual_color",
    "manual_note",
}


def path_if_exists(path):
    if not path:
        return None
    candidate = Path(path)
    return candidate if candidate.exists() else None


def detect_existing_artifacts(action, options):
    paths = []
    if action == "analyze":
        for path in (
            getattr(options, "progress_json", ""),
            getattr(options, "output_csv", ""),
            getattr(options, "details_csv", "") if getattr(options, "use_details", True) else "",
        ):
            existing = path_if_exists(path)
            if existing:
                paths.append(existing)
    elif action == "compare":
        for path in (getattr(options, "progress_json", ""), getattr(options, "model_comparison_csv", "")):
            existing = path_if_exists(path)
            if existing:
                paths.append(existing)
    elif action == "train":
        existing = path_if_exists(getattr(options, "classifier_output", ""))
        if existing:
            paths.append(existing)
    return list(dict.fromkeys(paths))


def backup_artifacts(paths, backup_root="backups", timestamp=None):
    existing = [Path(path) for path in paths if path and Path(path).exists()]
    if not existing:
        return {}
    timestamp = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = Path(backup_root) / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)
    moved = {}
    for source in existing:
        target = backup_dir / source.name
        counter = 1
        while target.exists():
            target = backup_dir / f"{source.stem}-{counter}{source.suffix}"
            counter += 1
        shutil.move(str(source), str(target))
        moved[str(source)] = str(target)
    return moved


def read_plain_csv(path):
    if not path or not Path(path).exists():
        return []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def merge_report_artifacts(rows, main_csv="", details_csv=""):
    by_path = {row.get("file_path", ""): row for row in rows if row.get("file_path")}
    merged = 0
    for artifact_row in read_plain_csv(main_csv) + read_plain_csv(details_csv):
        row = by_path.get(artifact_row.get("file_path", ""))
        if not row:
            continue
        changed = False
        for field in MERGE_REPORT_FIELDS:
            value = artifact_row.get(field, "")
            if value:
                row[field] = value
                changed = True
        if changed:
            merged += 1
    return merged


def prepare_artifacts(action, options, status_callback=None):
    found = detect_existing_artifacts(action, options)
    if getattr(options, "artifact_policy", ARTIFACT_POLICY_RESUME) == ARTIFACT_POLICY_FRESH:
        moved = backup_artifacts(found, getattr(options, "artifact_backup_dir", "backups"))
        if status_callback and moved:
            status_callback(f"Fresh start: backed up {len(moved)} existing artifact(s).")
        return moved
    if status_callback and found:
        status_callback(f"Resume: found {len(found)} existing artifact(s).")
    return {}
