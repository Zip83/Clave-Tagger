import csv
import tempfile
import unittest
from pathlib import Path

from music_category import config, playlist_matcher


class PlaylistMatcherTests(unittest.TestCase):
    def tearDown(self):
        config.load_category_config("category_config.json")

    def test_playlist_name_son_maps_to_son_cubano(self):
        config.load_category_config("category_config.json")

        self.assertEqual(playlist_matcher.category_from_playlist_name("Son"), "Son Cubano")

    def test_reads_virtualdj_xml_playlist(self):
        config.load_category_config("category_config.json")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "Son.xml"
            path.write_text(
                '<VirtualFolder><song artist="Compay Segundo" title="Chan Chan" album="Buena Vista" songlength="270.0" /></VirtualFolder>',
                encoding="utf-8",
            )

            tracks = playlist_matcher.read_label_playlist(path)

        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0].category, "Son Cubano")
        self.assertEqual(tracks[0].grouping, "#Son_Cubano")
        self.assertEqual(tracks[0].artist, "Compay Segundo")
        self.assertEqual(tracks[0].title, "Chan Chan")

    def test_reads_virtualdj_database_style_song_tags(self):
        config.load_category_config("category_config.json")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "Son.xml"
            path.write_text(
                '<VirtualDJ_Database><Song FilePath="tidal://track/1"><Tags Author="Ibrahim Ferrer" Title="Candela" Album="Buena Vista" Year="1997" /></Song></VirtualDJ_Database>',
                encoding="utf-8",
            )

            tracks = playlist_matcher.read_label_playlist(path)

        self.assertEqual(tracks[0].artist, "Ibrahim Ferrer")
        self.assertEqual(tracks[0].title, "Candela")
        self.assertEqual(tracks[0].year, "1997")

    def test_reads_csv_playlist(self):
        config.load_category_config("category_config.json")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "Son.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["artist", "title", "album", "year"])
                writer.writeheader()
                writer.writerow({"artist": "Ibrahim Ferrer", "title": "Candela", "album": "Buena Vista", "year": "1997"})

            tracks = playlist_matcher.read_label_playlist(path)

        self.assertEqual(tracks[0].category, "Son Cubano")
        self.assertEqual(tracks[0].year, "1997")

    def test_strict_match_fills_target_grouping_for_high_confidence(self):
        config.load_category_config("category_config.json")
        label = playlist_matcher.label_track_from_values("Son.csv", "Son", "", "Compay Segundo", "Chan Chan", "Buena Vista", "1997")
        rows = [
            {
                "file_path": "C:/Music/Compay Segundo - Chan Chan.mp3",
                "file_name": "Compay Segundo - Chan Chan.mp3",
                "artist": "Compay Segundo",
                "title": "Chan Chan",
                "album": "Buena Vista Social Club 1997",
            }
        ]

        matches = playlist_matcher.match_label_tracks([label], rows)

        self.assertEqual(matches[0]["match_confidence"], "high")
        self.assertEqual(matches[0]["target_grouping"], "#Son_Cubano")
        self.assertEqual(matches[0]["target_color"], "#999999")

    def test_bad_artist_does_not_fill_target_grouping(self):
        config.load_category_config("category_config.json")
        label = playlist_matcher.label_track_from_values("Son.csv", "Son", "", "Compay Segundo", "Chan Chan")
        rows = [
            {
                "file_path": "C:/Music/Other Artist - Chan Chan.mp3",
                "file_name": "Other Artist - Chan Chan.mp3",
                "artist": "Other Artist",
                "title": "Chan Chan",
                "album": "",
            }
        ]

        matches = playlist_matcher.match_label_tracks([label], rows)

        self.assertEqual(matches[0]["match_confidence"], "review")
        self.assertEqual(matches[0]["target_grouping"], "")

    def test_ambiguous_match_stays_review(self):
        config.load_category_config("category_config.json")
        label = playlist_matcher.label_track_from_values("Son.csv", "Son", "", "Ibrahim Ferrer", "Candela")
        rows = [
            {"file_path": "A.mp3", "file_name": "A.mp3", "artist": "Ibrahim Ferrer", "title": "Candela", "album": ""},
            {"file_path": "B.mp3", "file_name": "B.mp3", "artist": "Ibrahim Ferrer", "title": "Candela", "album": ""},
        ]

        matches = playlist_matcher.match_label_tracks([label], rows)

        self.assertEqual(matches[0]["match_confidence"], "review")
        self.assertIn("ambiguous", matches[0]["match_reason"])


if __name__ == "__main__":
    unittest.main()
