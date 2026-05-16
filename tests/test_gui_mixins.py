import unittest

from music_category.gui_playback import GuiPlaybackMixin
from music_category.gui_table import GuiTableMixin


class _Var:
    """Small stand-in for Tk variables used by GUI mixin tests."""

    def __init__(self, value=""):
        """Initialize the fake variable with a value."""
        self.value = value

    def get(self):
        """Return the stored fake variable value."""
        return self.value

    def set(self, value):
        """Update the stored fake variable value."""
        self.value = value


class _TableHarness(GuiTableMixin):
    """Minimal object exposing the state required by GuiTableMixin."""

    def __init__(self):
        """Initialize fake table state for non-Tk unit tests."""
        self.table_filter = _Var("All tracks")
        self.pending_tag_paths = set()


class _PlaybackHarness(GuiPlaybackMixin):
    """Minimal object exposing playback helpers that do not require Tk."""


class GuiMixinTests(unittest.TestCase):
    """Cover extracted GUI mixins without opening a Tk window."""

    def test_table_filter_uses_pending_path_cache(self):
        """Pending filter checks the in-memory pending path set."""
        harness = _TableHarness()
        harness.table_filter.set("Pending tags")
        harness.pending_tag_paths = {"song.mp3"}

        self.assertTrue(harness._row_matches_table_filter({"file_path": "song.mp3"}))
        self.assertFalse(harness._row_matches_table_filter({"file_path": "other.mp3"}))

    def test_completed_status_marks_review_rows(self):
        """Low-confidence and review recommendations stay marked for review."""
        harness = _TableHarness()

        status = harness._completed_status_for_row({
            "recommended_grouping": "Needs review",
            "recommended_confidence": "review",
        })

        self.assertEqual(status, "needs_review")

    def test_playback_time_format_is_mm_ss(self):
        """Playback helper formats seconds as mm:ss."""
        harness = _PlaybackHarness()

        self.assertEqual(harness._format_time(65.8), "01:05")
        self.assertEqual(harness._format_time(None), "00:00")


if __name__ == "__main__":
    unittest.main()
