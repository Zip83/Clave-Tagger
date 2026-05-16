from .light_model import (
    learned_features,
    parse_score_pairs,
    parse_top_label_scores,
    run_learned_analysis,
    train_classifier,
    truth_category,
)
from . import app_logging


def _detect_with_torch(classifier_path):
    import torch

    payload = torch.load(classifier_path, map_location="cpu")
    if isinstance(payload, dict) and payload.get("kind") == "heavy-audio-cnn":
        return "heavy"
    return ""


def _detect_with_joblib(classifier_path):
    from joblib import load

    payload = load(classifier_path)
    if isinstance(payload, dict) and payload.get("pipeline"):
        return "light"
    return ""


def train_classifier_backend(
    rows,
    output_path,
    backend="light",
    truth_column="id3_grouping_normalized",
    progress_callback=None,
    **options,
):
    if backend == "light":
        return train_classifier(
            rows,
            output_path,
            truth_column,
            progress_callback=progress_callback,
            cancel_token=options.get("cancel_token"),
        )
    if backend == "heavy":
        from . import heavy_model

        return heavy_model.train_heavy_classifier(
            rows,
            output_path,
            truth_column=truth_column,
            epochs=int(options.get("epochs", 8)),
            batch_size=int(options.get("batch_size", 8)),
            learning_rate=float(options.get("learning_rate", 1e-3)),
            limit=options.get("limit"),
            max_chunks_per_file=options.get("max_chunks_per_file"),
            progress_callback=progress_callback,
            cancel_token=options.get("cancel_token"),
        )
    raise ValueError(f"Unknown classifier backend: {backend}")


def detect_classifier_backend(classifier_path):
    suffix = str(classifier_path).lower().rsplit(".", 1)[-1] if "." in str(classifier_path) else ""
    loaders = [_detect_with_torch, _detect_with_joblib] if suffix in {"pt", "pth"} else [_detect_with_joblib, _detect_with_torch]
    for loader in loaders:
        try:
            backend = loader(classifier_path)
            if backend:
                return backend
        except Exception:
            pass

    return "light"


def run_learned_analysis_backend(rows, classifier_path, backend="auto", progress_callback=None, cancel_token=None):
    detected_backend = detect_classifier_backend(classifier_path)
    if backend == "auto":
        backend = detected_backend
    elif detected_backend != backend:
        app_logging.log_info(
            f"Classifier backend mismatch: requested {backend}, detected {detected_backend}; using detected backend."
        )
        backend = detected_backend
    if backend == "light":
        return run_learned_analysis(rows, classifier_path, progress_callback=progress_callback, cancel_token=cancel_token)
    if backend == "heavy":
        from . import heavy_model

        return heavy_model.run_heavy_analysis(rows, classifier_path, progress_callback=progress_callback, cancel_token=cancel_token)
    raise ValueError(f"Unknown classifier backend: {backend}")
