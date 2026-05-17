from dataclasses import dataclass
from pathlib import Path

from . import app_env, app_logging, app_paths, artifacts, calibration, overrides, playlist_matcher, tag_writer
from .cancel import CancelledError
from . import report as core


ARTIFACT_POLICY_RESUME = artifacts.ARTIFACT_POLICY_RESUME
ARTIFACT_POLICY_FRESH = artifacts.ARTIFACT_POLICY_FRESH
MERGE_REPORT_FIELDS = artifacts.MERGE_REPORT_FIELDS


@dataclass
class ReportOptions:
    """ReportOptions."""
    source_paths: list
    input_csv: str
    output_csv: str
    details_csv: str
    model_comparison_csv: str
    progress_json: str
    config_path: str
    classifier_path: str
    classifier_input: str
    classifier_output: str
    classifier_backend: str
    recommendation_priority: str
    mode: str
    audio_model_id: str
    model_full_track: bool
    use_details: bool
    prediction_column: str
    truth_column: str
    overrides_csv: str
    log_file: str
    env_file: str
    write_after_report: bool
    value_column: str
    color_column_after_report: str
    only_missing_grouping: bool = False
    cancel_token: object = None
    artifact_policy: str = ARTIFACT_POLICY_RESUME
    artifact_backup_dir: str = "backups"


@dataclass
class TrainOptions:
    """TrainOptions."""
    source_paths: list
    input_csv: str
    details_csv: str
    config_path: str
    classifier_path: str
    classifier_input: str
    classifier_output: str
    classifier_backend: str
    classifier_preset: str
    training_source: str
    mode: str
    use_details: bool
    heavy_epochs: int
    heavy_batch_size: int
    heavy_learning_rate: float
    heavy_max_files: int | None
    heavy_max_chunks_per_file: int | None
    truth_column: str
    log_file: str
    env_file: str
    cancel_token: object = None
    artifact_policy: str = ARTIFACT_POLICY_RESUME
    artifact_backup_dir: str = "backups"


def _path_if_exists(path):
    """Path if exists."""
    return artifacts.path_if_exists(path)


def detect_existing_artifacts(action, options):
    """Detect existing artifacts."""
    return artifacts.detect_existing_artifacts(action, options)


def backup_artifacts(paths, backup_root="backups", timestamp=None):
    """Backup artifacts."""
    return artifacts.backup_artifacts(paths, backup_root, timestamp)


def _read_plain_csv(path):
    """Read plain csv."""
    return artifacts.read_plain_csv(path)


def merge_report_artifacts(rows, main_csv="", details_csv=""):
    """Merge report artifacts."""
    return artifacts.merge_report_artifacts(rows, main_csv, details_csv)


def prepare_artifacts(action, options, status_callback=None):
    """Prepare artifacts."""
    return artifacts.prepare_artifacts(action, options, status_callback)


@dataclass
class WriteOptions:
    """WriteOptions."""
    csv_path: str
    config_path: str
    grouping_column: str
    color_column: str
    apply_write: bool
    only_when_empty: bool


@dataclass
class EvaluationOptions:
    """EvaluationOptions."""
    source_paths: list
    input_csv: str
    mode: str
    config_path: str
    prediction_column: str
    truth_column: str


@dataclass
class CalibrationOptions:
    """CalibrationOptions."""
    input_csv: str
    output_config: str
    mismatch_output: str
    truth_column: str


@dataclass
class LabelPlaylistOptions:
    """LabelPlaylistOptions."""
    playlist_paths: list
    explicit_category: str
    min_score: float
    output_csv: str
    config_path: str


def default_classifier_output_for_backend(backend):
    """Default classifier output for backend."""
    if backend == "heavy":
        return str(app_paths.DEFAULT_HEAVY_CLASSIFIER)
    return str(app_paths.DEFAULT_LIGHT_CLASSIFIER)


