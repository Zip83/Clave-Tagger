import sys

from . import app_env, app_logging, app_paths, artifacts, audio_model_catalog, audio_model_compare, calibration, classifier_presets, config, csv_io, evaluation, learning, model_runner, overrides, playlist_matcher, report_estimate, recommendations, tag_writer, text_classifier
from .cli_parser import build_parser
from .schemas import DETAIL_FIELDNAMES, MAIN_FIELDNAMES, MODELS_THAT_USE_AUDIO, MODES_THAT_USE_LEARNED, MODES_THAT_USE_TAGS

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

def apply_missing_tag_predictions(rows, mode, priority):
    if mode not in MODES_THAT_USE_TAGS:
        return
    for row in rows:
        if not row.get("tag_suggested_grouping"):
            category, confidence, reason = text_classifier.classify_from_tags(row)
            row["tag_suggested_grouping"] = category
            row["tag_confidence"] = confidence
            row["tag_reason"] = reason
    recommendations.apply_recommendations(rows, mode, priority)


def has_existing_grouping(row):
    return bool(str(row.get("id3_grouping_normalized") or row.get("id3_grouping") or "").strip())


def rows_missing_grouping(rows):
    return [row for row in rows if not has_existing_grouping(row)]


def train_if_requested(args, parser, rows, classifier_path):
    if not args.train_classifier:
        return classifier_path
    classifier_presets.apply_to_namespace(args)
    if args.classifier_backend == "auto":
        parser.error("--train-classifier requires --classifier-backend light or heavy, not auto")
    if args.classifier_backend == "heavy" and args.classifier_output == str(app_paths.DEFAULT_LIGHT_CLASSIFIER):
        args.classifier_output = str(app_paths.DEFAULT_HEAVY_CLASSIFIER)
    artifacts.prepare_artifacts("train", args, status_callback=print)
    def print_progress(payload):
        message = payload.get("message")
        if message:
            print(message, flush=True)
    trained = learning.train_classifier_backend(
        rows,
        args.classifier_output,
        backend=args.classifier_backend,
        truth_column=args.truth_column,
        epochs=args.heavy_epochs,
        batch_size=args.heavy_batch_size,
        learning_rate=args.heavy_learning_rate,
        limit=args.heavy_max_files,
        max_chunks_per_file=args.heavy_max_chunks_per_file,
        progress_callback=print_progress,
    )
    print(
        f"Trained {args.classifier_backend} classifier: {args.classifier_output} "
        f"(rows={trained['trained_rows']}, labels={len(trained['labels'])}, "
        f"skipped_no_truth={trained['skipped_no_truth']}, "
        f"skipped_no_features={trained.get('skipped_no_features', 0)}, "
        f"skipped_missing_file={trained.get('skipped_missing_file', 0)})"
    )
    return classifier_path or args.classifier_output


