import unittest

from music_category import recommendations


class RecommendationTests(unittest.TestCase):
    def test_sources_for_both_mode_excludes_learned(self):
        sources = recommendations.recommendation_sources_for_mode("both", "learned,tags,model")

        self.assertEqual(sources, ["tags", "model"])

    def test_invalid_priority_falls_back_to_default(self):
        self.assertEqual(recommendations.parse_priority("unknown"), ["manual", "learned", "tags", "model"])

    def test_high_confidence_tag_prevents_obvious_model_override(self):
        row = {
            "learned_suggested_grouping": "Needs review",
            "learned_confidence": "review",
            "model_audio_suggested_grouping": "Rumba",
            "model_audio_confidence": "medium",
            "tag_suggested_grouping": "Merengue",
            "tag_confidence": "high",
        }

        category, source, confidence = recommendations.choose_recommendation(row, "all")

        self.assertEqual((category, source, confidence), ("Merengue", "tags", "high"))

    def test_high_confidence_tag_beats_medium_learned_by_default(self):
        row = {
            "learned_suggested_grouping": "Bachata",
            "learned_confidence": "medium",
            "tag_suggested_grouping": "Cha cha cha",
            "tag_confidence": "high",
        }

        category, source, confidence = recommendations.choose_recommendation(row, "all")

        self.assertEqual((category, source, confidence), ("Cha cha cha", "tags", "high"))

    def test_medium_tag_beats_high_model_by_default(self):
        row = {
            "learned_suggested_grouping": "Needs review",
            "learned_confidence": "review",
            "model_audio_suggested_grouping": "Salsa Fusion/Pop",
            "model_audio_confidence": "high",
            "tag_suggested_grouping": "Merengue",
            "tag_confidence": "medium",
        }

        category, source, confidence = recommendations.choose_recommendation(row, "all")

        self.assertEqual((category, source, confidence), ("Merengue", "tags", "medium"))

    def test_low_model_is_not_recommended_by_default(self):
        row = {
            "model_audio_suggested_grouping": "Salsaton",
            "model_audio_confidence": "low",
            "tag_suggested_grouping": "Needs review",
            "tag_confidence": "review",
        }

        category, source, confidence = recommendations.choose_recommendation(row, "both")

        self.assertEqual((category, source, confidence), ("Needs review", "none", "review"))

    def test_model_only_is_not_recommended_in_combined_mode_by_default(self):
        row = {
            "model_audio_suggested_grouping": "Salsa Fusion/Pop",
            "model_audio_confidence": "high",
            "tag_suggested_grouping": "Needs review",
            "tag_confidence": "review",
        }

        category, source, confidence = recommendations.choose_recommendation(row, "both")

        self.assertEqual((category, source, confidence), ("Needs review", "none", "review"))

    def test_model_mode_still_uses_model_prediction(self):
        row = {
            "model_audio_suggested_grouping": "Salsa Fusion/Pop",
            "model_audio_confidence": "high",
            "tag_suggested_grouping": "Needs review",
            "tag_confidence": "review",
        }

        category, source, confidence = recommendations.choose_recommendation(row, "model")

        self.assertEqual((category, source, confidence), ("Salsa Fusion/Pop", "model", "high"))

    def test_manual_override_wins(self):
        row = {
            "manual_grouping": "Rumba",
            "learned_suggested_grouping": "Merengue",
            "learned_confidence": "high",
            "model_audio_suggested_grouping": "Salsa Fusion/Pop",
            "model_audio_confidence": "high",
            "tag_suggested_grouping": "Cumbia",
            "tag_confidence": "high",
        }

        category, source, confidence = recommendations.choose_recommendation(row, "all")

        self.assertEqual((category, source, confidence), ("Rumba", "manual", "high"))


if __name__ == "__main__":
    unittest.main()