def sync_classifier_paths_for_backend(backend, classifier_path, classifier_output):
    """Synchronize classifier paths for backend."""
    if backend == "auto":
        return classifier_path, classifier_output

    def is_default_path(path):
        """Is default path."""
        normalized = (path or "").replace("\\", "/")
        return normalized in {
            "",
            str(app_paths.DEFAULT_LIGHT_CLASSIFIER).replace("\\", "/"),
            str(app_paths.DEFAULT_HEAVY_CLASSIFIER).replace("\\", "/"),
        }

    default_path = default_classifier_output_for_backend(backend)
    next_path = default_path if is_default_path(classifier_path) else classifier_path
    next_output = default_path if is_default_path(classifier_output) else classifier_output
    return next_path, next_output


def dependency_state(mode, classifier_backend, use_details=True, write_after_report=False):
    """Dependency state."""
    uses_audio_model = mode in {"model", "both", "all"}
    uses_learned = mode in {"learned", "all"}
    is_heavy = classifier_backend == "heavy"
    is_light = classifier_backend == "light"
    return {
        "audio_model": uses_audio_model,
        "audio_progress": uses_audio_model,
        "learned_classifier": uses_learned,
        "details_csv": bool(use_details),
        "light_training": is_light,
        "heavy_training": is_heavy,
        "classifier_inference_backend": uses_learned,
        "write_after_report_columns": bool(write_after_report),
    }


def load_rows(source_paths, input_csv, mode, config_path, progress_callback=None):
    """Load rows."""
    core.load_category_config(config_path)
    if source_paths:
        return core.read_rows_from_sources(source_paths, mode, progress_callback=progress_callback)
    if input_csv:
        return core.read_rows_from_csv(input_csv, progress_callback=progress_callback)
    raise ValueError("Select at least one folder or an input CSV.")


def rows_without_source_folders(rows, removed_source_paths):
    """Rows without source folders."""
    removed = {str(Path(path)) for path in removed_source_paths}
    return [row for row in rows if str(Path(row.get("source_folder", ""))) not in removed]


def preview_rows(source_paths, input_csv, config_path, progress_callback=None):
    """Preview rows."""
    return load_rows(source_paths, input_csv, "tags", config_path, progress_callback=progress_callback)


def estimate_report(options, status_callback=None, progress_callback=None):
    """Estimate report."""
    if status_callback:
        status_callback("Estimate: loading track metadata...")
    rows = load_rows(options.source_paths, options.input_csv, options.mode, options.config_path, progress_callback=progress_callback)
    if status_callback:
        status_callback("Estimate: reading audio progress cache...")
    progress = core.load_progress(options.progress_json) if options.mode in core.MODELS_THAT_USE_AUDIO else {}
    cached = sum(1 for row in rows if core.model_cache_key(row, options.model_full_track, options.audio_model_id) in progress)
    remaining = max(0, len(rows) - cached) if options.mode in core.MODELS_THAT_USE_AUDIO else 0
    per_file = core.DEFAULT_SECONDS_PER_MODEL_FILE * (4 if options.model_full_track else 1)
    seconds = 2 + (core.DEFAULT_FIRST_MODEL_SECONDS if remaining else 0) + remaining * per_file
    scope = "full-track" if options.model_full_track else "30s clip"
    status = f"Files: {len(rows)} | mode: {options.mode} | MAEST: {scope} | cached model results: {cached} | estimate: {core.format_duration(seconds)}"
    return rows, status


def refresh_recommendations(rows, mode, priority):
    """Refresh recommendations."""
    core.apply_recommendations(rows, mode, priority)


def has_existing_grouping(row):
    """Has existing grouping."""
    return bool(str(row.get("id3_grouping_normalized") or row.get("id3_grouping") or "").strip())


def rows_missing_grouping(rows):
    """Rows missing grouping."""
    return [row for row in rows if not has_existing_grouping(row)]


