from . import audio_model

MODELS_THAT_USE_AUDIO = {"model", "both", "all"}
MODES_THAT_USE_TAGS = {"tags", "both", "all"}
MODES_THAT_USE_LEARNED = {"learned", "all"}

DEFAULT_SECONDS_PER_MODEL_FILE = audio_model.DEFAULT_SECONDS_PER_MODEL_FILE
DEFAULT_FIRST_MODEL_SECONDS = audio_model.DEFAULT_FIRST_MODEL_SECONDS

MAIN_FIELDNAMES = [
    "source_folder",
    "file_path",
    "file_name",
    "artist",
    "title",
    "album",
    "genre",
    "id3_grouping",
    "id3_grouping_normalized",
    "id3_color",
    "id3_color_normalized",
    "tag_suggested_grouping",
    "tag_confidence",
    "model_audio_suggested_grouping",
    "model_audio_confidence",
    "model_audio_bpm",
    "learned_suggested_grouping",
    "learned_confidence",
    "recommended_grouping",
    "recommended_source",
    "recommended_confidence",
    "target_grouping",
    "target_color",
]

DETAIL_FIELDNAMES = [
    "file_path",
    "file_name",
    "tag_reason",
    "model_audio_top_labels",
    "model_audio_category_scores",
    "model_audio_reason",
    "learned_reason",
]


def empty_prediction_fields():
    """Provide empty prediction fields behavior."""
    return {
        "tag_suggested_grouping": "",
        "tag_confidence": "",
        "tag_reason": "",
        "model_audio_suggested_grouping": "",
        "model_audio_confidence": "",
        "model_audio_bpm": "",
        "model_audio_top_labels": "",
        "model_audio_category_scores": "",
        "model_audio_reason": "",
        "learned_suggested_grouping": "",
        "learned_confidence": "",
        "learned_reason": "",
        "recommended_grouping": "",
        "recommended_source": "",
        "recommended_confidence": "",
        "target_grouping": "",
        "target_color": "",
    }
