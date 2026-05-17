from . import config, csv_io, id3_tags


def plan_tag_changes(rows, grouping_column=None, color_column=None, only_when_empty=False, progress_callback=None):
    """Plan tag changes."""
    changes = []
    skipped = []
    total = len(rows)
    if progress_callback:
        progress_callback(
            {
                "event": "write_plan_start",
                "processed": 0,
                "total": total,
                "message": f"Planning tag changes for {total} rows...",
            }
        )
    for index, row in enumerate(rows, start=1):
        file_path = row.get("file_path", "")
        if not file_path:
            skipped.append((file_path, "missing file_path"))
            continue

        metadata = None
        row_changes = {}

        if grouping_column:
            raw_grouping = (row.get(grouping_column, "") or "").strip()
            target_grouping = config.category_to_grouping(raw_grouping)
            if not raw_grouping:
                skipped.append((file_path, f"empty {grouping_column}"))
            elif config.normalize_value_to_category(raw_grouping) == "Needs review":
                skipped.append((file_path, "target grouping is Needs review"))
            else:
                metadata = metadata or id3_tags.read_id3(file_path)
                if only_when_empty and metadata["id3_grouping"]:
                    skipped.append((file_path, f"Grouping already set: {metadata['id3_grouping']}"))
                elif metadata["id3_grouping"] != target_grouping:
                    row_changes["grouping"] = (metadata["id3_grouping"], target_grouping)

        if color_column:
            raw_color = (row.get(color_column, "") or "").strip()
            target_color = config.category_to_color(raw_color)
            if not raw_color:
                skipped.append((file_path, f"empty {color_column}"))
            elif config.normalize_value_to_category(raw_color) == "Needs review":
                skipped.append((file_path, "target color is Needs review"))
            else:
                metadata = metadata or id3_tags.read_id3(file_path)
                if only_when_empty and metadata["id3_color"]:
                    skipped.append((file_path, f"Color already set: {metadata['id3_color']}"))
                elif metadata["id3_color"] != target_color:
                    row_changes["color"] = (metadata["id3_color"], target_color)

        if row_changes:
            changes.append((file_path, row_changes))
        if progress_callback:
            progress_callback(
                {
                    "event": "write_plan_file_done",
                    "row": row,
                    "processed": index,
                    "total": total,
                    "message": f"Planned tag row {index}/{total}: {row.get('file_name') or file_path or 'track'}",
                }
            )
    return changes, skipped


def plan_clear_tag_changes(rows, clear_grouping=True, clear_color=True, progress_callback=None):
    """Plan clear tag changes."""
    changes = []
    skipped = []
    total = len(rows)
    if progress_callback:
        progress_callback(
            {
                "event": "clear_plan_start",
                "processed": 0,
                "total": total,
                "message": f"Planning tag clears for {total} rows...",
            }
        )
    for index, row in enumerate(rows, start=1):
        file_path = row.get("file_path", "")
        if not file_path:
            skipped.append((file_path, "missing file_path"))
            continue

        metadata = id3_tags.read_id3(file_path)
        row_changes = {}
        if clear_grouping and metadata["id3_grouping"]:
            row_changes["clear_grouping"] = (metadata["id3_grouping"], "")
        if clear_color and metadata["id3_color"]:
            row_changes["clear_color"] = (metadata["id3_color"], "")

        if row_changes:
            changes.append((file_path, row_changes))
        else:
            skipped.append((file_path, "Grouping/Color already empty"))

        if progress_callback:
            progress_callback(
                {
                    "event": "clear_plan_file_done",
                    "row": row,
                    "processed": index,
                    "total": total,
                    "message": f"Planned clear row {index}/{total}: {row.get('file_name') or file_path or 'track'}",
                }
            )
    return changes, skipped


def apply_tag_changes(changes, apply_changes=False, log=print, progress_callback=None):
    """Apply tag changes."""
    total = len(changes)
    if progress_callback:
        progress_callback(
            {
                "event": "write_apply_start",
                "processed": 0,
                "total": total,
                "message": f"{'Writing' if apply_changes else 'Dry-run'} tag changes for {total} files...",
            }
        )
    for index, (file_path, row_changes) in enumerate(changes, start=1):
        log(f"[{index}/{len(changes)}] {'WRITE' if apply_changes else 'DRY-RUN'}: {file_path}")
        if "grouping" in row_changes:
            current_value, target_value = row_changes["grouping"]
            log(f"  Grouping: {current_value!r} -> {target_value!r}")
        if "color" in row_changes:
            current_value, target_value = row_changes["color"]
            log(f"  Color: {current_value!r} -> {target_value!r}")
        if "clear_grouping" in row_changes:
            current_value, _target_value = row_changes["clear_grouping"]
            log(f"  Clear Grouping: {current_value!r} -> ''")
        if "clear_color" in row_changes:
            current_value, _target_value = row_changes["clear_color"]
            log(f"  Clear Color: {current_value!r} -> ''")
        if apply_changes:
            if "grouping" in row_changes:
                id3_tags.write_id3_grouping(file_path, row_changes["grouping"][1])
            if "color" in row_changes:
                id3_tags.write_id3_color(file_path, row_changes["color"][1])
            if "clear_grouping" in row_changes:
                id3_tags.clear_id3_grouping(file_path)
            if "clear_color" in row_changes:
                id3_tags.clear_id3_color(file_path)
        if progress_callback:
            progress_callback(
                {
                    "event": "write_apply_file_done",
                    "processed": index,
                    "total": total,
                    "message": f"{'Wrote' if apply_changes else 'Dry-run'} tag changes {index}/{total}: {file_path}",
                }
            )


def write_tags_from_csv(csv_path, grouping_column=None, color_column=None, apply_changes=False, only_when_empty=False):
    """Write tags from csv."""
    rows = csv_io.read_rows_from_csv(csv_path)
    changes, skipped = plan_tag_changes(rows, grouping_column, color_column, only_when_empty)
    apply_tag_changes(changes, apply_changes=apply_changes)
    print(f"Planned changes: {len(changes)}")
    print(f"Skipped rows: {len(skipped)}")
    if not apply_changes:
        print("Dry-run only. Add --apply-write to modify MP3 files.")


def write_grouping_from_csv(csv_path, value_column, apply_changes=False, only_when_empty=False):
    """Write grouping from csv."""
    write_tags_from_csv(csv_path=csv_path, grouping_column=value_column, color_column=None, apply_changes=apply_changes, only_when_empty=only_when_empty)
