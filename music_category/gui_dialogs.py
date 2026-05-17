"""Dialog windows and result viewers for the Tkinter GUI."""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import app_logging, app_paths, gui_services


class GuiDialogsMixin:
    """Provide modal dialogs and secondary result windows for the GUI shell."""

    def show_model_comparison_window(self, comparison_rows, fieldnames):
        """Open a side-by-side audio model comparison result window."""
        window = tk.Toplevel(self)
        window.title("Audio Model Comparison")
        window.geometry("1100x520+60+60")
        ttk.Label(window, text=f"Saved CSV: {self.model_comparison_csv.get()}").pack(anchor="w", padx=10, pady=(10, 4))

        frame = ttk.Frame(window)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        base_columns = ["file_name", "id3_grouping_normalized", "tag_suggested_grouping"]
        model_columns = [
            field for field in fieldnames
            if field.endswith("_grouping") or field.endswith("_confidence")
            if field not in base_columns
        ]
        columns = [column for column in base_columns + model_columns if column in fieldnames]
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=16)
        yscroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        xscroll = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        for column in columns:
            label = column.replace("_suggested_grouping", "").replace("_grouping", "").replace("_confidence", " conf")
            tree.heading(column, text=label)
            tree.column(column, width=220 if column == "file_name" else 145, stretch=column == "file_name")
        for row in comparison_rows:
            tree.insert("", tk.END, values=[row.get(column, "") for column in columns])

    def _label_playlist_options_dialog(self):
        """Collect playlist files and category mapping options for label matching."""
        dialog = tk.Toplevel(self)
        dialog.title("Match Label Playlist")
        dialog.geometry("760x430+80+80")
        dialog.transient(self)
        dialog.grab_set()
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        paths = []
        result = {"options": None}
        infer_label = "Infer from playlist name"
        category_value = tk.StringVar(value=infer_label)
        min_score_value = tk.StringVar(value=self.label_playlist_min_score.get() or "0.94")
        output_value = tk.StringVar(value=self.label_playlist_output.get() or str(app_paths.DEFAULT_PLAYLIST_MATCHES_CSV))

        intro = ttk.Label(
            dialog,
            text="Choose exported playlist files, then tell ClaveTagger what genre/category the playlist represents.",
            padding=(10, 10, 10, 4),
            wraplength=720,
        )
        intro.grid(row=0, column=0, sticky="ew")

        list_frame = ttk.LabelFrame(dialog, text="Playlist files", padding=8)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 8))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED, height=7)
        listbox.grid(row=0, column=0, sticky="nsew")
        list_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview)
        list_scroll.grid(row=0, column=1, sticky="ns")
        listbox.configure(yscrollcommand=list_scroll.set)

        def refresh_paths():
            """Refresh the selected playlist file listbox."""
            listbox.delete(0, tk.END)
            for path in paths:
                listbox.insert(tk.END, path)

        def add_files():
            """Append one or more playlist files chosen by the user."""
            selected = filedialog.askopenfilenames(
                parent=dialog,
                title="Select exported playlist files",
                filetypes=[
                    ("Playlist files", "*.csv *.xml *.vdjfolder *.m3u *.m3u8"),
                    ("CSV", "*.csv"),
                    ("VirtualDJ XML", "*.xml *.vdjfolder"),
                    ("M3U", "*.m3u *.m3u8"),
                    ("All files", "*.*"),
                ],
            )
            for path in selected:
                if path not in paths:
                    paths.append(path)
            refresh_paths()

        def remove_selected():
            """Remove selected playlist files from the pending match dialog."""
            selected = set(listbox.curselection())
            paths[:] = [path for index, path in enumerate(paths) if index not in selected]
            refresh_paths()

        file_buttons = ttk.Frame(list_frame)
        file_buttons.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self._button(file_buttons, "Add files", add_files, "Add one or more exported playlist files. Supported: CSV, XML/VDJ folder, M3U.").pack(side=tk.LEFT)
        self._button(file_buttons, "Remove selected", remove_selected, "Remove selected playlist files from this match run.").pack(side=tk.LEFT, padx=6)

        options_frame = ttk.LabelFrame(dialog, text="Match options", padding=8)
        options_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 8))
        options_frame.columnconfigure(1, weight=1)
        self._label(
            options_frame,
            "Playlist category / genre:",
            "Choose the category this playlist represents, for example Son Cubano. Infer uses the playlist file name, such as Son.",
        ).grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            options_frame,
            textvariable=category_value,
            values=[infer_label] + self.category_names,
            state="readonly",
            width=28,
        ).grid(row=0, column=1, sticky="w", padx=8, pady=2)
        self._label(options_frame, "Min score:", "Strict artist/title similarity threshold. 0.94 is conservative.").grid(row=1, column=0, sticky="w")
        ttk.Entry(options_frame, textvariable=min_score_value, width=8).grid(row=1, column=1, sticky="w", padx=8, pady=2)
        self._label(options_frame, "Output CSV:", "CSV report with every playlist row, local match, score, status, and target tag values.").grid(row=2, column=0, sticky="w")
        output_row = ttk.Frame(options_frame)
        output_row.grid(row=2, column=1, sticky="ew", padx=8, pady=2)
        output_row.columnconfigure(0, weight=1)
        ttk.Entry(output_row, textvariable=output_value).grid(row=0, column=0, sticky="ew")

        def browse_output():
            """Choose the playlist match CSV output path."""
            path = filedialog.asksaveasfilename(
                parent=dialog,
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            )
            if path:
                output_value.set(path)

        self._button(output_row, "Save as", browse_output, "Choose where to save the playlist match CSV.").grid(row=0, column=1, padx=(6, 0))

        buttons = ttk.Frame(dialog, padding=(10, 0, 10, 10))
        buttons.grid(row=3, column=0, sticky="ew")

        def accept():
            """Validate dialog values and return playlist match options."""
            if not paths:
                messagebox.showinfo("No playlist", "Choose at least one playlist file.", parent=dialog)
                return
            try:
                min_score = float(min_score_value.get() or "0.94")
            except ValueError:
                messagebox.showerror("Invalid score", "Min score must be a number, for example 0.94.", parent=dialog)
                return
            category = "" if category_value.get() == infer_label else category_value.get()
            self.label_playlist_output.set(output_value.get().strip())
            self.label_playlist_min_score.set(str(min_score))
            result["options"] = gui_services.LabelPlaylistOptions(
                playlist_paths=list(paths),
                explicit_category=category,
                min_score=min_score,
                output_csv=output_value.get().strip(),
                config_path=self.config_path.get().strip(),
            )
            dialog.destroy()

        self._button(buttons, "Match", accept, "Run matching against the currently loaded local tracks.").pack(side=tk.LEFT)
        self._button(buttons, "Cancel", dialog.destroy, "Close without matching.").pack(side=tk.RIGHT)
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        self.wait_window(dialog)
        return result["options"]

    def match_label_playlist(self):
        """Run label playlist matching from the GUI without writing MP3 tags."""
        options = self._label_playlist_options_dialog()
        if not options:
            return
        if not self.rows and not self.source_paths and not self.input_csv.get().strip():
            messagebox.showinfo("No local tracks", "Load local tracks first, or add source folders before matching a playlist.")
            return

        def worker():
            """Run playlist matching in the background worker thread."""
            try:
                def phase(message):
                    """Forward service phase messages to the GUI queue."""
                    self.message_queue.put(("phase", message))

                rows = self.rows
                if not rows:
                    phase("Playlist match: no loaded tracks yet, loading preview first...")
                    rows = gui_services.preview_rows(
                        self.source_paths,
                        self.input_csv.get().strip(),
                        self.config_path.get().strip(),
                        progress_callback=lambda payload: self.message_queue.put(("load_progress", payload)),
                    )
                    self.rows = rows
                    self.message_queue.put(("rows_loaded", rows))

                match_rows, summary = gui_services.match_label_playlists(
                    options,
                    rows,
                    status_callback=phase,
                    progress_callback=lambda payload: self.message_queue.put(("playlist_match_progress", payload)),
                )
                self.rows = rows
                self.message_queue.put(("playlist_match_result", (match_rows, summary)))
                self.message_queue.put((
                    "status",
                    f"Playlist match complete: {summary['matched']} matched, {summary['review']} review, "
                    f"{summary['unmatched']} unmatched. Prepared {summary['updated']} pending tag row(s).",
                ))
            except Exception as error:
                app_logging.log_exception("playlist match failed", error)
                self.message_queue.put(("error", str(error)))
            finally:
                self.message_queue.put(("done", None))

        self._start_worker(worker)

    def show_playlist_match_window(self, match_rows, summary):
        """Open a color-coded result window for playlist matching."""
        window = tk.Toplevel(self)
        window.title("Playlist Match Results")
        window.geometry("1060x500+70+70")
        ttk.Label(
            window,
            text=(
                f"Saved CSV: {summary.get('output_csv', '')} | "
                f"matched {summary.get('matched', 0)}, review {summary.get('review', 0)}, "
                f"unmatched {summary.get('unmatched', 0)}, pending updates {summary.get('updated', 0)}"
            ),
            padding=(10, 10, 10, 4),
        ).pack(anchor="w")

        frame = ttk.Frame(window)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        columns = (
            "match_status", "playlist_name", "playlist_category", "playlist_artist", "playlist_title",
            "file_name", "artist", "title", "match_score", "target_grouping", "target_color",
        )
        headings = {
            "match_status": "Status",
            "playlist_name": "Playlist",
            "playlist_category": "Category",
            "playlist_artist": "Playlist Artist",
            "playlist_title": "Playlist Title",
            "file_name": "Matched File",
            "artist": "Local Artist",
            "title": "Local Title",
            "match_score": "Score",
            "target_grouping": "Target Grouping",
            "target_color": "Target Color",
        }
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=16)
        yscroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        xscroll = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        for column in columns:
            tree.heading(column, text=headings[column])
            tree.column(column, width=220 if column in {"playlist_title", "file_name"} else 125, stretch=column in {"playlist_title", "file_name"})
        tree.tag_configure("matched", background="#dcf7df")
        tree.tag_configure("review", background="#fff0bf")
        tree.tag_configure("unmatched", background="#ffd6d6")
        for row in match_rows:
            status = row.get("match_status", "review")
            tree.insert("", tk.END, values=[row.get(column, "") for column in columns], tags=(status,))
