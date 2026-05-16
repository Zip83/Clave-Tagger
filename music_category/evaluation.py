def evaluate_rows(rows, prediction_column, truth_column):
    """Evaluate rows."""
    comparable = []
    for row in rows:
        truth = row.get(truth_column, "")
        prediction = row.get(prediction_column, "")
        if truth and prediction:
            comparable.append((truth, prediction, row))

    matches = 0
    for truth, prediction, _row in comparable:
        truth_values = [part.strip() for part in truth.split(";") if part.strip()]
        if prediction in truth_values:
            matches += 1

    total = len(comparable)
    accuracy = matches / total if total else 0
    print(f"Compared rows: {total}")
    print(f"Matches: {matches}")
    print(f"Accuracy: {accuracy:.1%}")
    return total, matches, accuracy


def evaluate_available_predictions(rows, truth_column):
    """Evaluate available predictions."""
    columns = [
        ("tags", "tag_suggested_grouping"),
        ("model", "model_audio_suggested_grouping"),
        ("learned", "learned_suggested_grouping"),
        ("recommended", "recommended_grouping"),
    ]
    print("Prediction comparison:")
    for label, column in columns:
        comparable = [row for row in rows if row.get(column) and row.get(truth_column)]
        if not comparable:
            continue
        matches = 0
        for row in comparable:
            truth_values = [part.strip() for part in row.get(truth_column, "").split(";") if part.strip()]
            if row.get(column) in truth_values:
                matches += 1
        accuracy = matches / len(comparable) if comparable else 0
        print(f"  {label:11s} {column:32s} rows={len(comparable):4d} matches={matches:4d} accuracy={accuracy:.1%}")