def run_report(options, model_progress_callback=None, learned_progress_callback=None, rows=None, status_callback=None):
    """Run report."""
    def report_status(message):
        """Report status."""
        if status_callback:
            status_callback(message)

    report_status("Analyze: preparing logging and environment...")
    app_logging.configure_logging(options.log_file)
    app_env.load_env_file(options.env_file)
    if not options.output_csv:
        raise ValueError("Choose a main output CSV.")
    prepare_artifacts("analyze", options, status_callback=report_status)

    details_csv = options.details_csv if options.use_details else None
    report_status("Analyze: loading track metadata...")
    rows = rows if rows is not None else load_rows(options.source_paths, options.input_csv, options.mode, options.config_path)
    report_status(f"Analyze: {len(rows)} tracks ready.")
    if options.artifact_policy == ARTIFACT_POLICY_RESUME:
        merged = merge_report_artifacts(rows, options.output_csv, details_csv)
        if merged:
            report_status(f"Analyze: merged existing CSV predictions/targets for {merged} row(s).")
    if options.overrides_csv:
        report_status("Analyze: applying manual overrides...")
        overrides.apply_overrides(rows, options.overrides_csv)
    report_status("Analyze: preparing tag/text recommendations...")
    refresh_recommendations(rows, options.mode, options.recommendation_priority)
    analysis_rows = rows
    if options.only_missing_grouping:
        analysis_rows = rows_missing_grouping(rows)
        skipped = len(rows) - len(analysis_rows)
        for row in rows:
            row["_analysis_skipped_existing_grouping"] = has_existing_grouping(row)
        report_status(f"Analyze: Only missing Grouping is enabled; {len(analysis_rows)}/{len(rows)} tracks will be analyzed, {skipped} already tagged.")

    if options.mode in core.MODELS_THAT_USE_AUDIO:
        model_scope = "full tracks" if options.model_full_track else "30s clips"
        report_status(f"Analyze: preparing audio model analysis ({model_scope})...")
        core.run_model_analysis(
            analysis_rows,
            options.progress_json,
            options.output_csv,
            details_csv,
            options.mode,
            progress_callback=model_progress_callback,
            recommendation_priority=options.recommendation_priority,
            cancel_token=getattr(options, "cancel_token", None),
            full_track=options.model_full_track,
            model_id=options.audio_model_id,
        )

    if options.mode in core.MODES_THAT_USE_LEARNED:
        if not options.classifier_path:
            raise ValueError("Choose a learned classifier for learned/all mode.")
        report_status(f"Analyze: loading learned classifier ({options.classifier_backend})...")
        core.run_learned_analysis_backend(
            analysis_rows,
            options.classifier_path,
            backend=options.classifier_backend,
            progress_callback=learned_progress_callback,
            cancel_token=getattr(options, "cancel_token", None),
        )

    report_status("Analyze: finalizing recommendations...")
    refresh_recommendations(rows, options.mode, options.recommendation_priority)
    report_status(f"Analyze: writing main CSV to {options.output_csv}...")
    core.write_csv(options.output_csv, rows, core.MAIN_FIELDNAMES)
    if details_csv:
        report_status(f"Analyze: writing details CSV to {details_csv}...")
        core.write_csv(details_csv, rows, core.DETAIL_FIELDNAMES)
    if options.write_after_report:
        report_status("Analyze: preparing write-after-report dry run...")
        tag_writer.write_tags_from_csv(options.output_csv, options.value_column, options.color_column_after_report, apply_changes=False)

    status = f"Wrote {options.output_csv}" + (f" and {details_csv}" if details_csv else "")
    return rows, status


def compare_audio_models(options, progress_callback=None, rows=None, status_callback=None, load_progress_callback=None):
    """Compare audio models."""
    if status_callback:
        status_callback("Compare models: preparing logging and environment...")
    app_logging.configure_logging(options.log_file)
    app_env.load_env_file(options.env_file)
    prepare_artifacts("compare", options, status_callback=status_callback)
    if rows is None:
        if status_callback:
            status_callback("Compare models: loading track metadata...")
        rows = load_rows(options.source_paths, options.input_csv, "tags", options.config_path, progress_callback=load_progress_callback)
    if status_callback:
        status_callback(f"Compare models: running audio models for {len(rows)} tracks...")
    comparison_rows, fieldnames = core.run_audio_model_comparison(
        rows,
        options.model_comparison_csv,
        options.progress_json,
        full_track=options.model_full_track,
        progress_callback=progress_callback,
        cancel_token=getattr(options, "cancel_token", None),
    )
    status = f"Wrote audio model comparison CSV: {options.model_comparison_csv}"
    return rows, comparison_rows, fieldnames, status


