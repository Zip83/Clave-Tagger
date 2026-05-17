import unittest

from music_category import virtual_table


class VirtualTableTests(unittest.TestCase):
    def test_visible_slice_limits_large_row_set(self):
        indexes = list(range(10000))

        start, end, visible = virtual_table.visible_slice(indexes, 0, 160)

        self.assertEqual(start, 0)
        self.assertEqual(end, 160)
        self.assertEqual(len(visible), 160)

    def test_clamp_start_stays_inside_filtered_rows(self):
        self.assertEqual(virtual_table.clamp_start(9999, 100, 20), 80)
        self.assertEqual(virtual_table.clamp_start(-10, 100, 20), 0)
        self.assertEqual(virtual_table.clamp_start(10, 0, 20), 0)

    def test_matching_indexes_uses_predicate_once_per_row(self):
        rows = [{"keep": False}, {"keep": True}, {"keep": False}, {"keep": True}]

        indexes = virtual_table.matching_indexes(rows, lambda row: row["keep"])

        self.assertEqual(indexes, [1, 3])

    def test_start_for_row_index_scrolls_current_row_into_window(self):
        indexes = list(range(1000))

        start = virtual_table.start_for_row_index(indexes, 900, 0, 120)

        self.assertLessEqual(start, 900)
        self.assertLess(900, start + 120)

    def test_scrollbar_fractions_represent_full_filtered_count(self):
        first, last = virtual_table.scrollbar_fractions(100, 1000, 100)

        self.assertAlmostEqual(first, 0.1)
        self.assertAlmostEqual(last, 0.2)

    def test_sorted_indexes_sorts_text_case_insensitive(self):
        rows = [{"file_name": "b.mp3"}, {"file_name": "A.mp3"}, {"file_name": ""}]
        indexes = [0, 1, 2]

        self.assertEqual(virtual_table.sorted_indexes(rows, indexes, "file_name", "asc"), [1, 0, 2])
        self.assertEqual(virtual_table.sorted_indexes(rows, indexes, "file_name", "desc"), [0, 1, 2])

    def test_sorted_indexes_sorts_numeric_values(self):
        rows = [{"score": "120.5"}, {"score": ""}, {"score": "89"}]
        indexes = [0, 1, 2]

        self.assertEqual(
            virtual_table.sorted_indexes(rows, indexes, "score", "asc", {"score"}),
            [2, 0, 1],
        )

    def test_sort_none_keeps_original_index_order(self):
        rows = [{"file_name": "b.mp3"}, {"file_name": "a.mp3"}]

        self.assertEqual(virtual_table.sorted_indexes(rows, [0, 1], "file_name", "none"), [0, 1])

    def test_next_sort_state_cycles_with_third_click_reset(self):
        self.assertEqual(virtual_table.next_sort_state("", "none", "file_name"), ("file_name", "asc"))
        self.assertEqual(virtual_table.next_sort_state("file_name", "asc", "file_name"), ("file_name", "desc"))
        self.assertEqual(virtual_table.next_sort_state("file_name", "desc", "file_name"), ("", "none"))
        self.assertEqual(virtual_table.next_sort_state("file_name", "desc", "title"), ("title", "asc"))


if __name__ == "__main__":
    unittest.main()
