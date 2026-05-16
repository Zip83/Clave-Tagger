import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from music_category import gui_services


class GuiServicesTests(unittest.TestCase):
    def test_run_report_can_use_preloaded_rows(self):
        options = gui_services.ReportOptions(
            source_paths=[],
            input_csv="",
            output_csv="report.csv",
            details_csv="",
            model_comparison_csv="reports/model_comparison.csv",
            progress_json="progress.json",
            config_path="category_config.json",
            classifier_path="",
            classifier_input="",
            classifier_output="models/learned_light.joblib",
            classifier_backend="light",
            recommendation_priority="tags",
            mode="tags",
            audio_model_id="mtg-upf/discogs-maest-30s-pw-73e-ts",
            model_full_track=False,
            use_details=False,
            prediction_column="recommended_grouping",
            truth_column="id3_grouping_normalized",
            overrides_csv="",
            log_file="logs/clavetagger.log",
            env_file=".env",
            write_after_report=False,
            value_column="target_grouping",
            color_column_after_report="",
        )
        rows = [{"file_path": "song.mp3", "tag_suggested_grouping": "Rumba", "tag_confidence": "high"}]
        status_events = []

        with patch("music_category.gui_services.load_rows", side_effect=AssertionError("should not reload")):
            with patch("music_category.gui_services.core.write_csv") as write_csv:
                result_rows, status = gui_services.run_report(options, rows=rows, status_callback=status_events.append)

        self.assertIs(result_rows, rows)
        self.assertEqual(rows[0]["recommended_grouping"], "Rumba")
        self.assertIn("report.csv", status)
        self.assertIn("Analyze: 1 tracks ready.", status_events)
        self.assertIn("Analyze: preparing tag/text recommendations...", status_events)
        self.assertIn("Analyze: writing main CSV to report.csv...", status_events)
        write_csv.assert_called_once()

    def test_preview_rows_reports_loading_progress(self):
        progress_events = []
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "song.mp3"
            path.write_bytes(b"fake")
            metadata = {
                "artist": "",
                "title": "",
                "album": "",
                "genre": "",
                "id3_grouping": "",
                "id3_grouping_normalized": "",
                "id3_color": "",
                "id3_color_normalized": "",
            }
            with patch("music_category.id3_tags.read_id3", return_value=metadata):
                rows = gui_services.preview_rows([temp_dir], "", "category_config.json", progress_callback=progress_events.append)

        self.assertEqual(len(rows), 1)
        self.assertEqual(progress_events[0]["event"], "load_start")
        self.assertEqual(progress_events[-1]["event"], "load_file_done")
        self.assertEqual(progress_events[-1]["processed"], 1)

    def test_run_write_tags_reports_plan_and_apply_progress(self):
        progress_events = []
        status_events = []
        logs = []
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "report.csv"
            csv_path.write_text("file_path,file_name,target_grouping\nsong.mp3,song.mp3,Rumba\n", encoding="utf-8")
            options = gui_services.WriteOptions(
                csv_path=str(csv_path),
                config_path="category_config.json",
                grouping_column="target_grouping",
                color_column="",
                apply_write=False,
                only_when_empty=False,
            )
            metadata = {"id3_grouping": "", "id3_color": ""}
            with patch("music_category.id3_tags.read_id3", return_value=metadata):
                changes, skipped = gui_services.run_write_tags(
                    options,
                    logs.append,
                    progress_callback=progress_events.append,
                    status_callback=status_events.append,
                )

        self.assertEqual(len(changes), 1)
        self.assertEqual(skipped, 0)
        event_names = [event["event"] for event in progress_events]
        self.assertIn("load_start", event_names)
        self.assertIn("write_plan_file_done", event_names)
        self.assertIn("write_apply_file_done", event_names)
        self.assertTrue(any("planning" in event.lower() for event in status_events))

    def test_run_write_rows_uses_in_memory_rows_without_reading_csv(self):
        rows = [{"file_path": "song.mp3", "file_name": "song.mp3", "target_grouping": "Rumba"}]
        logs = []
        metadata = {"id3_grouping": "", "id3_color": ""}

        with patch("music_category.gui_services.core.read_rows_from_csv", side_effect=AssertionError("should not read csv")):
            with patch("music_category.tag_writer.id3_tags.read_id3", return_value=metadata):
                changes, skipped = gui_services.run_write_rows(
                    rows,
                    "category_config.json",
                    "target_grouping",
                    "",
                    apply_write=False,
                    log_callback=logs.append,
                )

        self.assertEqual(skipped, 0)
        self.assertEqual(changes, [("song.mp3", {"grouping": ("", "#Rumba")})])

    def test_run_clear_rows_plans_grouping_and_color_deletes(self):
        rows = [{"file_path": "song.mp3", "file_name": "song.mp3"}]
        logs = []
        metadata = {"id3_grouping": "#Rumba", "id3_color": "#FFD166"}

        with patch("music_category.tag_writer.id3_tags.read_id3", return_value=metadata):
            changes, skipped = gui_services.run_clear_rows(
                rows,
                "category_config.json",
                apply_write=False,
                log_callback=logs.append,
            )

        self.assertEqual(skipped, 0)
        self.assertEqual(
            changes,
            [("song.mp3", {"clear_grouping": ("#Rumba", ""), "clear_color": ("#FFD166", "")})],
        )

    def test_run_report_can_analyze_only_rows_missing_grouping(self):
        options = gui_services.ReportOptions(
            source_paths=[],
            input_csv="",
            output_csv="report.csv",
            details_csv="",
            model_comparison_csv="reports/model_comparison.csv",
            progress_json="progress.json",
            config_path="category_config.json",
            classifier_path="",
            classifier_input="",
            classifier_output="models/learned_light.joblib",
            classifier_backend="light",
            recommendation_priority="tags",
            mode="model",
            audio_model_id="mtg-upf/discogs-maest-30s-pw-73e-ts",
            model_full_track=False,
            use_details=False,
            prediction_column="recommended_grouping",
            truth_column="id3_grouping_normalized",
            overrides_csv="",
            log_file="logs/clavetagger.log",
            env_file=".env",
            write_after_report=False,
            value_column="target_grouping",
            color_column_after_report="",
            only_missing_grouping=True,
        )
        rows = [
            {"file_path": "done.mp3", "file_name": "done.mp3", "id3_grouping_normalized": "Salsa (Dura)"},
            {"file_path": "todo.mp3", "file_name": "todo.mp3", "id3_grouping_normalized": ""},
        ]

        with patch("music_category.gui_services.core.run_model_analysis") as run_model:
            with patch("music_category.gui_services.core.write_csv"):
                gui_services.run_report(options, rows=rows)

        analyzed_rows = run_model.call_args.args[0]
        self.assertEqual([row["file_name"] for row in analyzed_rows], ["todo.mp3"])
        self.assertTrue(rows[0]["_analysis_skipped_existing_grouping"])
        self.assertFalse(rows[1]["_analysis_skipped_existing_grouping"])

    def test_plan_write_tags_maps_category_to_configured_grouping(self):
        options = gui_services.WriteOptions(
            csv_path="report.csv",
            config_path="category_config.json",
            grouping_column="target_grouping",
            color_column="",
            apply_write=False,
            only_when_empty=False,
        )
        rows = [{"file_path": "song.mp3", "target_grouping": "Rumba"}]
        metadata = {"id3_grouping": "", "id3_color": ""}

        with patch("music_category.gui_services.core.read_rows_from_csv", return_value=rows):
            with patch("music_category.tag_writer.id3_tags.read_id3", return_value=metadata):
                changes, skipped = gui_services.plan_write_tags(options)

        self.assertEqual(skipped, 0)
        self.assertEqual(changes, [("song.mp3", {"grouping": ("", "#Rumba")})])

    def test_plan_write_tags_requires_a_target_column(self):
        options = gui_services.WriteOptions(
            csv_path="report.csv",
            config_path="category_config.json",
            grouping_column="",
            color_column="",
            apply_write=False,
            only_when_empty=False,
        )

        with self.assertRaises(ValueError):
            gui_services.plan_write_tags(options)

    def test_apply_manual_corrections_updates_selected_rows_only(self):
        rows = [
            {"file_path": "one.mp3", "file_name": "one.mp3", "recommended_grouping": "Needs review"},
            {"file_path": "two.mp3", "file_name": "two.mp3", "recommended_grouping": "Needs review"},
        ]

        updated = gui_services.apply_manual_corrections(
            rows,
            ["two.mp3"],
            "Son Cubano",
            "",
            "fixed in bulk",
            "",
            mode="all",
            priority="",
            config_path="category_config.json",
        )

        self.assertEqual(updated, 1)
        self.assertEqual(rows[0].get("target_grouping", ""), "")
        self.assertEqual(rows[1]["target_grouping"], "Son Cubano")
        self.assertEqual(rows[1]["target_color"], "#999999")
        self.assertEqual(rows[1]["manual_note"], "fixed in bulk")
        self.assertEqual(rows[1]["recommended_grouping"], "Son Cubano")
        self.assertEqual(rows[1]["recommended_source"], "manual")

    def test_sync_classifier_paths_switches_only_default_paths(self):
        path, output = gui_services.sync_classifier_paths_for_backend(
            "heavy",
            "models/learned_light.joblib",
            "models/learned_light.joblib",
        )

        self.assertEqual(path, "models\\learned_heavy.pt")
        self.assertEqual(output, "models\\learned_heavy.pt")

        path, output = gui_services.sync_classifier_paths_for_backend(
            "light",
            "models/custom-heavy.pt",
            "models/custom-heavy.pt",
        )

        self.assertEqual(path, "models/custom-heavy.pt")
        self.assertEqual(output, "models/custom-heavy.pt")

        path, output = gui_services.sync_classifier_paths_for_backend(
            "auto",
            "models/learned_heavy.pt",
            "models/learned_heavy.pt",
        )

        self.assertEqual(path, "models/learned_heavy.pt")
        self.assertEqual(output, "models/learned_heavy.pt")

    def test_dependency_state_disables_irrelevant_learned_audio_inputs(self):
        state = gui_services.dependency_state(
            mode="learned",
            classifier_backend="heavy",
            use_details=False,
            write_after_report=False,
        )

        self.assertFalse(state["audio_model"])
        self.assertFalse(state["audio_progress"])
        self.assertTrue(state["learned_classifier"])
        self.assertFalse(state["details_csv"])
        self.assertTrue(state["heavy_training"])
        self.assertFalse(state["light_training"])
        self.assertFalse(state["write_after_report_columns"])

    def test_dependency_state_enables_model_audio_without_learned_classifier(self):
        state = gui_services.dependency_state(
            mode="model",
            classifier_backend="light",
            use_details=True,
            write_after_report=True,
        )

        self.assertTrue(state["audio_model"])
        self.assertTrue(state["audio_progress"])
        self.assertFalse(state["learned_classifier"])
        self.assertTrue(state["details_csv"])
        self.assertTrue(state["light_training"])
        self.assertFalse(state["heavy_training"])
        self.assertTrue(state["write_after_report_columns"])

    def test_rows_without_source_folders_removes_only_matching_sources(self):
        rows = [
            {"file_name": "a.mp3", "source_folder": "C:/Music/A"},
            {"file_name": "b.mp3", "source_folder": "C:/Music/B"},
            {"file_name": "csv.mp3", "source_folder": ""},
        ]

        kept = gui_services.rows_without_source_folders(rows, ["C:/Music/A"])

        self.assertEqual([row["file_name"] for row in kept], ["b.mp3", "csv.mp3"])

    def test_match_label_playlist_updates_loaded_rows_and_writes_csv(self):
        rows = [
            {
                "file_path": "C:/Music/Chan Chan.mp3",
                "file_name": "Chan Chan.mp3",
                "artist": "Compay Segundo",
                "title": "Chan Chan",
                "album": "Buena Vista Social Club 1997",
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            playlist = Path(temp_dir) / "Son.csv"
            output = Path(temp_dir) / "matches.csv"
            playlist.write_text(
                "artist,title,album,year\nCompay Segundo,Chan Chan,Buena Vista,1997\n",
                encoding="utf-8",
            )
            options = gui_services.LabelPlaylistOptions(
                playlist_paths=[str(playlist)],
                explicit_category="Son Cubano",
                min_score=0.94,
                output_csv=str(output),
                config_path="category_config.json",
            )

            match_rows, summary = gui_services.match_label_playlists(options, rows)

            self.assertEqual(summary["matched"], 1)
            self.assertEqual(summary["updated"], 1)
            self.assertEqual(rows[0]["target_grouping"], "#Son_Cubano")
            self.assertEqual(rows[0]["target_color"], "#999999")
            self.assertEqual(match_rows[0]["match_status"], "matched")
            self.assertIn("match_status", output.read_text(encoding="utf-8"))

    def test_match_label_playlist_review_rows_do_not_update_targets(self):
        rows = [
            {
                "file_path": "C:/Music/Chan Chan.mp3",
                "file_name": "Chan Chan.mp3",
                "artist": "Compay Segundo",
                "title": "Chan Chan",
                "album": "Buena Vista Social Club 1997",
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            playlist = Path(temp_dir) / "Son.csv"
            output = Path(temp_dir) / "matches.csv"
            playlist.write_text(
                "artist,title,album,year\nCompay Segundo,Chan Chan,Buena Vista,1997\n",
                encoding="utf-8",
            )
            options = gui_services.LabelPlaylistOptions(
                playlist_paths=[str(playlist)],
                explicit_category="Son Cubano",
                min_score=1.0,
                output_csv=str(output),
                config_path="category_config.json",
            )

            match_rows, summary = gui_services.match_label_playlists(options, rows)

            self.assertEqual(summary["matched"], 0)
            self.assertEqual(summary["review"], 1)
            self.assertEqual(summary["updated"], 0)
            self.assertEqual(rows[0].get("target_grouping", ""), "")
            self.assertEqual(match_rows[0]["match_status"], "review")


if __name__ == "__main__":
    unittest.main()
