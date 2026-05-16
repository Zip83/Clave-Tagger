from . import config


def parse_score_pairs(value):
    scores = {}
    for part in (value or "").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, score = part.rsplit("=", 1)
        try:
            scores[name.strip()] = float(score)
        except ValueError:
            continue
    return scores


def parse_top_label_scores(value):
    scores = {}
    for part in (value or "").split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, score = part.rsplit("=", 1)
        try:
            scores[name.strip()] = float(score)
        except ValueError:
            continue
    return scores


def learned_features(row):
    features = {}
    for category, score in parse_score_pairs(row.get("model_audio_category_scores", "")).items():
        features[f"category_score:{category}"] = score
    for label, score in parse_top_label_scores(row.get("model_audio_top_labels", "")).items():
        features[f"maest_label:{label}"] = score
    if row.get("model_audio_suggested_grouping"):
        features[f"model_guess:{row['model_audio_suggested_grouping']}"] = 1.0
    if row.get("tag_suggested_grouping"):
        features[f"tag_guess:{row['tag_suggested_grouping']}"] = 1.0
    try:
        bpm = float(row.get("model_audio_bpm", "") or 0)
    except ValueError:
        bpm = 0.0
    if bpm:
        features["bpm"] = bpm / 220.0
    return features


def truth_category(row, truth_column="id3_grouping_normalized"):
    truth = row.get(truth_column, "")
    values = [part.strip() for part in truth.split(";") if part.strip()]
    values = [config.normalize_value_to_category(value) for value in values]
    values = [value for value in values if value and value != "Needs review"]
    return values[0] if values else ""


def train_classifier(rows, output_path, truth_column="id3_grouping_normalized", progress_callback=None, cancel_token=None):
    from joblib import dump
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    samples = []
    labels = []
    skipped_no_truth = 0
    skipped_no_features = 0
    total = len(rows)
    if progress_callback:
        progress_callback(
            {
                "event": "training_start",
                "backend": "light",
                "processed": 0,
                "total": total,
                "message": f"Training light classifier: scanning {total} rows",
            }
        )
    for index, row in enumerate(rows, start=1):
        if cancel_token:
            cancel_token.throw_if_cancelled()
        if progress_callback:
            progress_callback(
                {
                    "event": "training_file_start",
                    "backend": "light",
                    "row": row,
                    "status": "current",
                    "after_status": "done",
                    "processed": index - 1,
                    "total": total,
                    "message": f"Light training {index}/{total}: {row.get('file_name') or row.get('file_path') or 'track'}",
                }
            )
        label = truth_category(row, truth_column)
        if not label:
            skipped_no_truth += 1
            if progress_callback:
                progress_callback(
                    {
                        "event": "training_file_done",
                        "backend": "light",
                        "row": row,
                        "status": "needs_review",
                        "processed": index,
                        "total": total,
                        "message": f"Light training {index}/{total}: skipped empty Grouping",
                    }
                )
            continue
        features = learned_features(row)
        if not features:
            skipped_no_features += 1
            if progress_callback:
                progress_callback(
                    {
                        "event": "training_file_done",
                        "backend": "light",
                        "row": row,
                        "status": "needs_review",
                        "processed": index,
                        "total": total,
                        "message": f"Light training {index}/{total}: skipped missing model features",
                    }
                )
            continue
        samples.append(features)
        labels.append(label)
        if progress_callback:
            progress_callback(
                {
                    "event": "training_file_done",
                    "backend": "light",
                    "row": row,
                    "status": "done",
                    "processed": index,
                    "total": total,
                    "message": f"Light training {index}/{total}: collected {label}",
                }
            )

    unique_labels = sorted(set(labels))
    if len(samples) < 2 or len(unique_labels) < 2:
        raise ValueError(
            "Classifier training needs at least two labeled rows from at least two categories "
            "with model feature columns. To add another style later, retrain from the whole tagged "
            "library or a cumulative CSV that contains the old categories plus the new one."
        )

    if progress_callback:
        progress_callback(
            {
                "event": "training_fit_start",
                "backend": "light",
                "processed": total,
                "total": total,
                "message": f"Fitting light classifier with {len(samples)} rows and {len(unique_labels)} labels",
            }
        )
    if cancel_token:
        cancel_token.throw_if_cancelled()
    pipeline = Pipeline(
        [
            ("vectorizer", DictVectorizer(sparse=True)),
            ("classifier", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ]
    )
    pipeline.fit(samples, labels)
    payload = {
        "pipeline": pipeline,
        "labels": unique_labels,
        "trained_rows": len(samples),
        "skipped_no_truth": skipped_no_truth,
        "skipped_no_features": skipped_no_features,
        "config_categories": [item.get("category", "") for item in config.category_items()],
    }
    if progress_callback:
        progress_callback(
            {
                "event": "training_save_start",
                "backend": "light",
                "processed": total,
                "total": total,
                "message": f"Saving light classifier to {output_path}",
            }
        )
    dump(payload, output_path)
    if progress_callback:
        progress_callback(
            {
                "event": "training_done",
                "backend": "light",
                "processed": total,
                "total": total,
                "message": f"Light classifier trained: rows={len(samples)}, labels={len(unique_labels)}",
            }
        )
    return payload


def run_learned_analysis(rows, classifier_path, progress_callback=None, cancel_token=None):
    from joblib import load

    payload = load(classifier_path)
    pipeline = payload["pipeline"] if isinstance(payload, dict) else payload
    classes = list(pipeline.named_steps["classifier"].classes_)
    total = len(rows)
    for index, row in enumerate(rows, start=1):
        if cancel_token:
            cancel_token.throw_if_cancelled()
        if progress_callback:
            progress_callback(
                {
                    "event": "learned_file_start",
                    "row": row,
                    "processed": index - 1,
                    "pending": total,
                    "total": total,
                    "message": f"Classifying {row.get('file_name', '')} ({index}/{total})",
                }
            )
        features = learned_features(row)
        if not features:
            result = {
                "learned_suggested_grouping": "Needs review",
                "learned_confidence": "review",
                "learned_reason": "No model feature columns were available for the learned classifier.",
            }
        else:
            probabilities = pipeline.predict_proba([features])[0]
            best_index = max(range(len(probabilities)), key=lambda pos: probabilities[pos])
            probability = float(probabilities[best_index])
            category = classes[best_index]
            confidence = "high" if probability >= 0.70 else "medium" if probability >= 0.50 else "low" if probability >= 0.35 else "review"
            if confidence == "review":
                category = "Needs review"
            result = {
                "learned_suggested_grouping": category,
                "learned_confidence": confidence,
                "learned_reason": f"Local classifier probability={probability:.3f}; trained labels={', '.join(classes)}",
            }
        row.update(result)
        if progress_callback:
            progress_callback(
                {
                    "event": "learned_file_done",
                    "row": row,
                    "processed": index,
                    "pending": total,
                    "total": total,
                    "message": f"{row.get('file_name', '')} -> {result['learned_suggested_grouping']} ({result['learned_confidence']})",
                }
            )
