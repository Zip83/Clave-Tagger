import json
from collections import Counter, defaultdict
from pathlib import Path

from . import config, csv_io


def row_truth_values(row, truth_column):
    return [part.strip() for part in row.get(truth_column, "").split(";") if part.strip()]


def analyze_mismatches(rows, truth_column="id3_grouping_normalized"):
    summary = defaultdict(Counter)
    examples = []
    for row in rows:
        truths = row_truth_values(row, truth_column)
        if not truths:
            continue
        for source, column in (
            ("tag", "tag_suggested_grouping"),
            ("model", "model_audio_suggested_grouping"),
            ("learned", "learned_suggested_grouping"),
            ("recommended", "recommended_grouping"),
        ):
            prediction = row.get(column, "")
            if prediction and prediction not in truths:
                truth = truths[0]
                summary[source][(prediction, truth)] += 1
                if len(examples) < 200:
                    examples.append(
                        {
                            "file_path": row.get("file_path", ""),
                            "file_name": row.get("file_name", ""),
                            "source": source,
                            "prediction": prediction,
                            "truth": truth,
                        }
                    )
    return summary, examples


def tuned_config_from_summary(summary):
    tuned = json.loads(json.dumps(config.CATEGORY_CONFIG, ensure_ascii=False))
    notes = []
    for source, counter in summary.items():
        for (prediction, truth), count in counter.items():
            if source == "model" and count >= 3:
                for item in tuned.get("categories", []):
                    if item.get("category") == prediction:
                        current = float(item.get("model_weight", 1.0))
                        item["model_weight"] = round(max(0.25, current - min(0.2, count * 0.02)), 3)
                        notes.append(f"Reduced model_weight for {prediction}; often predicted instead of {truth} ({count} rows).")
                    if item.get("category") == truth:
                        current = float(item.get("model_weight", 1.0))
                        item["model_weight"] = round(min(1.5, current + min(0.15, count * 0.015)), 3)
                        notes.append(f"Increased model_weight for {truth}; often missed as {prediction} ({count} rows).")
    tuned["calibration_notes"] = notes
    return tuned


def calibrate_from_csv(input_csv, calibration_output, mismatch_output=None, truth_column="id3_grouping_normalized"):
    rows = csv_io.read_rows_from_csv(input_csv)
    summary, examples = analyze_mismatches(rows, truth_column)
    tuned = tuned_config_from_summary(summary)
    output_path = Path(calibration_output)
    output_path.write_text(json.dumps(tuned, ensure_ascii=False, indent=2), encoding="utf-8")
    if mismatch_output:
        csv_io.write_csv(mismatch_output, examples, ["file_path", "file_name", "source", "prediction", "truth"])
    return tuned, examples
