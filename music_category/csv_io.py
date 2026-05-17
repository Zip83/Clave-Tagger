import csv
from pathlib import Path

from . import app_logging, id3_tags, text_classifier
from .schemas import DETAIL_FIELDNAMES, MAIN_FIELDNAMES, MODES_THAT_USE_TAGS, empty_prediction_fields


def iter_mp3_files(source_paths):
    """Iter mp3 files."""
    for source_path in source_paths:
        source = Path(source_path)
        for file_path in sorted(source.rglob("*.mp3")):
            yield source, file_path


def read_rows_from_sources(source_paths, mode, progress_callback=None):
    """Read rows from sources."""
    rows = []
    files = list(iter_mp3_files(source_paths))
    total = len(files)
    if progress_callback:
        progress_callback(
            {
                "event": "load_start",
                "processed": 0,
                "total": total,
                "message": f"Loading metadata for {total} MP3 files...",
            }
        )
    for index, (source, file_path) in enumerate(files, start=1):
        metadata = id3_tags.read_id3(file_path)
        row = {
            "source_folder": str(source),
            "file_path": str(file_path),
            "file_name": file_path.name,
            **metadata,
            **empty_prediction_fields(),
        }
        if mode in MODES_THAT_USE_TAGS:
            category, confidence, reason = text_classifier.classify_from_tags(row)
            row["tag_suggested_grouping"] = category
            row["tag_confidence"] = confidence
            row["tag_reason"] = reason
        rows.append(row)
        if progress_callback:
            progress_callback(
                {
                    "event": "load_file_done",
                    "row": row,
                    "processed": index,
                    "total": total,
                    "message": f"Loaded metadata {index}/{total}: {file_path.name}",
                }
            )
    return rows


def read_rows_from_csv(path, progress_callback=None):
    """Read rows from csv."""
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    total = len(rows)
    if progress_callback:
        progress_callback(
            {
                "event": "load_start",
                "processed": 0,
                "total": total,
                "message": f"Loading {total} rows from CSV...",
            }
        )
    for index, row in enumerate(rows, start=1):
        metadata = {}
        file_path = row.get("file_path", "")
        if file_path and Path(file_path).exists():
            try:
                metadata = id3_tags.read_id3(file_path)
            except Exception as error:
                app_logging.log_exception(f"Could not refresh ID3 metadata from CSV path {file_path}", error)
        row.setdefault("source_folder", "")
        row.setdefault("file_name", Path(row.get("file_path", "")).name)
        for key in ("artist", "title", "album", "genre", "id3_grouping", "id3_grouping_normalized", "id3_color", "id3_color_normalized"):
            if not row.get(key):
                row[key] = metadata.get(key, "")
        if "suggested_grouping" in row and not row.get("tag_suggested_grouping"):
            row["tag_suggested_grouping"] = row["suggested_grouping"]
        if "confidence" in row and not row.get("tag_confidence"):
            row["tag_confidence"] = row["confidence"]
        if "reason" in row and not row.get("tag_reason"):
                row["tag_reason"] = row["reason"]
        for key in MAIN_FIELDNAMES + DETAIL_FIELDNAMES:
            row.setdefault(key, "")
        if progress_callback:
            progress_callback(
                {
                    "event": "load_file_done",
                    "row": row,
                    "processed": index,
                    "total": total,
                    "message": f"Loaded CSV row {index}/{total}: {row.get('file_name') or row.get('file_path') or 'track'}",
                }
            )
    return rows


def load_extra_classifier_input(rows, classifier_input):
    """Load extra classifier input."""
    if not classifier_input:
        return
    extra_rows = read_rows_from_csv(classifier_input)
    by_path = {row.get("file_path", ""): row for row in extra_rows if row.get("file_path")}
    for row in rows:
        extra = by_path.get(row.get("file_path", ""))
        if not extra:
            continue
        for key in ("model_audio_top_labels", "model_audio_category_scores", "model_audio_reason"):
            if extra.get(key) and not row.get(key):
                row[key] = extra[key]


def write_csv(path, rows, fieldnames):
    """Write csv."""
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
