"""Virtual table filtering, sorting, row-state, and scroll helpers for the GUI."""

import tkinter as tk

from . import gui_services, virtual_table


class GuiTableMixin:
    """Keep the main track table virtualized and synchronized with row state."""

    def _insert_or_update_row(self, row, status=None):
        """Update one rendered table row without forcing a full rerender."""
        file_path = row.get("file_path", "")
        tag = self._row_display_tag(row, status)
        if file_path in self.row_by_path:
            if self._row_matches_table_filter(row):
                self.tree.item(file_path, values=self._row_values(row), tags=(tag,))
            else:
                self.tree.delete(file_path)
                self.row_by_path.pop(file_path, None)
        self._update_pending_title()

    def _row_values(self, row):
        """Return the visible Treeview values for one track row."""
        return (
            row.get("file_name", ""), row.get("id3_grouping_normalized", ""), row.get("id3_color", ""),
            row.get("tag_suggested_grouping", ""), row.get("model_audio_suggested_grouping", ""),
            row.get("learned_suggested_grouping", ""), row.get("recommended_grouping", ""),
            row.get("target_grouping", ""), row.get("target_color", ""),
            row.get("recommended_source", ""), row.get("recommended_confidence", ""),
        )

    def _row_display_tag(self, row, status=None):
        """Choose and store the table color/state tag for one row."""
        tag = status or row.get("_gui_status", "queued")
        if row.get("_analysis_skipped_existing_grouping"):
            tag = "done"
        elif tag not in {"queued", "current"} and row.get("recommended_grouping") == "Needs review":
            tag = "needs_review"
        row["_gui_status"] = tag
        return tag

    def _row_matches_table_filter(self, row):
        """Return whether a row is included by the active table filter."""
        if row.get("_gui_status") == "current":
            return True
        filter_name = self.table_filter.get()
        has_grouping = gui_services.has_existing_grouping(row)
        if filter_name == "Missing Grouping":
            return not has_grouping
        if filter_name == "Tagged":
            return has_grouping
        if filter_name == "Pending tags":
            return row.get("file_path", "") in self.pending_tag_paths
        if filter_name == "Needs review":
            return row.get("_gui_status") == "needs_review" or row.get("recommended_grouping") == "Needs review"
        return True

    def refresh_table_filter(self):
        """Rebuild the filtered index and redraw the visible table window."""
        self._refresh_filtered_rows(keep_start=False)
        self._render_virtual_table()

    def toggle_table_sort(self, column):
        """Cycle visual sort state for a Treeview column header."""
        self.sort_column, self.sort_direction = virtual_table.next_sort_state(
            self.sort_column,
            self.sort_direction,
            column,
        )
        self._update_sort_headings()
        self._refresh_filtered_rows(keep_start=False)
        self._render_virtual_table()

    def _reset_table_sort(self):
        """Clear visual sort and restore loaded-row order."""
        self.sort_column = ""
        self.sort_direction = "none"
        self._update_sort_headings()

    def _update_sort_headings(self):
        """Refresh column heading text to show active sort direction."""
        if not getattr(self, "tree", None):
            return
        for column, label in self.column_headings.items():
            suffix = ""
            if column == self.sort_column:
                suffix = " â†‘" if self.sort_direction == "asc" else (" â†“" if self.sort_direction == "desc" else "")
            self.tree.heading(column, text=f"{label}{suffix}", command=lambda selected=column: self.toggle_table_sort(selected))

    def _refresh_filtered_rows(self, keep_start=True):
        """Recompute filtered/sorted row indexes for the virtual table."""
        indexes = virtual_table.matching_indexes(self.rows, self._row_matches_table_filter)
        self.filtered_row_indexes = virtual_table.sorted_indexes(
            self.rows,
            indexes,
            self.sort_column,
            self.sort_direction,
            numeric_columns=set(),
        )
        if not keep_start:
            self.virtual_table_start = 0
        self.virtual_table_start = virtual_table.clamp_start(
            self.virtual_table_start,
            len(self.filtered_row_indexes),
            self.virtual_table_window,
        )

    def _render_virtual_table(self, start=None, preserve_selection=True):
        """Render only the currently visible virtual slice into Treeview."""
        if start is not None:
            self.virtual_table_start = start
        self.virtual_table_start, end, indexes = virtual_table.visible_slice(
            self.filtered_row_indexes,
            self.virtual_table_start,
            self.virtual_table_window,
        )
        selected = set(self.tree.selection()) if preserve_selection else set()
        self._reset_table(update_status=False)
        for row_index in indexes:
            row = self.rows[row_index]
            file_path = row.get("file_path", "")
            if not file_path:
                continue
            self.tree.insert("", tk.END, iid=file_path, values=self._row_values(row), tags=(self._row_display_tag(row),))
            self.row_by_path[file_path] = file_path
        rendered_selection = [item for item in selected if item in self.row_by_path]
        if rendered_selection:
            self.tree.selection_set(rendered_selection)
        self._update_virtual_scrollbar()
        self._update_table_status(end)

    def _update_virtual_scrollbar(self):
        """Map the virtual table window onto the real scrollbar fractions."""
        if not self.virtual_yscroll:
            return
        first, last = virtual_table.scrollbar_fractions(
            self.virtual_table_start,
            len(self.filtered_row_indexes),
            self.virtual_table_window,
        )
        self.virtual_yscroll.set(first, last)

    def _update_table_status(self, end=None):
        """Display visible, filtered, total, and sort information."""
        filtered = len(self.filtered_row_indexes)
        if not filtered:
            self.selection_info.set(f"0/{len(self.rows)} visible")
            return
        end = self.virtual_table_start + len(self.tree.get_children("")) if end is None else end
        sort_note = ""
        if self.sort_column and self.sort_direction != "none":
            sort_note = f" | sorted by {self.column_headings.get(self.sort_column, self.sort_column)} {self.sort_direction}"
        self.selection_info.set(
            f"visible {self.virtual_table_start + 1}-{min(end, filtered)} / filtered {filtered} / total {len(self.rows)}{sort_note}"
        )

    def _virtual_page_size(self):
        """Return a reasonable page size for keyboard table scrolling."""
        try:
            return max(1, int(self.tree["height"]))
        except Exception:
            return 8

    def _set_virtual_table_start(self, start):
        """Move the virtual table window to an absolute start index."""
        self._render_virtual_table(start=start)
        return "break"

    def _scroll_virtual_table(self, delta):
        """Move the virtual table window by a relative row delta."""
        self._render_virtual_table(start=self.virtual_table_start + int(delta))
        return "break"

    def _on_virtual_mousewheel(self, event):
        """Scroll the virtual table from a mouse wheel event."""
        step = -1 if event.delta > 0 else 1
        units = max(1, abs(event.delta) // 120) * 3
        return self._scroll_virtual_table(step * units)

    def _virtual_yview(self, *args):
        """Implement the scrollbar command for the virtual table."""
        if not args:
            return
        if args[0] == "moveto":
            fraction = float(args[1])
            target = int(fraction * max(1, len(self.filtered_row_indexes)))
            self._render_virtual_table(start=target)
        elif args[0] == "scroll":
            amount = int(args[1])
            unit = self._virtual_page_size() if args[2] == "pages" else 3
            self._scroll_virtual_table(amount * unit)

    def _completed_status_for_row(self, row):
        """Choose the final row state after analysis or learned inference."""
        if row.get("_analysis_skipped_existing_grouping"):
            return "done"
        if row.get("recommended_grouping") == "Needs review":
            return "needs_review"
        if row.get("recommended_confidence") in {"", "review", "low"}:
            return "needs_review"
        current_grouping = row.get("id3_grouping_normalized", "")
        recommended = row.get("recommended_grouping", "")
        if row.get("recommended_confidence") == "high" or (current_grouping and current_grouping == recommended):
            return "done"
        return "completed"

    def _mark_current(self, row, after_status=None):
        """Mark one row as currently processing and restore the previous current row."""
        file_path = row.get("file_path", "")
        for existing in self.rows:
            if existing.get("_gui_status") == "current":
                existing["_gui_status"] = existing.get("_previous_gui_status", "queued")
                existing.pop("_previous_gui_status", None)
                self._insert_or_update_row(existing)
        row["_previous_gui_status"] = after_status or row.get("_gui_status", "queued")
        row["_gui_status"] = "current"
        self._scroll_row_into_view(row)
        self._insert_or_update_row(row, status="current")
        if file_path in self.row_by_path:
            self.tree.see(file_path)

    def _scroll_row_into_view(self, row):
        """Move the virtual window so the given row is rendered."""
        try:
            row_index = self.rows.index(row)
        except ValueError:
            return
        self._refresh_filtered_rows(keep_start=True)
        self.virtual_table_start = virtual_table.start_for_row_index(
            self.filtered_row_indexes,
            row_index,
            self.virtual_table_start,
            self.virtual_table_window,
        )
        self._render_virtual_table()

    def _reset_table(self, update_status=True):
        """Clear rendered Treeview items while keeping in-memory rows."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.row_by_path = {}
        if update_status:
            self._update_pending_title()

    def _clear_table_state(self):
        """Clear table indexes, pending state, and rendered rows."""
        self.pending_tag_paths = set()
        self.filtered_row_indexes = []
        self.virtual_table_start = 0
        self._reset_table()
        self._update_virtual_scrollbar()
        self._update_table_status()
