from .audio_model import analyze_audio, classify_from_model
from .cli import build_parser, main
from .config import category_to_color, category_to_grouping, load_category_config, normalize_value_to_category
from .csv_io import iter_mp3_files, load_extra_classifier_input, read_rows_from_csv, read_rows_from_sources, write_csv
from .evaluation import evaluate_available_predictions, evaluate_rows
from .id3_tags import read_id3, write_id3_color, write_id3_grouping
from .learning import (
    run_learned_analysis,
    run_learned_analysis_backend,
    train_classifier,
    train_classifier_backend,
)
from .model_runner import model_cache_key, run_model_analysis
from .audio_model_compare import comparison_fieldnames, comparison_models, run_audio_model_comparison
from .progress import format_duration, load_progress, save_progress
from .recommendations import apply_recommendations, choose_recommendation, parse_priority, recommendation_sources_for_mode
from .report_estimate import print_estimate
from .schemas import (
    DEFAULT_FIRST_MODEL_SECONDS,
    DEFAULT_SECONDS_PER_MODEL_FILE,
    DETAIL_FIELDNAMES,
    MAIN_FIELDNAMES,
    MODELS_THAT_USE_AUDIO,
    MODES_THAT_USE_LEARNED,
    MODES_THAT_USE_TAGS,
    empty_prediction_fields,
)
from .tag_writer import write_grouping_from_csv, write_tags_from_csv
from .text_classifier import classify_from_tags
from .overrides import apply_overrides, read_overrides, upsert_override, write_overrides
from .calibration import calibrate_from_csv
from .playlist_matcher import load_label_playlists, match_label_tracks, MATCH_FIELDNAMES

__all__ = [name for name in globals() if not name.startswith("_")]