def train_classifier(options, progress_callback=None, rows=None, status_callback=None):
    """Train classifier."""
    def report_status(message):
        """Report status."""
        if status_callback:
            status_callback(message)

    report_status("Training: preparing logging and environment...")
    app_logging.configure_logging(options.log_file)
    app_env.load_env_file(options.env_file)
    backend = options.classifier_backend
    if backend == "auto":
        raise ValueError("Choose light or heavy backend for training.")
    output_path = options.classifier_output or options.classifier_path or default_classifier_output_for_backend(backend)
    prepare_artifacts("train", options, status_callback=report_status)

    if rows is None:
        report_status("Training: loading rows from selected source...")
        rows = load_rows(options.source_paths, options.input_csv, options.mode, options.config_path)
    report_status(f"Training: {len(rows)} tracks ready. Filtering to rows with usable Grouping...")
    if options.classifier_input and Path(options.classifier_input).exists():
        report_status(f"Training: merging classifier input from {options.classifier_input}...")
        core.load_extra_classifier_input(rows, options.classifier_input)
    elif (
        options.artifact_policy != ARTIFACT_POLICY_FRESH
        and options.use_details
        and options.details_csv
        and Path(options.details_csv).exists()
    ):
        report_status(f"Training: merging detail features from {options.details_csv}...")
        core.load_extra_classifier_input(rows, options.details_csv)

    report_status(f"Training: starting {backend} classifier...")
    trained = core.train_classifier_backend(
        rows,
        output_path,
        backend=backend,
        truth_column=options.truth_column,
        epochs=options.heavy_epochs,
        batch_size=options.heavy_batch_size,
        learning_rate=options.heavy_learning_rate,
        limit=options.heavy_max_files,
        max_chunks_per_file=options.heavy_max_chunks_per_file,
        progress_callback=progress_callback,
        cancel_token=options.cancel_token,
    )
    status = f"Trained classifier {output_path} | rows={trained['trained_rows']} | labels={len(trained['labels'])}"
    report_status(status)
    return rows, trained, status


def evaluate_report(options, status_callback=None, progress_callback=None):
    """Evaluate report."""
    if status_callback:
        status_callback("Evaluate: loading rows and current tags...")
    rows = load_rows(options.source_paths, options.input_csv, options.mode, options.config_path, progress_callback=progress_callback)
    if status_callback:
        status_callback(f"Evaluate: comparing {options.prediction_column} against {options.truth_column}...")
    total, matches, accuracy = core.evaluate_rows(rows, options.prediction_column, options.truth_column)
    status = f"Compared rows: {total} | matches: {matches} | accuracy: {accuracy:.1%}"
    return rows, status


def calibrate(options, status_callback=None):
    """Calibrate the requested value."""
    if status_callback:
        status_callback(f"Calibrate: reading {options.input_csv}...")
    tuned, examples = calibration.calibrate_from_csv(
        options.input_csv,
        options.output_config,
        mismatch_output=options.mismatch_output,
        truth_column=options.truth_column,
    )
    if status_callback:
        status_callback(f"Calibrate: wrote suggested config to {options.output_config}.")
    return tuned, examples, f"Wrote {options.output_config}; mismatches: {len(examples)}"


def apply_playlist_matches_to_rows(rows, match_rows):
    """Apply playlist matches to rows."""
    row_by_path = {row.get("file_path", ""): row for row in rows if row.get("file_path")}
    matched_by_path = {}
    conflicts = set()
    for match in match_rows:
        file_path = match.get("file_path", "")
        grouping = match.get("target_grouping", "")
        if match.get("match_status") != "matched" or not file_path or not grouping:
            continue
        existing = matched_by_path.get(file_path)
        if existing and existing.get("target_grouping") != grouping:
            conflicts.add(file_path)
            continue
        matched_by_path[file_path] = match

    for match in match_rows:
        if match.get("file_path", "") not in conflicts:
            continue
        if match.get("match_status") != "matched":
            continue
        match["match_status"] = "review"
        match["match_confidence"] = "review"
        match["target_grouping"] = ""
        match["target_color"] = ""
        match["match_reason"] = f"{match.get('match_reason', '')}; conflicting playlist labels for same local file".strip("; ")

    updated_paths = []
    for file_path, match in matched_by_path.items():
        if file_path in conflicts:
            continue
        row = row_by_path.get(file_path)
        if not row:
            continue
        row["target_grouping"] = match.get("target_grouping", "")
        row["target_color"] = match.get("target_color", "")
        row["manual_note"] = f"Matched from playlist: {match.get('playlist_name', '')}".strip()
        row["_suppress_pending_recommendation"] = False
        updated_paths.append(file_path)
    return updated_paths, len(conflicts)


