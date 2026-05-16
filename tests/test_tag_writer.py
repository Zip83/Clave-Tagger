import unittest
from unittest.mock import patch

from music_category import config, tag_writer


class TagWriterTests(unittest.TestCase):
    def setUp(self):
        config.load_category_config("category_config.json")

    def test_plan_tag_changes_skips_needs_review(self):
        rows = [{"file_path": "song.mp3", "target_grouping": "Needs review"}]

        changes, skipped = tag_writer.plan_tag_changes(rows, grouping_column="target_grouping")

        self.assertEqual(changes, [])
        self.assertEqual(skipped, [("song.mp3", "target grouping is Needs review")])

    def test_plan_tag_changes_maps_grouping_and_color(self):
        rows = [{"file_path": "song.mp3", "target_grouping": "Rumba", "target_color": "Rumba"}]
        metadata = {"id3_grouping": "", "id3_color": ""}

        with patch("music_category.tag_writer.id3_tags.read_id3", return_value=metadata):
            changes, skipped = tag_writer.plan_tag_changes(rows, grouping_column="target_grouping", color_column="target_color")

        self.assertEqual(skipped, [])
        self.assertEqual(changes, [("song.mp3", {"grouping": ("", "#Rumba"), "color": ("", "#FFD166")})])

    def test_plan_clear_tag_changes_clears_grouping_and_color(self):
        rows = [{"file_path": "song.mp3", "file_name": "song.mp3"}]
        metadata = {"id3_grouping": "#Rumba", "id3_color": "#FFD166"}

        with patch("music_category.tag_writer.id3_tags.read_id3", return_value=metadata):
            changes, skipped = tag_writer.plan_clear_tag_changes(rows)

        self.assertEqual(skipped, [])
        self.assertEqual(
            changes,
            [("song.mp3", {"clear_grouping": ("#Rumba", ""), "clear_color": ("#FFD166", "")})],
        )

    def test_apply_clear_tag_changes_calls_delete_helpers_only_when_apply(self):
        changes = [("song.mp3", {"clear_grouping": ("#Rumba", ""), "clear_color": ("#FFD166", "")})]
        logs = []

        with patch("music_category.tag_writer.id3_tags.clear_id3_grouping") as clear_grouping:
            with patch("music_category.tag_writer.id3_tags.clear_id3_color") as clear_color:
                tag_writer.apply_tag_changes(changes, apply_changes=False, log=logs.append)
                clear_grouping.assert_not_called()
                clear_color.assert_not_called()

                tag_writer.apply_tag_changes(changes, apply_changes=True, log=logs.append)
                clear_grouping.assert_called_once_with("song.mp3")
                clear_color.assert_called_once_with("song.mp3")


if __name__ == "__main__":
    unittest.main()
