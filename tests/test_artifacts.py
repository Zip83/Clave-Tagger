import csv
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from music_category import artifacts


class ArtifactTests(unittest.TestCase):
    def test_detect_existing_artifacts_for_analyze(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "report.csv"
            details = root / "details.csv"
            progress = root / "progress.json"
            output.write_text("", encoding="utf-8")
            details.write_text("", encoding="utf-8")
            progress.write_text("{}", encoding="utf-8")
            options = SimpleNamespace(
                output_csv=str(output),
                details_csv=str(details),
                progress_json=str(progress),
                use_details=True,
            )

            found = artifacts.detect_existing_artifacts("analyze", options)

        self.assertEqual([path.name for path in found], ["progress.json", "report.csv", "details.csv"])

    def test_backup_artifacts_moves_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "report.csv"
            source.write_text("old", encoding="utf-8")

            moved = artifacts.backup_artifacts([source], root / "backups", timestamp="20260516-120000")

            target = root / "backups" / "20260516-120000" / "report.csv"
            self.assertFalse(source.exists())
            self.assertTrue(target.exists())
            self.assertEqual(moved[str(source)], str(target))

    def test_merge_report_artifacts_only_merges_prediction_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = root / "report.csv"
            with report.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["file_path", "artist", "id3_grouping", "recommended_grouping", "target_grouping"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "file_path": "song.mp3",
                        "artist": "Old Artist",
                        "id3_grouping": "#Old",
                        "recommended_grouping": "Son Cubano",
                        "target_grouping": "#Son_Cubano",
                    }
                )
            rows = [{"file_path": "song.mp3", "artist": "Current Artist", "id3_grouping": ""}]

            merged = artifacts.merge_report_artifacts(rows, report)

        self.assertEqual(merged, 1)
        self.assertEqual(rows[0]["artist"], "Current Artist")
        self.assertEqual(rows[0]["id3_grouping"], "")
        self.assertEqual(rows[0]["recommended_grouping"], "Son Cubano")
        self.assertEqual(rows[0]["target_grouping"], "#Son_Cubano")

    def test_prepare_artifacts_fresh_starts_with_missing_original(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "model.pt"
            output.write_text("old", encoding="utf-8")
            options = SimpleNamespace(
                classifier_output=str(output),
                artifact_policy="fresh",
                artifact_backup_dir=str(root / "backups"),
            )

            moved = artifacts.prepare_artifacts("train", options)

            self.assertEqual(len(moved), 1)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
