import unittest

from mutagen.id3 import GRP1, TIT1, TXXX

from music_category import id3_tags


class Id3TagReadTests(unittest.TestCase):
    def test_grouping_ignores_grp1(self):
        tags = {
            "GRP1": GRP1(encoding=3, text=["#Cha_cha_cha"]),
        }

        grouping = ""
        for key in ("TIT1", "TXXX:GROUPING", "TXXX:Grouping", "TXXX:grouping"):
            values = id3_tags.tag_text_values(tags, key)
            if values:
                grouping = values[-1]
                break

        self.assertEqual(grouping, "")

    def test_grouping_reads_tit1(self):
        tags = {"TIT1": TIT1(encoding=3, text=["#Son_Cubano"])}

        self.assertEqual(id3_tags.tag_text_values(tags, "TIT1"), ["#Son_Cubano"])

    def test_color_uses_last_value_from_multi_value_color_frame(self):
        tags = {"TXXX:Color": TXXX(encoding=3, desc="Color", text=["cyan", "#999999"])}

        self.assertEqual(id3_tags.read_color(tags), "#999999")


if __name__ == "__main__":
    unittest.main()
