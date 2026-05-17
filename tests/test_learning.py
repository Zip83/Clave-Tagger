import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from music_category.cancel import CancelToken, CancelledError
from music_category import audio_features, heavy_model, learning


class LearningTests(unittest.TestCase):
    def test_parse_score_pairs(self):
        scores = learning.parse_score_pairs("Rumba=0.0600; Salsa (Dura)=0.0200; broken")

        self.assertEqual(scores["Rumba"], 0.06)
        self.assertEqual(scores["Salsa (Dura)"], 0.02)
        self.assertNotIn("broken", scores)

    def test_learned_features_include_model_scores_labels_and_audio_features(self):
        row = {
            "model_audio_category_scores": "Rumba=0.0600; Salsa (Dura)=0.0200",
            "model_audio_top_labels": "Latin---Rumba=0.0400, Latin---Salsa=0.0200",
            "model_audio_suggested_grouping": "Rumba",
            "tag_suggested_grouping": "Rumba",
            "model_audio_features": "audio_feature:mfcc_01:mean=0.250000; audio_feature:percussive_ratio=1.500000",
        }

        features = learning.learned_features(row)

        self.assertEqual(features["category_score:Rumba"], 0.06)
        self.assertEqual(features["maest_label:Latin---Rumba"], 0.04)
        self.assertEqual(features["model_guess:Rumba"], 1.0)
        self.assertEqual(features["tag_guess:Rumba"], 1.0)
        self.assertEqual(features["audio_feature:mfcc_01:mean"], 0.25)
        self.assertEqual(features["audio_feature:percussive_ratio"], 1.5)
        self.assertFalse(any("bpm" in key.lower() for key in features))

    def test_audio_features_round_trip_from_serialized_details(self):
        values = {"audio_feature:mfcc_01:mean": 0.125, "audio_feature:percussive_ratio": 2.0}

        serialized = audio_features.serialize_audio_features(values)

        self.assertEqual(audio_features.parse_audio_features(serialized), values)

    def test_truth_category_uses_first_normalized_grouping(self):
        row = {"id3_grouping_normalized": "#Rumba; #Salsa"}

        self.assertEqual(learning.truth_category(row), "Rumba")

    def test_light_training_reports_progress(self):
        rows = [
            {"id3_grouping_normalized": "Rumba", "model_audio_category_scores": "Rumba=0.5", "tag_suggested_grouping": "Rumba"},
            {"id3_grouping_normalized": "Merengue", "model_audio_category_scores": "Merengue=0.5", "tag_suggested_grouping": "Merengue"},
            {"id3_grouping_normalized": "", "model_audio_category_scores": "Rumba=0.1"},
        ]
        events = []

        with tempfile.TemporaryDirectory() as temp_dir:
            result = learning.train_classifier_backend(
                rows,
                str(Path(temp_dir) / "model.joblib"),
                backend="light",
                progress_callback=events.append,
            )

        self.assertEqual(result["trained_rows"], 2)
        self.assertIn("training_start", [event["event"] for event in events])
        self.assertIn("training_fit_start", [event["event"] for event in events])
        self.assertIn("training_done", [event["event"] for event in events])
        row_events = [event for event in events if event["event"] == "training_file_done"]
        self.assertTrue(all("row" in event for event in row_events))
        self.assertIn("needs_review", [event.get("status") for event in row_events])
        start_events = [event for event in events if event["event"] == "training_file_start"]
        self.assertEqual(len(start_events), len(rows))
        self.assertTrue(all(event.get("status") == "current" for event in start_events))

    def test_heavy_training_reports_batch_progress_and_loss(self):
        events = []
        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "a.mp3"
            second = Path(temp_dir) / "b.mp3"
            first.write_bytes(b"fake")
            second.write_bytes(b"fake")
            rows = [
                {"file_path": str(first), "id3_grouping_normalized": "Rumba"},
                {"file_path": str(second), "id3_grouping_normalized": "Merengue"},
            ]

            def fake_model(num_classes):
                import torch.nn as nn

                return nn.Sequential(nn.Flatten(), nn.Linear(64 * 938, num_classes))

            def fake_tensor(_file_path, clip_offset=0.0, clip_duration=30.0):
                import torch

                return torch.zeros(1, 64, 938)

            with patch("music_category.heavy_model.AudioCnn.create", side_effect=fake_model):
                with patch("music_category.heavy_model.load_file_tensor", side_effect=fake_tensor):
                    with patch("music_category.heavy_model.chunk_starts_for_file", return_value=[0.0]):
                        result = heavy_model.train_heavy_classifier(
                            rows,
                            str(Path(temp_dir) / "model.pt"),
                            epochs=1,
                            batch_size=1,
                            progress_callback=events.append,
                        )

        self.assertEqual(result["trained_rows"], 2)
        self.assertEqual(result["label_counts"], {"Merengue": 1, "Rumba": 1})
        self.assertEqual(result["chunk_label_counts"], {"Merengue": 1, "Rumba": 1})
        batch_events = [event for event in events if event["event"] == "training_batch_done"]
        self.assertTrue(batch_events)
        self.assertIn("loss", batch_events[0])
        self.assertIn("heavy_epoch_done", [event["event"] for event in events])
        scan_events = [event for event in events if event["event"] == "training_scan_file"]
        self.assertTrue(all("row" in event for event in scan_events))
        self.assertTrue(all(event.get("status") == "done" for event in scan_events))
        current_events = [event for event in events if event["event"] == "training_scan_file_start"]
        self.assertTrue(all(event.get("after_status") == "done" for event in current_events))
        self.assertTrue(all(event.get("status") == "current" for event in current_events))
        self.assertIn("training_setup_start", [event["event"] for event in events])
        self.assertIn("training_setup_model", [event["event"] for event in events])

    def test_heavy_training_can_cancel_during_setup(self):
        events = []
        token = CancelToken()

        def cancel_on_setup(event):
            events.append(event)
            if event["event"] == "training_setup_start":
                token.cancel()

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(CancelledError):
                heavy_model.train_heavy_classifier(
                    [],
                    str(Path(temp_dir) / "model.pt"),
                    progress_callback=cancel_on_setup,
                    cancel_token=token,
                )

        self.assertTrue(token.cancelled)
        self.assertIn("training_setup_start", [event["event"] for event in events])

    def test_heavy_training_skips_undecodable_chunks(self):
        events = []
        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "a.mp3"
            second = Path(temp_dir) / "b.mp3"
            first.write_bytes(b"fake")
            second.write_bytes(b"fake")
            rows = [
                {"file_path": str(first), "id3_grouping_normalized": "Rumba"},
                {"file_path": str(second), "id3_grouping_normalized": "Merengue"},
            ]

            def fake_model(num_classes):
                import torch.nn as nn

                return nn.Sequential(nn.Flatten(), nn.Linear(64 * 938, num_classes))

            def fake_tensor(file_path, clip_offset=0.0, clip_duration=30.0):
                import torch

                if str(file_path).endswith("a.mp3"):
                    raise RuntimeError("decode failed")
                return torch.zeros(1, 64, 938)

            with patch("music_category.heavy_model.AudioCnn.create", side_effect=fake_model):
                with patch("music_category.heavy_model.load_file_tensor", side_effect=fake_tensor):
                    with patch("music_category.heavy_model.chunk_starts_for_file", return_value=[0.0]):
                        result = heavy_model.train_heavy_classifier(
                            rows,
                            str(Path(temp_dir) / "model.pt"),
                            epochs=1,
                            batch_size=2,
                            progress_callback=events.append,
                        )

        self.assertEqual(result["trained_rows"], 2)
        event_names = [event["event"] for event in events]
        self.assertIn("training_done", event_names)
        self.assertTrue({"training_batch_done", "training_batch_skipped"} & set(event_names))


if __name__ == "__main__":
    unittest.main()
