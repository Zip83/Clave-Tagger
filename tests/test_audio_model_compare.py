import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from music_category import audio_model_compare


class AudioModelCompareTests(unittest.TestCase):
    def test_comparison_fieldnames_include_each_model_columns(self):
        models = [
            {"rank": 2, "name": "MAEST 30s", "model_id": "a/model"},
            {"rank": 3, "name": "MAEST 10s", "model_id": "b/model"},
        ]

        fields = audio_model_compare.comparison_fieldnames(models)

        self.assertIn("m2_maest_30s_grouping", fields)
        self.assertIn("m3_maest_10s_confidence", fields)

    def test_run_audio_model_comparison_writes_side_by_side_csv(self):
        rows = [{"file_path": "song.mp3", "file_name": "song.mp3", "tag_suggested_grouping": "Merengue"}]
        models = [
            {"rank": 2, "name": "Model A", "model_id": "a/model"},
            {"rank": 3, "name": "Model B", "model_id": "b/model"},
        ]

        def fake_analyze(_classifier, _file_path, **kwargs):
            model_id = kwargs["model_id"]
            return {
                "model_audio_suggested_grouping": "Merengue" if model_id == "a/model" else "Salsa (Dura)",
                "model_audio_confidence": "high",
                "model_audio_bpm": "144.0",
                "model_audio_top_labels": model_id,
                "model_audio_category_scores": "",
                "model_audio_reason": f"model={model_id}",
            }

        fake_transformers = types.SimpleNamespace(pipeline=lambda *args, **kwargs: object())
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "comparison.csv"
            progress = Path(temp_dir) / "progress.json"
            with patch.dict("sys.modules", {"transformers": fake_transformers}):
                with patch("music_category.audio_model.analyze_audio", side_effect=fake_analyze):
                    comparison_rows, fields = audio_model_compare.run_audio_model_comparison(
                        rows,
                        output,
                        progress,
                        models=models,
                    )
            self.assertTrue(output.exists())

        self.assertIn("m2_model_a_grouping", fields)
        self.assertEqual(comparison_rows[0]["m2_model_a_grouping"], "Merengue")
        self.assertEqual(comparison_rows[0]["m3_model_b_grouping"], "Salsa (Dura)")


if __name__ == "__main__":
    unittest.main()
