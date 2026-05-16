import json
import tempfile
import unittest
from pathlib import Path

from music_category import config


class CategoryConfigTests(unittest.TestCase):
    def tearDown(self):
        config.load_category_config("category_config.json")

    def test_loads_grouping_color_aliases_from_config(self):
        payload = {
            "categories": [
                {
                    "category": "Rumba",
                    "grouping": "#Rumba",
                    "color": "#FFD166",
                    "aliases": ["#Guaguanco", "Guaguancó"],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "category_config.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            config.load_category_config(path)

        self.assertEqual(config.normalize_value_to_category("#Rumba"), "Rumba")
        self.assertEqual(config.normalize_value_to_category("#Guaguanco"), "Rumba")
        self.assertEqual(config.normalize_value_to_category("Guaguancó"), "Rumba")
        self.assertEqual(config.category_to_grouping("Rumba"), "#Rumba")
        self.assertEqual(config.category_to_color("Rumba"), "#FFD166")

    def test_normalize_grouping_deduplicates_multiple_values(self):
        config.load_category_config("category_config.json")

        self.assertEqual(config.normalize_grouping("#Rumba; Guaguancó; #Rumba"), "Rumba")


    def test_text_classification_rules_are_loaded_from_config(self):
        config.load_category_config("category_config.json")
        rules = config.text_classification_config()

        self.assertFalse(rules["use_source_folder"])
        self.assertIn("weights", rules)
        salsa = config.find_category_item("Salsa (Dura)")
        self.assertIn("salsa", salsa["weak_tag_patterns"])


if __name__ == "__main__":
    unittest.main()