def match_label_playlists(options, rows, status_callback=None, progress_callback=None):
    """Match label playlists."""
    if not rows:
        raise ValueError("Load local tracks before matching label playlists.")
    if not options.playlist_paths:
        raise ValueError("Choose at least one label playlist file.")
    if not options.output_csv:
        raise ValueError("Choose a playlist match output CSV.")

    core.load_category_config(options.config_path)
    if status_callback:
        status_callback(f"Playlist match: loading {len(options.playlist_paths)} playlist file(s)...")
    label_tracks = playlist_matcher.load_label_playlists(options.playlist_paths, options.explicit_category)
    if status_callback:
        status_callback(f"Playlist match: matching {len(label_tracks)} playlist rows against {len(rows)} loaded tracks...")
    if progress_callback:
        progress_callback({
            "event": "playlist_match_start",
            "processed": 0,
            "total": len(label_tracks),
            "message": f"Playlist match: 0/{len(label_tracks)}",
        })

    match_rows = []
    total = max(1, len(label_tracks))
    for index, label in enumerate(label_tracks, start=1):
        match_rows.extend(playlist_matcher.match_label_tracks([label], rows, options.min_score))
        if progress_callback:
            progress_callback({
                "event": "playlist_match_file_done",
                "processed": index,
                "total": total,
                "message": f"Playlist match: {index}/{len(label_tracks)} | {label.artist} - {label.title}".strip(" -"),
            })

    updated_paths, conflicts = apply_playlist_matches_to_rows(rows, match_rows)
    if status_callback:
        status_callback(f"Playlist match: writing match CSV to {options.output_csv}...")
    core.write_csv(options.output_csv, match_rows, playlist_matcher.MATCH_FIELDNAMES)
    high = sum(1 for row in match_rows if row.get("match_status") == "matched")
    review = sum(1 for row in match_rows if row.get("match_status") == "review")
    unmatched = sum(1 for row in match_rows if row.get("match_status") == "unmatched")
    summary = {
        "playlist_rows": len(label_tracks),
        "matched": high,
        "review": review,
        "unmatched": unmatched,
        "updated": len(updated_paths),
        "conflicts": conflicts,
        "updated_paths": updated_paths,
        "output_csv": options.output_csv,
    }
    return match_rows, summary


def save_manual_override(path, row, grouping, color="", note=""):
    """Save manual override."""
    overrides.upsert_override(path, row, grouping, color, note)


def apply_manual_corrections(rows, file_paths, grouping, color="", note="", overrides_csv="", mode="both", priority="", config_path=""):
    """Apply manual corrections."""
    if config_path:
        core.load_category_config(config_path)
    selected = set(file_paths)
    if not selected:
        return 0
    grouping = (grouping or "").strip()
    color = (color or "").strip() or core.category_to_color(grouping)
    note = (note or "").strip()
    updated = 0
    for row in rows:
        if row.get("file_path") not in selected:
            continue
        row["manual_grouping"] = grouping
        row["manual_color"] = color
        row["target_grouping"] = grouping
        row["target_color"] = color
        row["manual_note"] = note
        if overrides_csv:
            overrides.upsert_override(overrides_csv, row, grouping, color, note)
        updated += 1
    refresh_recommendations(rows, mode, priority)
    return updated


