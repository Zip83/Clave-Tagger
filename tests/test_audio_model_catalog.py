import tempfile
import unittest
from pathlib import Path

from music_category import audio_model, audio_model_catalog
from music_category.cli_parser import build_parser


class AudioModelCatalogTests(unittest.TestCase):
    def test_catalog_loads_in_rank_order(self):
        models = audio_model_catalog.load_catalog()
        ranks = [model["rank"] for model in models]

        self.assertGreaterEqual(len(models), 4)
        self.assertEqual(ranks, sorted(ranks))

    def test_catalog_contains_default_maest_model(self):
        models = audio_model_catalog.supported_models()
        model_ids = {model.get("model_id") for model in models}

        self.assertIn(audio_model.MODEL_ID, model_ids)

    def test_catalog_formatter_mentions_practical_rank(self):
        text = audio_model_catalog.format_catalog()

        self.assertIn("MAEST", text)
        self.assertIn("practical preset order", text)

    def test_find_by_label_round_trips(self):
        model = audio_model_catalog.load_catalog()[1]
        label = audio_model_catalog.preset_label(model)

        self.assertEqual(audio_model_catalog.find_by_label(label), model)

    def test_missing_catalog_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "missing.json"

            self.assertEqual(audio_model_catalog.load_catalog(path), [])

    def test_cli_accepts_list_audio_models_without_source(self):
        args = build_parser().parse_args(["--list-audio-models"])

        self.assertTrue(args.list_audio_models)


if __name__ == "__main__":
    unittest.main()