def main():
    parser = build_parser()
    args = parser.parse_args()
    app_paths.ensure_runtime_dirs()
    app_logging.configure_logging(args.log_file)
    env_status = app_env.load_env_file(args.env_file)
    app_logging.log_info(app_env.env_status_message(env_status))
    if args.list_audio_models:
        print(audio_model_catalog.format_catalog())
        return
    config.load_category_config(args.config)

    if args.calibrate_from_csv:
        tuned, examples = calibration.calibrate_from_csv(
            args.calibrate_from_csv,
            args.calibration_output,
            mismatch_output=args.mismatch_output,
            truth_column=args.truth_column,
        )
        print(f"Wrote suggested config: {args.calibration_output}")
        print(f"Wrote mismatches: {args.mismatch_output}")
        print(f"Calibration notes: {len(tuned.get('calibration_notes', []))}; mismatch examples: {len(examples)}")
        return

    if args.write_grouping_from_csv:
        tag_writer.write_grouping_from_csv(args.write_grouping_from_csv, args.value_column, args.apply_write, args.only_when_empty)
        return
    if args.write_tags_from_csv:
        if not args.grouping_column and not args.color_column:
            parser.error("--write-tags-from-csv requires --grouping-column and/or --color-column")
        tag_writer.write_tags_from_csv(args.write_tags_from_csv, args.grouping_column, args.color_column, args.apply_write, args.only_when_empty)
        return

    if args.label_playlist:
        if not args.source:
            parser.error("--label-playlist requires --source with local MP3 folders to match against")
        print("Loading local MP3 metadata for playlist matching...")
        local_rows = csv_io.read_rows_from_sources(args.source, "tags")
        print(f"Loading label playlist rows from {len(args.label_playlist)} playlist file(s)...")
        label_tracks = playlist_matcher.load_label_playlists(args.label_playlist, args.label_playlist_category)
        match_rows = playlist_matcher.match_label_tracks(label_tracks, local_rows, args.label_match_min_score)
        csv_io.write_csv(args.label_playlist_output, match_rows, playlist_matcher.MATCH_FIELDNAMES)
        high = sum(1 for row in match_rows if row.get("match_confidence") == "high")
        review = len(match_rows) - high
        print(f"Wrote playlist match CSV: {args.label_playlist_output}")
        print(f"Playlist rows: {len(label_tracks)} | high matches: {high} | review/unmatched: {review}")
        print("Dry-run write matched labels with:")
        print(f"  --write-tags-from-csv \"{args.label_playlist_output}\" --grouping-column target_grouping --color-column target_color")
        return

    if not args.source and not args.input_csv:
        parser.error("report mode requires --source or --input-csv")
    if not args.output_csv and not args.estimate_only and not args.evaluate and not args.train_classifier:
        parser.error("report mode requires --output-csv")

    load_mode = "tags" if args.compare_audio_models else args.mode
    args.use_details = bool(args.details_csv)
    action = "compare" if args.compare_audio_models else "analyze"
    if not args.estimate_only and not args.evaluate and not args.train_classifier:
        artifacts.prepare_artifacts(action, args, status_callback=print)
    rows = csv_io.read_rows_from_sources(args.source, load_mode) if args.source else csv_io.read_rows_from_csv(args.input_csv)
    if args.artifact_policy == "resume" and not args.compare_audio_models:
        merged = artifacts.merge_report_artifacts(rows, args.output_csv, args.details_csv)
        if merged:
            print(f"Merged existing CSV predictions/targets for {merged} row(s).")
    csv_io.load_extra_classifier_input(rows, args.classifier_input)
    if args.overrides_csv:
        overrides.apply_overrides(rows, args.overrides_csv)
    apply_missing_tag_predictions(rows, load_mode, args.recommendation_priority)

    if args.compare_audio_models:
        comparison_rows, fieldnames = audio_model_compare.run_audio_model_comparison(
            rows,
            args.model_comparison_csv,
            args.progress_json,
            full_track=args.model_full_track,
        )
        print(f"Wrote audio model comparison CSV: {args.model_comparison_csv}")
        print(f"Compared rows: {len(comparison_rows)} | model columns: {len(fieldnames) - len(audio_model_compare.BASE_COMPARISON_FIELDS)}")
        return

    if args.estimate_only:
        report_estimate.print_estimate(rows, args.mode, args.progress_json)
        return

    training_only = args.train_classifier and not args.output_csv and not args.evaluate and args.classifier_backend == "heavy"
    should_run_model = (
        args.mode in MODELS_THAT_USE_AUDIO
        and not training_only
        and not (args.evaluate and args.input_csv and not args.output_csv)
    )
    if should_run_model:
        analysis_rows = rows_missing_grouping(rows) if args.only_missing_grouping else rows
        if args.only_missing_grouping:
            skipped = len(rows) - len(analysis_rows)
            print(f"Only missing Grouping: analyzing {len(analysis_rows)} of {len(rows)} files; skipping {skipped} tagged files.")
        model_runner.run_model_analysis(
            analysis_rows,
            args.progress_json,
            args.output_csv,
            args.details_csv,
            args.mode,
            recommendation_priority=args.recommendation_priority,
            full_track=args.model_full_track,
            model_id=args.audio_model_id,
        )

    classifier_path = train_if_requested(args, parser, rows, args.use_classifier)
    if args.mode in MODES_THAT_USE_LEARNED:
        if not classifier_path:
            parser.error("--mode learned/all requires --use-classifier or --train-classifier")
        analysis_rows = rows_missing_grouping(rows) if args.only_missing_grouping else rows
        if args.only_missing_grouping and not should_run_model:
            skipped = len(rows) - len(analysis_rows)
            print(f"Only missing Grouping: analyzing {len(analysis_rows)} of {len(rows)} files; skipping {skipped} tagged files.")
        learning.run_learned_analysis_backend(analysis_rows, classifier_path, backend=args.classifier_backend, progress_callback=None)

    recommendations.apply_recommendations(rows, args.mode, args.recommendation_priority)

    if args.evaluate:
        evaluation.evaluate_rows(rows, args.prediction_column, args.truth_column)
        evaluation.evaluate_available_predictions(rows, args.truth_column)

    if args.output_csv:
        csv_io.write_csv(args.output_csv, rows, MAIN_FIELDNAMES)
        print(f"Wrote main CSV: {args.output_csv}")
    if args.details_csv:
        csv_io.write_csv(args.details_csv, rows, DETAIL_FIELDNAMES)
        print(f"Wrote details CSV: {args.details_csv}")

    if args.write_after_report:
        if not args.output_csv:
            parser.error("--write-after-report requires --output-csv")
        tag_writer.write_tags_from_csv(args.output_csv, args.value_column, args.color_column, args.apply_write, args.only_when_empty)
