import time

from . import app_env, app_logging, audio_model, csv_io, progress, recommendations
from .cancel import CancelledError
from .schemas import DETAIL_FIELDNAMES, MAIN_FIELDNAMES


FULL_TRACK_CACHE_SUFFIX = "::full_track"


def model_cache_key(row, full_track=False, model_id=None):
    """Provide model cache key behavior."""
    file_path = row["file_path"]
    model_id = model_id or audio_model.MODEL_ID
    if not full_track and model_id == audio_model.MODEL_ID:
        return file_path
    scope = FULL_TRACK_CACHE_SUFFIX if full_track else "::clip"
    return f"{file_path}::audio_model={model_id}{scope}"


def cached_model_results(rows, progress_path, full_track=False, model_id=None):
    """Provide cached model results behavior."""
    cached = progress.load_progress(progress_path)
    for row in rows:
        result = cached.get(model_cache_key(row, full_track, model_id))
        if result:
            row.update(result)
    return cached


def run_model_analysis(
    rows,
    progress_path,
    output_csv,
    details_csv,
    mode,
    progress_callback=None,
    recommendation_priority=None,
    cancel_token=None,
    full_track=False,
    model_id=None,
):
    """Run model analysis."""
    from transformers import pipeline

    model_id = (model_id or audio_model.MODEL_ID).strip() or audio_model.MODEL_ID
    cache = cached_model_results(rows, progress_path, full_track, model_id)
    pending = [
        row for row in rows
        if model_cache_key(row, full_track, model_id) not in cache
        and (full_track or model_id != audio_model.MODEL_ID or not row.get("model_audio_reason"))
    ]
    cached_rows = [row for row in rows if row not in pending and row.get("model_audio_reason")]
    if cached_rows and progress_callback:
        progress_callback(
            {
                "event": "model_cached_rows",
                "rows": cached_rows,
                "processed": 0,
                "pending": len(pending),
                "total": len(rows),
                "message": f"Using cached audio results for {len(cached_rows)} tracks; next yellow row is the next uncached track.",
            }
        )
    if not pending:
        print("All model results already loaded from progress cache.", flush=True)
        if progress_callback:
            progress_callback({"event": "model_done", "processed": 0, "pending": 0, "total": len(rows), "message": "All model results already loaded from progress cache."})
        return

    scope = "full-track" if full_track else "30s clip"
    print(f"Loading audio model {model_id} ({scope}) for {len(pending)} of {len(rows)} files...", flush=True)
    if progress_callback:
        progress_callback({"event": "model_loading", "processed": 0, "pending": len(pending), "total": len(rows), "message": f"Loading audio model {model_id} ({scope}) for {len(pending)} of {len(rows)} files..."})
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
        absolute_index = rows.index(row) + 1
        print(f"[{processed}/{len(pending)} pending, {absolute_index}/{len(rows)} total] {row['file_name']}", flush=True)
        if progress_callback:
            progress_callback(
                {
                    "event": "model_file_start",
                    "row": row,
                    "processed": processed - 1,
                    "pending": len(pending),
                    "total": len(rows),
                    "message": f"Analyzing {row['file_name']} ({processed}/{len(pending)})",
                }
            )
        try:
            result = audio_model.analyze_audio(classifier, row["file_path"], full_track=full_track, cancel_token=cancel_token, model_id=model_id)
        except CancelledError:
            raise
        except Exception as error:
            app_logging.log_exception(f"audio model analysis error for {row.get('file_path', '')}", error)
            result = {
                "model_audio_suggested_grouping": "Needs review",
                "model_audio_confidence": "review",
                "model_audio_bpm": "",
                "model_audio_top_labels": "",
                "model_audio_category_scores": "",
                "model_audio_reason": f"audio model analysis error: {error}",
            }
        row.update(result)
        cache[model_cache_key(row, full_track, model_id)] = result
        progress.save_progress(progress_path, cache)
        recommendations.apply_recommendations(rows, mode, recommendation_priority)

        elapsed = time.time() - started
        average = (time.time() - start_all) / processed
        remaining = average * (len(pending) - processed)
        print(
            f"  -> {result['model_audio_suggested_grouping']} ({result['model_audio_confidence']}), "
            f"bpm={result['model_audio_bpm']}, file={elapsed:.1f}s, eta={progress.format_duration(remaining)}",
            flush=True,
        )
        if progress_callback:
            progress_callback(
                {
                    "event": "model_file_done",
                    "row": row,
                    "result": result,
                    "processed": processed,
                    "pending": len(pending),
                    "total": len(rows),
                    "elapsed": elapsed,
                    "eta_seconds": remaining,
                    "message": f"{row['file_name']} -> {result['model_audio_suggested_grouping']} ({result['model_audio_confidence']}), bpm={result['model_audio_bpm']}",
                }
            )
        if processed % 5 == 0:
            if output_csv:
                csv_io.write_csv(output_csv, rows, MAIN_FIELDNAMES)
            if details_csv:
                csv_io.write_csv(details_csv, rows, DETAIL_FIELDNAMES)
