from . import audio_decode, audio_features, config

MODEL_ID = "mtg-upf/discogs-maest-30s-pw-73e-ts"
SAMPLE_RATE = 16000
CLIP_OFFSET = 30.0
CLIP_DURATION = 30.0
DEFAULT_SECONDS_PER_MODEL_FILE = 7.0
DEFAULT_FIRST_MODEL_SECONDS = 45.0
FULL_TRACK_CHUNK_SECONDS = 30.0
MIN_FULL_TRACK_CHUNK_SECONDS = 5.0


def top_score(results, label):
    """Top score."""
    for item in results:
        if item["label"] == label:
            return float(item["score"])
    return 0.0


def score_sum(results, labels):
    """Score sum."""
    return sum(top_score(results, label) for label in labels)


def confidence_from_score(score, margin):
    """Convert model score and margin into a confidence label.

    Args:
        score: Best category score.
        margin: Difference between the best and second-best score.

    Returns:
        One of ``high``, ``medium``, ``low``, or ``review``.
    """
    if score >= 0.035 and margin >= 0.012:
        return "high"
    if score >= 0.018 and margin >= 0.005:
        return "medium"
    if score >= 0.010:
        return "low"
    return "review"


def classify_from_model(results):
    """Map raw audio-model labels to configured categories.

    Args:
        results: Hugging Face audio-classification label score dictionaries.

    Returns:
        Tuple of category, confidence, serialized category scores, and reason.
    """
    scores = {}
    for item in config.category_items():
        category = item.get("category", "")
        if not category:
            continue
        category_score = 0.0
        for label, weight in config.model_label_specs(item):
            category_score += top_score(results, label) * weight
        category_score *= float(item.get("model_weight", 1.0))
        scores[category] = category_score

    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ordered:
        return "Needs review", "review", "", "No categories are configured for model classification."
    best_category, best_score = ordered[0]
    second_score = ordered[1][1] if len(ordered) > 1 else 0.0
    margin = best_score - second_score
    top_labels = ", ".join(f"{item['label']}={item['score']:.4f}" for item in results[:8])
    category_scores = "; ".join(f"{name}={score:.4f}" for name, score in ordered[:6])

    if best_score < 0.010 or margin < 0.0025:
        return "Needs review", "review", category_scores, f"Model did not decide clearly; top labels: {top_labels}; category scores: {category_scores}"

    confidence = confidence_from_score(best_score, margin)
    if config.find_category_item(best_category).get("model_low_confidence") and confidence != "review":
        confidence = "low"
    return best_category, confidence, category_scores, f"MAEST Discogs model; top labels: {top_labels}; category scores: {category_scores}"


def _classifier_results(classifier, audio):
    """Classifier results."""
    return sorted(classifier(audio), key=lambda item: float(item["score"]), reverse=True)


def _average_results(results_by_chunk):
    """Average results."""
    scores = {}
    counts = {}
    for results in results_by_chunk:
        for item in results:
            label = item["label"]
            scores[label] = scores.get(label, 0.0) + float(item["score"])
            counts[label] = counts.get(label, 0) + 1
    chunk_count = max(1, len(results_by_chunk))
    return sorted(
        [{"label": label, "score": score / chunk_count} for label, score in scores.items()],
        key=lambda item: float(item["score"]),
        reverse=True,
    )


def _analyze_clip(classifier, file_path):
    """Analyze clip."""
    (audio, _sample_rate), caught, stderr_output = audio_decode.load_audio(
        file_path,
        sample_rate=SAMPLE_RATE,
        mono=True,
        offset=CLIP_OFFSET,
        duration=CLIP_DURATION,
    )
    if len(audio) == 0:
        raise ValueError("audio decode returned zero samples")
    results = _classifier_results(classifier, audio)
    return audio, results, caught, stderr_output, 1


def _analyze_full_track(classifier, file_path, cancel_token=None):
    """Analyze full track."""
    (audio, _sample_rate), caught, stderr_output = audio_decode.load_audio(
        file_path,
        sample_rate=SAMPLE_RATE,
        mono=True,
        offset=0.0,
        duration=None,
    )
    if len(audio) == 0:
        raise ValueError("audio decode returned zero samples")

    chunk_size = int(SAMPLE_RATE * FULL_TRACK_CHUNK_SECONDS)
    min_chunk_size = int(SAMPLE_RATE * MIN_FULL_TRACK_CHUNK_SECONDS)
    chunk_results = []
    for start in range(0, len(audio), chunk_size):
        if cancel_token:
            cancel_token.throw_if_cancelled()
        chunk = audio[start:start + chunk_size]
        if len(chunk) < min_chunk_size:
            continue
        chunk_results.append(_classifier_results(classifier, chunk))
    if not chunk_results:
        raise ValueError("audio decode returned no usable full-track chunks")
    return audio, _average_results(chunk_results), caught, stderr_output, len(chunk_results)


def analyze_audio(classifier, file_path, full_track=False, cancel_token=None, model_id=MODEL_ID):
    """Analyze one audio file with model labels and Librosa features.

    Args:
        classifier: Hugging Face audio-classification pipeline.
        file_path: MP3 path to analyze.
        full_track: Whether to average predictions across the whole song.
        cancel_token: Optional cooperative cancellation token.
        model_id: Model id used in diagnostic text.

    Returns:
        Row field dictionary for report output.
    """
    if full_track:
        audio, results, caught, stderr_output, chunk_count = _analyze_full_track(classifier, file_path, cancel_token)
    else:
        audio, results, caught, stderr_output, chunk_count = _analyze_clip(classifier, file_path)
    feature_values = audio_features.extract_audio_features(audio, SAMPLE_RATE)
    category, confidence, category_scores, reason = classify_from_model(results)
    scope = f"full track averaged over {chunk_count} chunks" if full_track else "30s clip"
    return {
        "model_audio_suggested_grouping": category,
        "model_audio_confidence": confidence,
        "model_audio_top_labels": ", ".join(f"{item['label']}={item['score']:.4f}" for item in results[:12]),
        "model_audio_category_scores": category_scores,
        "model_audio_features": audio_features.serialize_audio_features(feature_values),
        "model_audio_reason": f"{scope}; model={model_id}; {reason}"
        + ("; warnings: " + " | ".join(str(item.message) for item in caught[:3]) if caught else "")
        + ("; decoder stderr captured, see log" if stderr_output else ""),
    }
