import csv
import os
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from music_category import app_env, app_paths, audio_decode, calibration, classifier_presets, gui_services, gui_settings, light_model, model_runner, overrides, power


class HardeningTests(unittest.TestCase):
    def test_default_runtime_paths_live_in_runtime_folders(self):
        self.assertEqual(app_paths.DEFAULT_MAIN_CSV, Path("reports") / "report_main.csv")
        self.assertEqual(app_paths.DEFAULT_DETAILS_CSV, Path("reports") / "report_details.csv")
        self.assertEqual(app_paths.DEFAULT_MODEL_COMPARISON_CSV, Path("reports") / "model_comparison.csv")
        self.assertEqual(app_paths.DEFAULT_PROGRESS_JSON, Path("progress") / "music_category_report_progress.json")
        self.assertEqual(app_paths.DEFAULT_LIGHT_CLASSIFIER, Path("models") / "learned_light.joblib")
        self.assertEqual(app_paths.DEFAULT_HEAVY_CLASSIFIER, Path("models") / "learned_heavy.pt")
        self.assertEqual(app_paths.DEFAULT_LOG_FILE, Path("logs") / "clavetagger.log")
        self.assertEqual(app_paths.DEFAULT_GUI_SETTINGS, Path("settings") / "gui_settings.json")

    def test_gitignore_excludes_runtime_artifacts(self):
        text = Path(".gitignore").read_text(encoding="utf-8")

        for pattern in [".venv*/", ".env", "reports/*", "progress/*", "logs/*", "models/*", "settings/*", "*.joblib", "*.pt", "uv.exe", "build/", "dist/", "release/", "*.spec"]:
            self.assertIn(pattern, text)

    def test_gui_settings_round_trip_known_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "gui_settings.json"
            values = {"mode": "learned", "only_missing_grouping": True, "source_paths": ["C:/Music"]}

            gui_settings.save_settings(values, path)
            loaded = gui_settings.load_settings(path)

        self.assertEqual(loaded["mode"], "learned")
        self.assertTrue(loaded["only_missing_grouping"])
        self.assertEqual(loaded["source_paths"], ["C:/Music"])

    def test_gui_service_options_include_cli_parity_fields(self):
        report_fields = gui_services.ReportOptions.__dataclass_fields__
        train_fields = gui_services.TrainOptions.__dataclass_fields__

        for name in ["classifier_input", "classifier_output", "prediction_column", "truth_column", "overrides_csv", "log_file", "env_file", "write_after_report", "audio_model_id", "model_full_track", "model_comparison_csv"]:
            self.assertIn(name, report_fields)
        for name in ["classifier_input", "classifier_output", "classifier_preset", "training_source", "heavy_learning_rate", "heavy_max_files", "heavy_max_chunks_per_file", "env_file"]:
            self.assertIn(name, train_fields)

    def test_classifier_preset_values_are_expected(self):
        preset = classifier_presets.get("heavy-fast")

        self.assertEqual(preset["backend"], "heavy")
        self.assertEqual(preset["epochs"], 3)
        self.assertEqual(preset["max_chunks_per_file"], 2)

    def test_env_file_loads_hf_token_without_overwriting_existing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".env"
            path.write_text("HF_TOKEN=from-file\nOTHER=value\n", encoding="utf-8")
            with patch.dict(os.environ, {"HF_TOKEN": "already-set"}, clear=True):
                status = app_env.load_env_file(path)

                self.assertEqual(os.environ["HF_TOKEN"], "already-set")
                self.assertEqual(os.environ["OTHER"], "value")
                self.assertIn("HF_TOKEN", status["skipped_existing"])
                self.assertNotIn("from-file", app_env.env_status_message(status))

    def test_friendly_hf_error_for_auth_failures(self):
        message = app_env.friendly_hf_error(RuntimeError("403 Forbidden gated model"))

        self.assertIn("HF_TOKEN", message)

    def test_power_non_windows_is_noop(self):
        with patch("music_category.power.platform.system", return_value="Linux"):
            self.assertFalse(power.prevent_sleep())
            self.assertFalse(power.allow_sleep())

    def test_manual_override_beats_existing_predictions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "manual_overrides.csv"
            row = {"file_path": "song.mp3", "file_name": "song.mp3", "artist": "Artist", "title": "Title"}

            overrides.upsert_override(path, row, "Rumba", "#FFD166", "fixed")
            rows = [{"file_path": "song.mp3", "recommended_grouping": "Merengue"}]
            overrides.apply_overrides(rows, path)

        self.assertEqual(rows[0]["manual_grouping"], "Rumba")
        self.assertEqual(rows[0]["manual_color"], "#FFD166")
        self.assertEqual(rows[0]["manual_note"], "fixed")

    def test_light_training_skips_empty_grouping(self):
        rows = [
            {"id3_grouping_normalized": "", "model_audio_category_scores": "Rumba=0.1"},
            {"id3_grouping_normalized": "Rumba", "model_audio_category_scores": "Rumba=0.1"},
        ]

        samples = [light_model.truth_category(row) for row in rows]

        self.assertEqual(samples, ["", "Rumba"])

    def test_calibration_writes_proposed_config_not_input_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "report.csv"
            tuned_path = Path(temp_dir) / "category_config.tuned.json"
            mismatch_path = Path(temp_dir) / "mismatches.csv"
            with report_path.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=["file_path", "id3_grouping_normalized", "model_audio_suggested_grouping"])
                writer.writeheader()
                for index in range(3):
                    writer.writerow({"file_path": f"{index}.mp3", "id3_grouping_normalized": "Merengue", "model_audio_suggested_grouping": "Salsa Fusion/Pop"})

            with patch("music_category.csv_io.id3_tags.read_id3", return_value={}):
                tuned, examples = calibration.calibrate_from_csv(report_path, tuned_path, mismatch_output=mismatch_path)

            self.assertTrue(tuned_path.exists())
            self.assertTrue(mismatch_path.exists())
            self.assertEqual(len(examples), 3)
            self.assertIn("calibration_notes", tuned)
            self.assertTrue(json.loads(tuned_path.read_text(encoding="utf-8")))

    def test_audio_decode_error_marks_row_for_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            progress_path = Path(temp_dir) / "progress.json"
            rows = [{"file_path": "bad.mp3", "file_name": "bad.mp3"}]

            fake_transformers = types.SimpleNamespace(pipeline=lambda *args, **kwargs: object())
            with patch.dict(sys.modules, {"transformers": fake_transformers}):
                with patch("music_category.audio_model.analyze_audio", side_effect=ValueError("decode failed")):
                    model_runner.run_model_analysis(rows, progress_path, "", "", "model")

        self.assertEqual(rows[0]["model_audio_suggested_grouping"], "Needs review")
        self.assertEqual(rows[0]["model_audio_confidence"], "review")
        self.assertIn("decode failed", rows[0]["model_audio_reason"])

    def test_audio_model_cache_key_includes_non_default_model_and_scope(self):
        row = {"file_path": "song.mp3"}

        self.assertEqual(model_runner.model_cache_key(row), "song.mp3")
        self.assertIn("custom/model", model_runner.model_cache_key(row, model_id="custom/model"))
        self.assertIn("full_track", model_runner.model_cache_key(row, full_track=True))

    def test_decode_capture_suppresses_native_stderr(self):
        def noisy_operation():
            os.write(2, b"native decoder noise")
            return "ok"

        result, _caught, stderr_output = audio_decode.run_with_decode_capture("song.mp3", noisy_operation)

        self.assertEqual(result, "ok")
        self.assertIn("native decoder noise", stderr_output)

    def test_decode_capture_preserves_original_exception(self):
        def broken_operation():
            os.write(2, b"native decoder failure")
            raise ValueError("decode exploded")

        with self.assertRaisesRegex(ValueError, "decode exploded"):
            audio_decode.run_with_decode_capture("song.mp3", broken_operation)


if __name__ == "__main__":
    unittest.main()
