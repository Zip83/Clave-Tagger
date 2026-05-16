import unittest
from unittest.mock import patch

from music_category import heavy_model, learning


class HeavyModelTests(unittest.TestCase):
    def test_expand_samples_uses_chunks_across_whole_file(self):
        samples = [({"file_path": "song.mp3"}, "Rumba")]

        with patch("music_category.heavy_model.chunk_starts_for_file", return_value=[0.0, 30.0, 60.0]):
            expanded = heavy_model.expand_samples_to_chunks(samples)

        self.assertEqual(len(expanded), 3)
        self.assertEqual([item[2] for item in expanded], [0.0, 30.0, 60.0])

    def test_expand_samples_can_limit_chunks_per_file(self):
        samples = [({"file_path": "song.mp3"}, "Rumba")]

        with patch("music_category.heavy_model.chunk_starts_for_file", return_value=[0.0, 30.0, 60.0]):
            expanded = heavy_model.expand_samples_to_chunks(samples, max_chunks_per_file=2)

        self.assertEqual([item[2] for item in expanded], [0.0, 30.0])

    def test_backend_dispatch_calls_heavy_trainer(self):
        rows = [{"file_path": "song.mp3", "id3_grouping_normalized": "Rumba"}]
        expected = {"trained_rows": 1, "labels": ["Rumba"]}

        with patch("music_category.heavy_model.train_heavy_classifier", return_value=expected) as trainer:
            result = learning.train_classifier_backend(rows, "model.pt", backend="heavy", epochs=2, batch_size=3)

        self.assertEqual(result, expected)
        trainer.assert_called_once()
        self.assertEqual(trainer.call_args.kwargs["epochs"], 2)
        self.assertEqual(trainer.call_args.kwargs["batch_size"], 3)

    def test_learned_analysis_uses_detected_heavy_backend_when_dropdown_is_light(self):
        rows = [{"file_path": "song.mp3"}]

        with patch("music_category.learning.detect_classifier_backend", return_value="heavy"):
            with patch("music_category.heavy_model.run_heavy_analysis", return_value=rows) as runner:
                result = learning.run_learned_analysis_backend(rows, "models/learned_heavy.pt", backend="light")

        self.assertIs(result, rows)
        runner.assert_called_once()

    def test_preferred_torch_threads_keeps_one_cpu_free(self):
        self.assertEqual(heavy_model.preferred_torch_threads(cpu_count=8, env_value=""), 4)
        self.assertEqual(heavy_model.preferred_torch_threads(cpu_count=4, env_value=""), 3)
        self.assertEqual(heavy_model.preferred_torch_threads(cpu_count=1, env_value=""), 1)

    def test_preferred_torch_threads_allows_env_override(self):
        self.assertEqual(heavy_model.preferred_torch_threads(cpu_count=8, env_value="6"), 6)
        self.assertEqual(heavy_model.preferred_torch_threads(cpu_count=8, env_value="bad"), 4)


if __name__ == "__main__":
    unittest.main()