def plan_write_tags(options, progress_callback=None, status_callback=None):
    """Plan write tags."""
    if not options.csv_path:
        raise ValueError("Choose a CSV file.")
    grouping = options.grouping_column or None
    color = options.color_column or None
    if not grouping and not color:
        raise ValueError("Fill grouping column and/or color column.")

    core.load_category_config(options.config_path)
    if status_callback:
        status_callback(f"Write tags: loading rows from {options.csv_path}...")
    rows = core.read_rows_from_csv(options.csv_path, progress_callback=progress_callback)
    if status_callback:
        status_callback("Write tags: planning changes...")
    changes, skipped = tag_writer.plan_tag_changes(rows, grouping, color, options.only_when_empty, progress_callback=progress_callback)
    return changes, len(skipped)


def plan_write_rows(rows, config_path, grouping_column=None, color_column=None, only_when_empty=False, progress_callback=None, status_callback=None):
    """Plan write rows."""
    grouping = grouping_column or None
    color = color_column or None
    if not grouping and not color:
        raise ValueError("Fill grouping column and/or color column.")

    core.load_category_config(config_path)
    if status_callback:
        status_callback(f"Write tags: planning changes for {len(rows)} in-memory rows...")
    changes, skipped = tag_writer.plan_tag_changes(rows, grouping, color, only_when_empty, progress_callback=progress_callback)
    return changes, len(skipped)


def run_write_tags(options, log_callback, progress_callback=None, status_callback=None):
    """Run write tags."""
    changes, skipped = plan_write_tags(options, progress_callback=progress_callback, status_callback=status_callback)
    if status_callback:
        status_callback(f"Write tags: {'writing' if options.apply_write else 'dry-run'} {len(changes)} planned changes...")
    tag_writer.apply_tag_changes(changes, apply_changes=options.apply_write, log=log_callback, progress_callback=progress_callback)
    log_callback(f"Planned changes: {len(changes)}")
    log_callback(f"Skipped checks: {skipped}")
    if not options.apply_write:
        log_callback("Dry-run only. Enable Apply write to modify MP3 files.")
    return changes, skipped


def run_write_rows(rows, config_path, grouping_column, color_column, apply_write=False, only_when_empty=False, log_callback=print, progress_callback=None, status_callback=None):
    """Run write rows."""
    changes, skipped = plan_write_rows(
        rows,
        config_path,
        grouping_column=grouping_column,
        color_column=color_column,
        only_when_empty=only_when_empty,
        progress_callback=progress_callback,
        status_callback=status_callback,
    )
    if status_callback:
        status_callback(f"Write tags: {'writing' if apply_write else 'dry-run'} {len(changes)} planned changes...")
    tag_writer.apply_tag_changes(changes, apply_changes=apply_write, log=log_callback, progress_callback=progress_callback)
    log_callback(f"Planned changes: {len(changes)}")
    log_callback(f"Skipped checks: {skipped}")
    if not apply_write:
        log_callback("Dry-run only. Enable Apply write to modify MP3 files.")
    return changes, skipped


def plan_clear_rows(rows, config_path, progress_callback=None, status_callback=None):
    """Plan clear rows."""
    core.load_category_config(config_path)
    if status_callback:
        status_callback(f"Clear tags: planning clears for {len(rows)} selected rows...")
    changes, skipped = tag_writer.plan_clear_tag_changes(rows, clear_grouping=True, clear_color=True, progress_callback=progress_callback)
    return changes, len(skipped)


def run_clear_rows(rows, config_path, apply_write=False, log_callback=print, progress_callback=None, status_callback=None):
    """Run clear rows."""
    changes, skipped = plan_clear_rows(rows, config_path, progress_callback=progress_callback, status_callback=status_callback)
    if status_callback:
        status_callback(f"Clear tags: {'clearing' if apply_write else 'dry-run'} {len(changes)} planned clears...")
    tag_writer.apply_tag_changes(changes, apply_changes=apply_write, log=log_callback, progress_callback=progress_callback)
    log_callback(f"Planned clears: {len(changes)}")
    log_callback(f"Skipped checks: {skipped}")
    if not apply_write:
        log_callback("Dry-run only. Use Clear Tags to modify MP3 files.")
    return changes, skipped
