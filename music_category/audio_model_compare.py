import re
import time

from . import app_env, app_logging, audio_model, audio_model_catalog, csv_io, model_runner, progress
from .cancel import CancelledError


BASE_COMPARISON_FIELDS = [
    "source_folder",
    "file_path",
    "file_name",
    "artist",
    "title",
    "album",
    "genre",
    "id3_grouping_normalized",
    "id3_color",
    "tag_suggested_grouping",
    "tag_confidence",
]


def comparison_models():
    """Provide comparison models behavior."""
    return [
        model for model in audio_model_catalog.load_catalog()
        if model.get("status") == "supported"
        and model.get("kind") == "huggingface-audio-classification"
        and model.get("model_id")
    ]


def model_column_prefix(model):
    """Provide model column prefix behavior."""
    name = re.sub(r"[^a-z0-9]+", "_", model.get("name", "").lower()).strip("_")
    return f"m{model.get('rank', 'x')}_{name}"


def comparison_fieldnames(models=None):
    """Provide comparison fieldnames behavior."""
    fields = list(BASE_COMPARISON_FIELDS)
    for model in models if models is not None else comparison_models():
        prefix = model_column_prefix(model)
        fields.extend([
            f"{prefix}_model_id",
            f"{prefix}_grouping",
            f"{prefix}_confidence",
            f"{prefix}_bpm",
            f"{prefix}_reason",
            f"{prefix}_top_labels",
            f"{prefix}_category_scores",
        ])
    return fields


def _base_row(row, models):
    """Provide base row behavior."""
    output = {field: row.get(field, "") for field in BASE_COMPARISON_FIELDS}
    for model in models:
        prefix = model_column_prefix(model)
        output[f"{prefix}_model_id"] = model.get("model_id", "")
        output[f"{prefix}_grouping"] = ""
        output[f"{prefix}_confidence"] = ""
        output[f"{prefix}_bpm"] = ""
        output[f"{prefix}_reason"] = ""
        output[f"{prefix}_top_labels"] = ""
        output[f"{prefix}_category_scores"] = ""
    return output


def _apply_result(output_row, model, result):
    """Apply result."""
    prefix = model_column_prefix(model)
    output_row[f"{prefix}_grouping"] = result.get("model_audio_suggested_grouping", "")
    output_row[f"{prefix}_confidence"] = result.get("model_audio_confidence", "")
    output_row[f"{prefix}_bpm"] = result.get("model_audio_bpm", "")
    output_row[f"{prefix}_reason"] = result.get("model_audio_reason", "")
    output_row[f"{prefix}_top_labels"] = result.get("model_audio_top_labels", "")
    output_row[f"{prefix}_category_scores"] = result.get("model_audio_category_scores", "")


def _error_result(error):
    """Provide error result behavior."""
    return {
        "model_audio_suggested_grouping": "Needs review",
        "model_audio_confidence": "review",
        "model_audio_bpm": "",
        "model_audio_top_labels": "",
        "model_audio_category_scores": "",
        "model_audio_reason": f"audio model comparison error: {error}",
    }


def run_audio_model_comparison(
    rows,
    output_csv,
    progress_path,
    full_track=False,
    models=None,
    progress_callback=None,
    cancel_token=None,
):
    """Run audio model comparison."""
    from transformers import pipeline

    selected_models = models or comparison_models()
    if not selected_models:
        raise ValueError("No supported Hugging Face audio-classification models are configured.")

    cache = progress.load_progress(progress_path)
    comparison_rows = [_base_row(row, selected_models) for row in rows]
    output_by_path = {row.get("file_path", ""): row for row in comparison_rows}
    fieldnames = comparison_fieldnames(selected_models)

    for model_index, model in enumerate(selected_models, start=1):
        if cancel_token:
            cancel_token.throw_if_cancelled()
        model_id = model["model_id"]
        pending = []
        for row in rows:
            key = model_runner.model_cache_key(row, full_track, model_id)
            cached = cache.get(key)
            if cached:
                _apply_result(output_by_path[row.get("file_path", "")], model, cached)
            else:
                pending.append(row)

        scope = "full-track" if full_track else "30s clip"
        message = f"Loading comparison model {model_index}/{len(selected_models)}: {model.get('name')} ({scope})"
        print(message, flush=True)
        if progress_callback:
            progress_callback({
                "event": "model_loading",
                "processed": 0,
                "pending": len(pending),
                "total": len(rows),
                "message": message,
                "model_name": model.get("name", ""),
                "model_id": model_id,
                "model_index": model_index,
                "model_count": len(selected_models),
            })

        if not pending:
            continue

        try:
            classifier = pipeline("audio-classification", model=model_id, trust_remote_code=True, top_k=None)
        except Exception as error:
            app_logging.log_exception(f"Could not load Hugging Face audio model {model_id}", error)
            raise RuntimeError(app_env.friendly_hf_error(error)) from error
        start_all = time.time()
        for processed, row in enumerate(pending, start=1):
            if cancel_token:
                cancel_token.throw_if_cancelled()
            started = time.time()
            if progress_callback:
                progress_callback({
                    "event": "model_file_start",
                    "row": row,
                    "processed": processed - 1,
                    "pending": len(pending),
                    "total": len(rows),
                    "message": f"{model.get('name')}: analyzing {row.get('file_name', '')} ({processed}/{len(pending)})",
                    "model_name": model.get("name", ""),
                    "model_id": model_id,
                    "model_index": model_index,
                    "model_count": len(selected_models),
                })
            try:
                result = audio_model.analyze_audio(
                    classifier,
                    row["file_path"],
                    full_track=full_track,
                    cancel_token=cancel_token,
                    model_id=model_id,
                )
            except CancelledError:
                raise
            except Exception as error:
                app_logging.log_exception(f"audio model comparison error for {row.get('file_path', '')}", error)
                result = _error_result(error)

            cache[model_runner.model_cache_key(row, full_track, model_id)] = result
            progress.save_progress(progress_path, cache)
            _apply_result(output_by_path[row.get("file_path", "")], model, result)

            elapsed = time.time() - started
            average = (time.time() - start_all) / processed
            remaining = average * (len(pending) - processed)
            if progress_callback:
                progress_callback({
                    "event": "model_file_done",
                    "row": row,
                    "result": result,
                    "processed": processed,
                    "pending": len(pending),
                    "total": len(rows),
                    "elapsed": elapsed,
                    "eta_seconds": remaining,
                    "message": f"{model.get('name')}: {row.get('file_name', '')} -> {result['model_audio_suggested_grouping']} ({result['model_audio_confidence']})",
                    "model_name": model.get("name", ""),
                    "model_id": model_id,
                    "model_index": model_index,
                    "model_count": len(selected_models),
                })
            if processed % 5 == 0 and output_csv:
                csv_io.write_csv(output_csv, comparison_rows, fieldnames)

    if output_csv:
        csv_io.write_csv(output_csv, comparison_rows, fieldnames)
    return comparison_rows, fieldnames
