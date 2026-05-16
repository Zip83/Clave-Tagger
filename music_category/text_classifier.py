from . import config


DEFAULT_TEXT_RULES = {
    "use_source_folder": False,
    "minimum_score": 35,
    "conflict_margin": 35,
    "confidence_thresholds": {"high": 100, "medium": 70},
    "weights": {
        "genre_strong": 100,
        "genre_weak": 20,
        "file_prefix_strong": 100,
        "file_prefix_weak": 20,
        "folder_strong": 100,
        "folder_weak": 20,
        "text_strong": 70,
        "text_weak": 10,
    },
}


def _text_rules():
    configured = config.text_classification_config()
    rules = dict(DEFAULT_TEXT_RULES)
    rules["weights"] = {**DEFAULT_TEXT_RULES["weights"], **configured.get("weights", {})}
    rules["confidence_thresholds"] = {
        **DEFAULT_TEXT_RULES["confidence_thresholds"],
        **configured.get("confidence_thresholds", {}),
    }
    for key in ("use_source_folder", "minimum_score", "conflict_margin"):
        if key in configured:
            rules[key] = configured[key]
    return rules


def _split_weak_hits(item, hits):
    weak_patterns = {config.normalize_text(pattern) for pattern in item.get("weak_tag_patterns", [])}
    strong = [hit for hit in hits if config.normalize_text(hit) not in weak_patterns]
    weak = [hit for hit in hits if config.normalize_text(hit) in weak_patterns]
    return strong, weak


def _add_hits(score, reasons, label, strong_hits, weak_hits, strong_weight, weak_weight):
    if strong_hits:
        score += strong_weight
        reasons.append(f"{label} matched {', '.join(str(hit) for hit in strong_hits[:3])}")
    if weak_hits:
        score += weak_weight
        reasons.append(f"{label} weakly matched {', '.join(str(hit) for hit in weak_hits[:3])}")
    return score


def classify_from_tags(row):
    rules = _text_rules()
    weights = rules["weights"]
    genre = config.normalize_text(row.get("genre", ""))
    file_text = config.normalize_text(row.get("file_name", ""))
    folder_segments = []
    if rules.get("use_source_folder"):
        folder_segments = [
            config.normalize_text(part)
            for part in str(row.get("source_folder", "")).replace("\\", "/").split("/")
            if part
        ]
    all_text = config.normalize_text(
        " ".join(
            [
                row.get("artist", ""),
                row.get("title", ""),
                row.get("album", ""),
                row.get("file_name", ""),
            ]
        )
    )

    candidates = []
    for item in config.category_items():
        category = item.get("category", "")
        patterns = item.get("tag_patterns", [])
        if not category or not patterns:
            continue
        score = 0
        reasons = []
        category_markers = [category, item.get("grouping", ""), *item.get("aliases", []), *patterns]
        normalized_markers = list(dict.fromkeys(config.normalize_text(marker) for marker in category_markers if marker))
        genre_hits = [pattern for pattern in patterns if genre and config.pattern_matches(genre, pattern)]
        file_prefix_hits = [
            marker
            for marker in normalized_markers
            if marker and (file_text == marker or file_text.startswith(marker + " "))
        ]
        folder_hits = [marker for marker in normalized_markers if marker and marker in folder_segments]
        text_hits = [pattern for pattern in patterns if config.pattern_matches(all_text, pattern)]
        strong_genre_hits, weak_genre_hits = _split_weak_hits(item, genre_hits)
        strong_prefix_hits, weak_prefix_hits = _split_weak_hits(item, file_prefix_hits)
        strong_folder_hits, weak_folder_hits = _split_weak_hits(item, folder_hits)
        strong_text_hits, weak_text_hits = _split_weak_hits(item, text_hits)
        score = _add_hits(score, reasons, "genre/tag", strong_genre_hits, weak_genre_hits, weights["genre_strong"], weights["genre_weak"])
        score = _add_hits(score, reasons, "filename prefix", strong_prefix_hits, weak_prefix_hits, weights["file_prefix_strong"], weights["file_prefix_weak"])
        score = _add_hits(score, reasons, "source folder", strong_folder_hits, weak_folder_hits, weights["folder_strong"], weights["folder_weak"])
        score = _add_hits(score, reasons, "title/artist/album/file", strong_text_hits, weak_text_hits, weights["text_strong"], weights["text_weak"])
        if score:
            candidates.append((score, category, "; ".join(reasons)))

    if not candidates:
        return "Needs review", "review", "No clear signal in ID3 tags or filename."

    candidates.sort(reverse=True)
    best_score, best_category, reason = candidates[0]
    if best_score < int(rules["minimum_score"]):
        return "Needs review", "review", f"Only weak tag signals for {best_category}: {reason}."
    if len(candidates) > 1 and best_score - candidates[1][0] < int(rules["conflict_margin"]):
        return "Needs review", "review", f"Conflicting tag signals: {best_category} and {candidates[1][1]}."

    thresholds = rules["confidence_thresholds"]
    confidence = "high" if best_score >= int(thresholds["high"]) else "medium" if best_score >= int(thresholds["medium"]) else "low"
    return best_category, confidence, reason
