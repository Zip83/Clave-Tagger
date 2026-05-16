def parse_priority(priority):
    """Parse priority."""
    if not priority:
        return ["manual", "learned", "tags", "model"]
    values = [part.strip().lower() for part in priority.split(",") if part.strip()]
    allowed = {"manual", "learned", "model", "tags"}
    return [value for value in values if value in allowed] or ["manual", "learned", "tags", "model"]


def recommendation_sources_for_mode(mode, priority=None):
    """Provide recommendation sources for mode behavior."""
    if mode == "tags":
        return ["tags"]
    if mode == "model":
        return ["model"]
    if mode == "learned":
        return ["learned"]
    if mode == "both":
        return [source for source in parse_priority(priority) if source in {"model", "tags"}]
    return parse_priority(priority)


def confidence_rank(confidence):
    """Provide confidence rank behavior."""
    return {"high": 3, "medium": 2, "low": 1, "review": 0, "": 0}.get(confidence, 0)


def confidence_aware_sources(row, mode):
    """Provide confidence aware sources behavior."""
    if row.get("manual_grouping"):
        return ["manual"]
    candidates = []
    if mode in {"learned", "all"}:
        candidates.append(("learned", confidence_rank(row.get("learned_confidence", ""))))
    if mode in {"tags", "both", "all"}:
        candidates.append(("tags", confidence_rank(row.get("tag_confidence", ""))))
    if mode == "model":
        candidates.append(("model", confidence_rank(row.get("model_audio_confidence", ""))))
    candidates = [(source, rank) for source, rank in candidates if rank >= 2]
    confidence_order = {
        ("tags", 3): 0,
        ("learned", 3): 1,
        ("model", 3): 2,
        ("tags", 2): 3,
        ("learned", 2): 4,
        ("model", 2): 5,
    }
    candidates.sort(key=lambda item: confidence_order.get((item[0], item[1]), 99))
    return [source for source, _rank in candidates]


def choose_recommendation(row, mode, priority=None):
    """Choose recommendation."""
    values = {
        "manual": (row.get("manual_grouping", ""), "high" if row.get("manual_grouping") else ""),
        "learned": (row.get("learned_suggested_grouping", ""), row.get("learned_confidence", "")),
        "model": (row.get("model_audio_suggested_grouping", ""), row.get("model_audio_confidence", "")),
        "tags": (row.get("tag_suggested_grouping", ""), row.get("tag_confidence", "")),
    }
    sources = recommendation_sources_for_mode(mode, priority) if priority else confidence_aware_sources(row, mode)
    for source in sources:
        category, confidence = values[source]
        if category and category != "Needs review":
            return category, source, confidence
    return "Needs review", "none", "review"


def apply_recommendations(rows, mode, priority=None):
    """Apply recommendations."""
    for row in rows:
        category, source, confidence = choose_recommendation(row, mode, priority)
        row["recommended_grouping"] = category
        row["recommended_source"] = source
        row["recommended_confidence"] = confidence
        row.setdefault("target_grouping", "")
