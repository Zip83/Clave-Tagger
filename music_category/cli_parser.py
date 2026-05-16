import argparse

from . import app_paths, audio_model, classifier_presets


def build_parser():
    """Build parser."""
    class HelpFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
        """Provide HelpFormatter behavior."""
        pass

    parser = argparse.ArgumentParser(
        description="Create MP3 category reports, train a local classifier, evaluate predictions, and optionally write Grouping/Color tags.",
        formatter_class=HelpFormatter,
    )
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument("--source", nargs="+", help="One or more folders containing MP3 files.")
    input_group.add_argument("--input-csv", help="Existing CSV to enrich or evaluate.")
    parser.add_argument("--env-file", default=".env", help="Local .env file. HF_TOKEN from this file is used for Hugging Face downloads unless already set in the environment.")
    parser.add_argument("--output-csv", default=str(app_paths.DEFAULT_MAIN_CSV), help="Main clean output CSV.")
    parser.add_argument("--details-csv", default=str(app_paths.DEFAULT_DETAILS_CSV), help="Optional detail CSV with reasons, model labels and category scores.")
    parser.add_argument("--mode", choices=["tags", "model", "both", "learned", "all"], default="both", help="How to classify songs.")
    parser.add_argument("--list-audio-models", action="store_true", help="Print known audio model presets and exit.")
    parser.add_argument("--audio-model-id", default=audio_model.MODEL_ID, help="Hugging Face audio-classification model id used for --mode model/both/all.")
    parser.add_argument("--compare-audio-models", action="store_true", help="Run every supported audio model preset and write a side-by-side comparison CSV.")
    parser.add_argument("--model-comparison-csv", default=str(app_paths.DEFAULT_MODEL_COMPARISON_CSV), help="Output CSV for --compare-audio-models.")
    parser.add_argument("--label-playlist", nargs="+", help="One or more CSV, M3U/M3U8, or VirtualDJ XML playlist files used as label sources to match against local MP3 files.")
    parser.add_argument("--label-playlist-category", default="", help="Optional category for all --label-playlist rows. Empty infers the category from the playlist file/name, e.g. Son -> Son Cubano.")
    parser.add_argument("--label-playlist-output", default=str(app_paths.DEFAULT_PLAYLIST_MATCHES_CSV), help="CSV output for strict playlist-to-local-file matches.")
    parser.add_argument("--label-match-min-score", type=float, default=0.94, help="Minimum strict match score before target_grouping/target_color are filled.")
    parser.add_argument("--model-full-track", action="store_true", help="Run the selected audio model over the whole song by averaging 30s chunks instead of one 30s clip.")
    parser.add_argument("--only-missing-grouping", action="store_true", help="Analyze only files where Grouping/TIT1 is empty; tagged rows remain in the CSV.")
    parser.add_argument("--progress-json", default=str(app_paths.DEFAULT_PROGRESS_JSON), help="Resume cache for model results.")
    parser.add_argument("--artifact-policy", choices=["resume", "fresh"], default="resume", help="Use existing runtime artifacts, or back them up and start clean.")
    parser.add_argument("--artifact-backup-dir", default="backups", help="Backup folder used when --artifact-policy fresh is selected.")
    parser.add_argument("--estimate-only", action="store_true", help="Only count files and estimate runtime.")
    parser.add_argument("--evaluate", action="store_true", help="Compare prediction column against a truth column.")
    parser.add_argument("--prediction-column", default="recommended_grouping", help="Prediction column for --evaluate.")
    parser.add_argument("--truth-column", default="id3_grouping_normalized", help="Truth column for --evaluate.")
    parser.add_argument("--train-classifier", action="store_true", help="Train a local classifier from existing Grouping tags and model feature columns.")
    parser.add_argument("--classifier-preset", choices=classifier_presets.choices(), default="", help="Optional training preset: light, heavy-fast, heavy-balanced, or heavy-thorough.")
    parser.add_argument("--classifier-backend", choices=["light", "heavy", "auto"], default="light", help="Classifier backend for training or learned analysis.")
    parser.add_argument("--classifier-output", default=str(app_paths.DEFAULT_LIGHT_CLASSIFIER), help="Output path for --train-classifier.")
    parser.add_argument("--classifier-input", help="Optional detail CSV to merge feature columns before training.")
    parser.add_argument("--use-classifier", help="Path to a learned classifier joblib used by --mode learned/all.")
    parser.add_argument("--heavy-epochs", type=int, default=8, help="Epoch count for --classifier-backend heavy.")
    parser.add_argument("--heavy-batch-size", type=int, default=8, help="Batch size for --classifier-backend heavy.")
    parser.add_argument("--heavy-learning-rate", type=float, default=1e-3, help="Learning rate for --classifier-backend heavy.")
    parser.add_argument("--heavy-max-files", type=int, help="Optional limit of tagged files for heavy training.")
    parser.add_argument("--heavy-max-chunks-per-file", type=int, help="Optional limit of whole-song chunks per file for heavy training.")
    parser.add_argument("--recommendation-priority", default="", help="Comma-separated recommendation priority. Empty uses confidence-aware ordering.")
    parser.add_argument("--overrides-csv", default=str(app_paths.DEFAULT_OVERRIDES_CSV), help="Optional manual overrides CSV.")
    parser.add_argument("--calibrate-from-csv", help="Existing report CSV used to suggest category_config tuning.")
    parser.add_argument("--calibration-output", default="category_config.tuned.json", help="Suggested tuned config output path.")
    parser.add_argument("--mismatch-output", default="reports/calibration_mismatches.csv", help="Mismatch CSV output for --calibrate-from-csv.")
    parser.add_argument("--log-file", default=str(app_paths.DEFAULT_LOG_FILE), help="Application log file.")
    parser.add_argument("--config", default="category_config.json", help="Category config with Grouping and Color values.")
    parser.add_argument("--write-grouping-from-csv", help="Write ID3 Grouping/TIT1 values from a CSV instead of creating a report.")
    parser.add_argument("--write-tags-from-csv", help="Write ID3 Grouping and/or Color values from a CSV instead of creating a report.")
    parser.add_argument("--value-column", default="target_grouping", help="CSV column used as target Grouping value.")
    parser.add_argument("--grouping-column", help="CSV column used as target Grouping value for --write-tags-from-csv.")
    parser.add_argument("--color-column", help="CSV column used as target Color value for --write-tags-from-csv.")
    parser.add_argument("--apply-write", action="store_true", help="Actually write MP3 tags. Without this, write mode is dry-run.")
    parser.add_argument("--only-when-empty", action="store_true", help="In write mode, skip files that already have Grouping.")
    parser.add_argument("--write-after-report", action="store_true", help="After writing report, write Grouping using --value-column.")
    return parser
