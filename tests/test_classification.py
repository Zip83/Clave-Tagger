import unittest

from music_category import audio_model, config, report, text_classifier


class ClassificationTests(unittest.TestCase):
    def setUp(self):
        config.load_category_config("category_config.json")

    def test_text_classifier_maps_guaguanco_to_rumba(self):
        row = {
            "genre": "Latin Rumba",
            "artist": "",
            "title": "Guaguancó para bailar",
            "album": "",
            "file_name": "guaguanco.mp3",
        }

        category, confidence, reason = text_classifier.classify_from_tags(row)

        self.assertEqual(category, "Rumba")
        self.assertEqual(confidence, "high")
        self.assertIn("rumba", reason.lower())

    def test_audio_model_maps_guaguanco_to_rumba_not_conga_or_salsa(self):
        results = [
            {"label": "Latin---Guaguanco", "score": 0.045},
            {"label": "Latin---Rumba", "score": 0.030},
            {"label": "Latin---Salsa", "score": 0.020},
        ]

        category, confidence, scores, _reason = audio_model.classify_from_model(results, bpm=110)

        self.assertEqual(category, "Rumba")
        self.assertNotIn("Conga=0.075", scores)
        self.assertIn(confidence, {"high", "medium", "low"})

    def test_recommendation_prefers_learned_model_tags_by_default(self):
        row = {
            "tag_suggested_grouping": "Salsa (Dura)",
            "tag_confidence": "medium",
            "model_audio_suggested_grouping": "Rumba",
            "model_audio_confidence": "medium",
            "learned_suggested_grouping": "Timba",
            "learned_confidence": "high",
        }

        category, source, confidence = report.choose_recommendation(row, "all")

        self.assertEqual(category, "Timba")
        self.assertEqual(source, "learned")
        self.assertEqual(confidence, "high")

    def test_both_mode_ignores_learned_and_prefers_stronger_tag_signal(self):
        row = {
            "tag_suggested_grouping": "Merengue",
            "tag_confidence": "high",
            "model_audio_suggested_grouping": "Rumba",
            "model_audio_confidence": "medium",
            "learned_suggested_grouping": "Timba",
            "learned_confidence": "high",
        }

        category, source, _confidence = report.choose_recommendation(row, "both")

        self.assertEqual(category, "Merengue")
        self.assertEqual(source, "tags")

    def test_filename_category_prefix_is_high_confidence(self):
        row = {
            "genre": "",
            "artist": "",
            "title": "",
            "album": "",
            "file_name": "Merengue - El Amor Nacio Asi.mp3",
            "source_folder": "",
        }

        category, confidence, _reason = text_classifier.classify_from_tags(row)

        self.assertEqual(category, "Merengue")
        self.assertEqual(confidence, "high")

    def test_folder_name_is_not_a_classification_signal(self):
        row = {
            "genre": "",
            "artist": "",
            "title": "",
            "album": "",
            "file_name": "01-Bandido.mp3",
            "source_folder": r"C:\Music\Kizomba",
        }

        category, confidence, _reason = text_classifier.classify_from_tags(row)

        self.assertEqual(category, "Needs review")
        self.assertEqual(confidence, "review")

    def test_generic_salsa_does_not_override_specific_timba(self):
        row = {
            "genre": "Salsa",
            "artist": "",
            "title": "Salsa Con Timba",
            "album": "",
            "file_name": "01 - Salsa Con Timba.mp3",
            "source_folder": r"C:\Music\Salsa",
        }

        category, confidence, _reason = text_classifier.classify_from_tags(row)

        self.assertEqual(category, "Timba")
        self.assertEqual(confidence, "medium")

    def test_generic_son_artist_name_does_not_force_son_cubano(self):
        row = {
            "genre": "",
            "artist": "Son Caribe",
            "title": "Negrita",
            "album": "",
            "file_name": "Son Caribe - Negrita.mp3",
            "source_folder": "",
        }

        category, confidence, _reason = text_classifier.classify_from_tags(row)

        self.assertEqual(category, "Needs review")
        self.assertEqual(confidence, "review")


if __name__ == "__main__":
    unittest.main()
