import os
import io
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import music_category_report as core
from music_category import app_env, app_logging, app_paths, audio_model, audio_model_catalog, classifier_presets, config, gui_services, gui_settings, id3_tags, learning, power, virtual_table
from music_category.cancel import CancelToken, CancelledError


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.window = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _event=None):
        if self.window or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(self.window, text=self.text, padding=6, relief="solid", wraplength=420)
        label.pack()

    def hide(self, _event=None):
        if self.window:
            self.window.destroy()
            self.window = None


class HoverText:
    def __init__(self, owner):
        self.owner = owner
        self.window = None
        self.text = ""

    def show_at_pointer(self, text):
        if not text:
            self.hide()
            return
        x, y = self.owner.winfo_pointerxy()
        if self.window and self.text == text:
            self.window.wm_geometry(f"+{x + 16}+{y + 18}")
            return
        self.hide()
        self.text = text
        self.window = tk.Toplevel(self.owner)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{x + 16}+{y + 18}")
        label = ttk.Label(self.window, text=text, padding=6, relief="solid", wraplength=460)
        label.pack()

    def hide(self, _event=None):
        if self.window:
            self.window.destroy()
            self.window = None
        self.text = ""


class MenuToolTip:
    def __init__(self, root, menu, descriptions):
        self.menu = menu
        self.descriptions = descriptions
        self.hover = HoverText(root)
        menu.bind("<<MenuSelect>>", self.show)
        menu.bind("<Leave>", self.hover.hide)
        menu.bind("<Unmap>", self.hover.hide)

    def show(self, _event=None):
        try:
            index = self.menu.index("active")
            label = self.menu.entrycget(index, "label") if index is not None else ""
        except tk.TclError:
            self.hover.hide()
            return
        self.hover.show_at_pointer(self.descriptions.get(label, ""))


class NotebookToolTip:
    def __init__(self, root, notebook, descriptions):
        self.notebook = notebook
        self.descriptions = descriptions
        self.hover = HoverText(root)
        notebook.bind("<Motion>", self.show)
        notebook.bind("<Leave>", self.hover.hide)

    def show(self, event):
        try:
            index = self.notebook.index(f"@{event.x},{event.y}")
        except tk.TclError:
            self.hover.hide()
            return
        self.hover.show_at_pointer(self.descriptions.get(index, ""))


class MusicCategoryGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(app_paths.APP_NAME)
        self.geometry("1120x660+20+20")
        self.minsize(920, 560)

        app_paths.ensure_runtime_dirs()
        app_logging.configure_logging(app_paths.DEFAULT_LOG_FILE)

        self.message_queue = queue.Queue()
        self.menu_tooltips = []
        self.notebook_tooltips = []
        self.worker_thread = None
        self.cancel_token = None
        self.busy_widgets = []
        self.playback_buttons = []
        self.play_pause_buttons = []
        self.seek_controls = []
        self.dependent_widgets = {}
        self.rows = []
        self.row_by_path = {}
        self.pending_tag_paths = set()
        self.filtered_row_indexes = []
        self.virtual_table_start = 0
        self.virtual_table_window = 160
        self.virtual_yscroll = None
        self.sort_column = ""
        self.sort_direction = "none"
        self.column_headings = {}
        self.current_file_path = ""
        self.playing_file = ""

        self.source_paths = []
        self.input_csv = tk.StringVar()
        self.output_csv = tk.StringVar(value=str(app_paths.DEFAULT_MAIN_CSV))
        self.details_csv = tk.StringVar(value=str(app_paths.DEFAULT_DETAILS_CSV))
        self.model_comparison_csv = tk.StringVar(value=str(app_paths.DEFAULT_MODEL_COMPARISON_CSV))
        self.progress_json = tk.StringVar(value=str(app_paths.DEFAULT_PROGRESS_JSON))
        self.log_file = tk.StringVar(value=str(app_paths.DEFAULT_LOG_FILE))
        self.env_file = tk.StringVar(value=".env")
        self.hf_token_status = tk.StringVar(value=f"HF token: {app_env.hf_token_status()}")
        self.config_path = tk.StringVar(value="category_config.json")
        self.classifier_path = tk.StringVar(value=str(app_paths.DEFAULT_LIGHT_CLASSIFIER))
        self.classifier_input = tk.StringVar()
        self.classifier_output = tk.StringVar(value=str(app_paths.DEFAULT_LIGHT_CLASSIFIER))
        self.classifier_backend = tk.StringVar(value="light")
        self.classifier_preset = tk.StringVar(value=classifier_presets.label_for("light"))
        self.training_source = tk.StringVar(value="Current loaded tracks")
        self.heavy_epochs = tk.StringVar(value="8")
        self.heavy_batch_size = tk.StringVar(value="8")
        self.heavy_learning_rate = tk.StringVar(value="0.001")
        self.heavy_max_files = tk.StringVar()
        self.heavy_max_chunks = tk.StringVar()
        self.recommendation_priority = tk.StringVar(value="")
        self.mode = tk.StringVar(value="both")
        self.audio_model_id = tk.StringVar(value=audio_model.MODEL_ID)
        self.model_full_track = tk.BooleanVar(value=False)
        self.only_missing_grouping = tk.BooleanVar(value=False)
        self.prevent_sleep = tk.BooleanVar(value=True)
        self.use_details = tk.BooleanVar(value=True)
        self.write_after_report = tk.BooleanVar(value=False)
        self.value_column = tk.StringVar(value="target_grouping")
        self.after_report_color_column = tk.StringVar(value="")
        self.prediction_column = tk.StringVar(value="recommended_grouping")
        self.truth_column = tk.StringVar(value="id3_grouping_normalized")
        self.overrides_csv = tk.StringVar(value=str(app_paths.DEFAULT_OVERRIDES_CSV))
        self.calibration_output = tk.StringVar(value="category_config.tuned.json")
        self.mismatch_output = tk.StringVar(value="reports/calibration_mismatches.csv")
        self.label_playlist_output = tk.StringVar(value=str(app_paths.DEFAULT_PLAYLIST_MATCHES_CSV))
        self.label_playlist_min_score = tk.StringVar(value="0.94")

        self.write_csv = tk.StringVar()
        self.grouping_column = tk.StringVar(value="target_grouping")
        self.color_column = tk.StringVar(value="target_color")
        self.apply_write = tk.BooleanVar(value=False)
        self.only_when_empty = tk.BooleanVar(value=False)

        self.selected_target_grouping = tk.StringVar()
        self.selected_target_color = tk.StringVar()
        self.selected_note = tk.StringVar()
        self.selected_info = tk.StringVar(value="No track selected")
        self.bulk_target_grouping = tk.StringVar()
        self.bulk_target_color = tk.StringVar()
        self.bulk_note = tk.StringVar()
        self.selection_info = tk.StringVar(value="No tracks selected")
        self.pending_tags_status = tk.StringVar(value="Pending tags: 0")
        self.table_filter = tk.StringVar(value="All tracks")
        self.source_summary = tk.StringVar(value="No source selected")
        self.playback_seek = tk.DoubleVar(value=0.0)
        self.playback_time = tk.StringVar(value="00:00 / 00:00")
        self.playback_duration = 0.0
        self.playback_offset = 0.0
        self.playback_updating = False
        self.playback_paused = False
        self.playback_buffer = None
        self.playback_buffer_path = ""
        self.prevent_sleep_active = False
        self.audio_model_presets = audio_model_catalog.load_catalog()
        self.audio_model_preset = tk.StringVar()
        self.audio_model_description = tk.StringVar(
            value="Choose a preset, or type a Hugging Face audio-classification model id manually."
        )
        for preset in self.audio_model_presets:
            if preset.get("model_id") == audio_model.MODEL_ID:
                self.audio_model_preset.set(audio_model_catalog.preset_label(preset))
                self.audio_model_description.set(self._audio_model_description(preset))
                break
        self.category_names = [item.get("category", "") for item in config.category_items()]

        self._settings_variables = self._build_settings_variables()
        self._load_gui_settings()
        self.reload_env_file(show_status=False)
        self._build_ui()
        self._bind_dependency_refresh()
        self._refresh_dependency_state()
        self.protocol("WM_DELETE_WINDOW", self.close_app)
        self.after(150, self._poll_queue)

    def _build_settings_variables(self):
        return {
            "output_csv": self.output_csv,
            "details_csv": self.details_csv,
            "model_comparison_csv": self.model_comparison_csv,
            "progress_json": self.progress_json,
            "log_file": self.log_file,
            "env_file": self.env_file,
            "config_path": self.config_path,
            "classifier_path": self.classifier_path,
            "classifier_input": self.classifier_input,
            "classifier_output": self.classifier_output,
            "classifier_backend": self.classifier_backend,
            "classifier_preset": self.classifier_preset,
            "training_source": self.training_source,
            "heavy_epochs": self.heavy_epochs,
            "heavy_batch_size": self.heavy_batch_size,
            "heavy_learning_rate": self.heavy_learning_rate,
            "heavy_max_files": self.heavy_max_files,
            "heavy_max_chunks": self.heavy_max_chunks,
            "recommendation_priority": self.recommendation_priority,
            "mode": self.mode,
            "audio_model_id": self.audio_model_id,
            "model_full_track": self.model_full_track,
            "only_missing_grouping": self.only_missing_grouping,
            "prevent_sleep": self.prevent_sleep,
            "use_details": self.use_details,
            "write_after_report": self.write_after_report,
            "value_column": self.value_column,
            "after_report_color_column": self.after_report_color_column,
            "prediction_column": self.prediction_column,
            "truth_column": self.truth_column,
            "overrides_csv": self.overrides_csv,
            "calibration_output": self.calibration_output,
            "mismatch_output": self.mismatch_output,
            "label_playlist_output": self.label_playlist_output,
            "label_playlist_min_score": self.label_playlist_min_score,
            "grouping_column": self.grouping_column,
            "color_column": self.color_column,
            "only_when_empty": self.only_when_empty,
            "audio_model_preset": self.audio_model_preset,
            "table_filter": self.table_filter,
        }

    def _load_gui_settings(self):
        gui_settings.apply_variables(gui_settings.load_settings(), self._settings_variables)
        preset = audio_model_catalog.find_by_label(self.audio_model_preset.get(), self.audio_model_presets)
        if preset:
            self.audio_model_description.set(self._audio_model_description(preset))

    def _save_gui_settings(self):
        settings = gui_settings.collect_variables(self._settings_variables)
        settings["apply_write"] = False
        gui_settings.save_settings(settings)

    def close_app(self):
        self._save_gui_settings()
        self.destroy()

    def _build_ui(self):
        self._build_menu()
        root = ttk.Frame(self, padding=10)
        root.pack(fill=tk.BOTH, expand=True)
        notebook = ttk.Notebook(root)
        notebook.pack(fill=tk.BOTH, expand=True)
        self.report_tab = ttk.Frame(notebook, padding=10)
        self.settings_tab = ttk.Frame(notebook, padding=10)
        self.write_tab = ttk.Frame(notebook, padding=10)
        self.log_tab = ttk.Frame(notebook, padding=10)
        notebook.add(self.report_tab, text="Analyze")
        notebook.add(self.settings_tab, text="Settings")
        notebook.add(self.write_tab, text="Write Tags")
        notebook.add(self.log_tab, text="Log")
        self.notebook_tooltips.append(NotebookToolTip(self, notebook, {
            0: "Analyze sources, preview tracks, follow progress, edit corrections, and control playback.",
            1: "Configure outputs, analysis mode, classifier training, evaluation, and calibration.",
            2: "Write Grouping and Color tags from a CSV. Writes stay dry-run until Apply write is enabled.",
            3: "View application messages and diagnostics from the current GUI session.",
        }))
        self._build_report_tab()
        self._build_settings_tab()
        self._build_write_tab()
        self._build_log_tab()

    def _build_menu(self):
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Add Folder", command=self.add_folder)
        file_menu.add_command(label="Add Subfolders From Parent", command=self.add_subfolders_from_parent)
        file_menu.add_command(label="Manage Sources", command=self.manage_sources)
        file_menu.add_separator()
        file_menu.add_command(label="Open Input CSV", command=self.browse_input_csv)
        file_menu.add_command(label="Choose Output CSV", command=self.browse_output_csv)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.close_app)
        menu.add_cascade(label="File", menu=file_menu)
        self._attach_menu_tooltips(file_menu, {
            "Add Folder": "Add one source folder and immediately preview MP3 tags recursively.",
            "Add Subfolders From Parent": "Choose a parent folder, then add multiple immediate subfolders at once.",
            "Manage Sources": "Review, remove, clear, or add source folders without losing the current selection by accident.",
            "Open Input CSV": "Load an existing report CSV instead of scanning folders.",
            "Choose Output CSV": "Choose where the next main analysis CSV will be saved.",
            "Exit": "Close ClaveTagger.",
        })

        action_menu = tk.Menu(menu, tearoff=False)
        action_menu.add_command(label="Estimate", command=self.estimate_report)
        action_menu.add_command(label="Analyze", command=self.run_report)
        action_menu.add_command(label="Write Pending Tags Dry Run", command=lambda: self.write_pending_tags(False))
        action_menu.add_command(label="Write Pending Tags", command=lambda: self.write_pending_tags(True))
        action_menu.add_command(label="Clear Selected Tags Dry Run", command=lambda: self.clear_selected_tags(False))
        action_menu.add_command(label="Clear Selected Tags", command=lambda: self.clear_selected_tags(True))
        action_menu.add_command(label="Match Label Playlist", command=self.match_label_playlist)
        action_menu.add_command(label="Compare Audio Models", command=self.compare_audio_models)
        action_menu.add_command(label="Train classifier", command=self.train_classifier)
        action_menu.add_command(label="Evaluate", command=self.evaluate_report)
        action_menu.add_command(label="Suggest Config Tuning", command=self.calibrate_report)
        action_menu.add_separator()
        action_menu.add_command(label="Abort", command=self.abort_current_task)
        menu.add_cascade(label="Actions", menu=action_menu)
        self._attach_menu_tooltips(action_menu, {
            "Estimate": "Dry-run the selected inputs and show the expected work without running audio analysis.",
            "Analyze": "Create the report using the selected mode: tags, MAEST audio, learned classifier, or combinations.",
            "Write Pending Tags Dry Run": "Preview writes for rows whose target/recommended category differs from current Grouping.",
            "Write Pending Tags": "Write all pending target/recommended Grouping and Color values to MP3 tags.",
            "Clear Selected Tags Dry Run": "Preview clearing Grouping and Color from the selected table rows.",
            "Clear Selected Tags": "Clear Grouping and Color from the selected table rows after confirmation.",
            "Match Label Playlist": "Match an exported TIDAL/VirtualDJ-style playlist to loaded local tracks and prepare pending target tags.",
            "Compare Audio Models": "Run every supported audio model preset and open a side-by-side comparison table.",
            "Train classifier": "Train the selected light/heavy classifier from files that already have Grouping tags.",
            "Evaluate": "Compare a prediction column against your chosen truth column.",
            "Suggest Config Tuning": "Read an existing CSV and write suggested config changes plus a mismatch report.",
            "Abort": "Request cooperative cancellation. The current file or model step may finish first.",
        })

        playback_menu = tk.Menu(menu, tearoff=False)
        playback_menu.add_command(label="Play / Pause selected", command=self.toggle_play_pause)
        playback_menu.add_command(label="Stop", command=self.stop_playback)
        playback_menu.add_command(label="Open externally", command=self.open_selected_external)
        menu.add_cascade(label="Playback", menu=playback_menu)
        self._attach_menu_tooltips(playback_menu, {
            "Play / Pause selected": "Toggle playback for the currently selected table row.",
            "Stop": "Stop in-app playback and reset the seek position.",
            "Open externally": "Open the selected track in the system default player.",
        })
        self.config(menu=menu)

    def _attach_menu_tooltips(self, menu, descriptions):
        self.menu_tooltips.append(MenuToolTip(self, menu, descriptions))

    def _label(self, parent, text, tooltip=""):
        label = ttk.Label(parent, text=text)
        if tooltip:
            ToolTip(label, tooltip)
        return label

    def _button(self, parent, text, command, tooltip="", **kwargs):
        button = ttk.Button(parent, text=text, command=command, **kwargs)
        if tooltip:
            ToolTip(button, tooltip)
        return button

    def _labeled_entry(self, parent, label, variable, width=24, tooltip=""):
        label_widget = self._label(parent, label, tooltip)
        label_widget.pack(side=tk.LEFT)
        entry = ttk.Entry(parent, textvariable=variable, width=width)
        entry.pack(side=tk.LEFT, padx=5)
        return entry

    def _track_dependency(self, group, *widgets):
        self.dependent_widgets.setdefault(group, []).extend(widgets)

    def _set_widgets_enabled(self, group, enabled):
        for widget in self.dependent_widgets.get(group, []):
            try:
                state = "readonly" if enabled and widget.winfo_class() == "TCombobox" else "normal"
                if not enabled:
                    state = "disabled"
                widget.configure(state=state)
            except tk.TclError:
                pass

    def _bind_dependency_refresh(self):
        for variable in (self.mode, self.classifier_backend, self.use_details, self.write_after_report):
            variable.trace_add("write", lambda *_args: self._refresh_dependency_state())

    def _refresh_dependency_state(self):
        state = gui_services.dependency_state(
            self.mode.get(),
            self.classifier_backend.get(),
            self.use_details.get(),
            self.write_after_report.get(),
        )
        for group, enabled in state.items():
            self._set_widgets_enabled(group, enabled)

    def _build_report_tab(self):
        paned = ttk.PanedWindow(self.report_tab, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)
        top = ttk.Frame(paned)
        bottom = ttk.Frame(paned)
        paned.add(top, weight=0)
        paned.add(bottom, weight=1)

        self._build_input_group(top)
        self._build_compact_actions(top)
        self._build_progress_group(top)
        self._build_table_and_editor(bottom)

    def _build_settings_tab(self):
        self._build_options_groups(self.settings_tab)

    def _build_log_tab(self):
        self._build_log(self.log_tab, expand=True)

    def _build_input_group(self, parent):
        frame = ttk.LabelFrame(parent, text="Input", padding=10)
        frame.pack(fill=tk.X, pady=(0, 6))

        row = ttk.Frame(frame)
        row.pack(fill=tk.X)
        self._label(row, "Sources:", "Currently selected folders. Use File > Add Folder or File > Manage Sources to change them.").pack(side=tk.LEFT)
        ttk.Label(row, textvariable=self.source_summary, width=28).pack(side=tk.LEFT, padx=(5, 12))
        self._label(row, "Input CSV:", "Optional existing report CSV loaded from File > Open Input CSV. Empty means scan selected folders.").pack(side=tk.LEFT)
        input_entry = ttk.Entry(row, textvariable=self.input_csv, width=42, state="readonly")
        input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self._label(row, "Recursive", "Folder scanning is recursive by default for all selected sources.").pack(side=tk.LEFT, padx=(8, 0))
        ToolTip(frame, "Use the File menu to add folders, manage sources, or open an input CSV.")

    def _build_compact_actions(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=(0, 6))
        action_row = ttk.Frame(frame)
        action_row.pack(fill=tk.X)
        self._label(action_row, "Task:", "Run tasks from the Actions menu. Abort stays here because it is needed quickly during long jobs.").pack(side=tk.LEFT)
        self.abort_button = self._button(
            action_row,
            "Abort",
            self.abort_current_task,
            "Request cancellation. ClaveTagger stops before the next file, batch, or epoch when possible.",
            state="disabled",
        )
        self.abort_button.pack(side=tk.LEFT, padx=(5, 10))
        ttk.Separator(action_row, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        self._label(action_row, "Playback:", "Controls the selected table row. Playback remains available while analysis is running.").pack(side=tk.LEFT, padx=(0, 5))
        self._play_pause_button(action_row).pack(side=tk.LEFT)
        self._playback_button(action_row, "■", self.stop_playback).pack(side=tk.LEFT)
        self._playback_button(action_row, "↗", self.open_selected_external).pack(side=tk.LEFT, padx=(2, 8))
        seek = ttk.Scale(action_row, from_=0, to=300, variable=self.playback_seek, orient=tk.HORIZONTAL)
        seek.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self._bind_seek_control(seek)
        ToolTip(seek, "Seek within the currently playing track.")
        ttk.Label(action_row, textvariable=self.playback_time, width=13).pack(side=tk.LEFT)

    def _playback_button(self, parent, text, command):
        tips = {
            "play_selected": "Play the selected track.",
            "toggle_play_pause": "Play, pause, or resume the selected track.",
            "pause_playback": "Pause or resume playback.",
            "stop_playback": "Stop playback.",
            "open_selected_external": "Open the selected track in the system player.",
        }
        button = self._button(parent, text, command, tips.get(getattr(command, "__name__", ""), "Playback control."), width=3)
        self.playback_buttons.append(button)
        return button

    def _play_pause_button(self, parent):
        button = self._playback_button(parent, "▶", self.toggle_play_pause)
        self.play_pause_buttons.append(button)
        return button

    def _update_play_pause_buttons(self):
        text = "▶" if self.playback_paused or not self.playing_file else "⏸"
        for button in self.play_pause_buttons:
            try:
                button.configure(text=text)
            except tk.TclError:
                pass

    def _bind_seek_control(self, scale):
        self.seek_controls.append(scale)
        scale.bind("<Button-1>", self._seek_from_pointer)
        scale.bind("<B1-Motion>", self._preview_seek_from_pointer)
        scale.bind("<ButtonRelease-1>", self._seek_from_pointer)

    def _set_seek_range(self, duration):
        maximum = max(float(duration or 0.0), 1.0)
        for scale in self.seek_controls:
            try:
                scale.configure(to=maximum)
            except tk.TclError:
                pass

    def _build_options_groups(self, parent):
        groups = ttk.Notebook(parent)
        groups.pack(fill=tk.X, pady=6)

        output = ttk.LabelFrame(groups, text="Output", padding=10)
        groups.add(output, text="Output")
        r = ttk.Frame(output); r.pack(fill=tk.X, pady=2)
        self._labeled_entry(r, "Main CSV:", self.output_csv, 34, "Main report output with one row per MP3.")
        self._button(r, "Save as", self.browse_output_csv, "Choose the main report CSV path.").pack(side=tk.LEFT)
        r = ttk.Frame(output); r.pack(fill=tk.X, pady=2)
        details_check = ttk.Checkbutton(r, text="Details CSV", variable=self.use_details)
        details_check.pack(side=tk.LEFT)
        ToolTip(details_check, "Also write detailed MAEST/model label scores for diagnostics and tuning.")
        details_entry = ttk.Entry(r, textvariable=self.details_csv, width=34)
        details_entry.pack(side=tk.LEFT, padx=5)
        details_button = self._button(r, "Save as", self.browse_details_csv, "Choose the details CSV path.")
        details_button.pack(side=tk.LEFT)
        self._track_dependency("details_csv", details_entry, details_button)
        r = ttk.Frame(output); r.pack(fill=tk.X, pady=2)
        progress_entry = self._labeled_entry(r, "Progress:", self.progress_json, 28, "Resume cache for MAEST model results.")
        self._track_dependency("audio_progress", progress_entry)
        self._labeled_entry(r, "Log:", self.log_file, 24, "Application log file for errors and diagnostics.")
        r = ttk.Frame(output); r.pack(fill=tk.X, pady=2)
        self._labeled_entry(r, "Model comparison:", self.model_comparison_csv, 34, "Side-by-side CSV created by Compare Audio Models.")
        r = ttk.Frame(output); r.pack(fill=tk.X, pady=2)
        self._labeled_entry(r, "Env file:", self.env_file, 28, "Local .env file. HF_TOKEN from this file is used for Hugging Face downloads unless already set in Windows.")
        self._button(r, "Reload", self.reload_env_file, "Reload .env and update the HF token status.").pack(side=tk.LEFT)
        ttk.Label(r, textvariable=self.hf_token_status).pack(side=tk.LEFT, padx=10)

        analysis = ttk.LabelFrame(groups, text="Analysis", padding=10)
        groups.add(analysis, text="Analysis")
        r = ttk.Frame(analysis); r.pack(fill=tk.X, pady=2)
        self._label(r, "Mode:", "tags = metadata/file names only, model = selected audio model only, learned = trained classifier, both/all combine sources.").pack(side=tk.LEFT)
        mode_combo = ttk.Combobox(r, textvariable=self.mode, values=("tags", "model", "both", "learned", "all"), state="readonly", width=10)
        mode_combo.pack(side=tk.LEFT, padx=5)
        full_track = ttk.Checkbutton(r, text="Full-track audio", variable=self.model_full_track)
        full_track.pack(side=tk.LEFT, padx=(4, 8))
        ToolTip(full_track, "Analyze the whole song by averaging 30s audio-model chunks. Slower, but usually more stable than one 30s clip.")
        self._track_dependency("audio_model", full_track)
        only_missing = ttk.Checkbutton(r, text="Only missing Grouping", variable=self.only_missing_grouping)
        only_missing.pack(side=tk.LEFT, padx=(4, 8))
        ToolTip(only_missing, "Skip tracks that already have Grouping/TIT1 filled. Skipped tagged rows are marked done.")
        prevent_sleep = ttk.Checkbutton(r, text="Prevent sleep while busy", variable=self.prevent_sleep)
        prevent_sleep.pack(side=tk.LEFT, padx=(4, 8))
        ToolTip(prevent_sleep, "Ask Windows not to enter sleep while analysis, training, writing, or other background work is running.")
        self._labeled_entry(r, "Priority:", self.recommendation_priority, 20, "Empty uses confidence-aware priority. Or enter manual,learned,tags,model.")
        r = ttk.Frame(analysis); r.pack(fill=tk.X, pady=2)
        self._label(r, "Preset:", "Known model presets ordered by expected usefulness for ClaveTagger. Future backends are documented but not runnable yet.").pack(side=tk.LEFT)
        preset_combo = ttk.Combobox(
            r,
            textvariable=self.audio_model_preset,
            values=audio_model_catalog.preset_labels(self.audio_model_presets),
            state="readonly",
            width=68,
        )
        preset_combo.pack(side=tk.LEFT, padx=5)
        preset_combo.bind("<<ComboboxSelected>>", self.on_audio_model_preset_selected)
        show_audio_button = self._button(r, "Show", self.show_audio_model_catalog, "Show the model preset list and practical ranking.")
        show_audio_button.pack(side=tk.LEFT)
        self._track_dependency("audio_model", preset_combo, show_audio_button)
        r = ttk.Frame(analysis); r.pack(fill=tk.X, pady=2)
        audio_model_entry = self._labeled_entry(r, "Audio model:", self.audio_model_id, 52, "Hugging Face audio-classification model id. Default is MAEST Discogs.")
        self._track_dependency("audio_model", audio_model_entry)
        ttk.Label(analysis, textvariable=self.audio_model_description, wraplength=940).pack(anchor="w", pady=(0, 4))
        r = ttk.Frame(analysis); r.pack(fill=tk.X, pady=2)
        self._label(r, "Learned backend:", "auto detects light/heavy from the selected classifier file; choose light/heavy manually only when needed.").pack(side=tk.LEFT)
        learned_backend_combo = ttk.Combobox(r, textvariable=self.classifier_backend, values=("auto", "light", "heavy"), state="readonly", width=8)
        learned_backend_combo.pack(side=tk.LEFT, padx=5)
        learned_backend_combo.bind("<<ComboboxSelected>>", self.on_classifier_backend_selected)
        learned_file_entry = self._labeled_entry(r, "Classifier file:", self.classifier_path, 34, "Trained light .joblib or heavy .pt model used by learned/all analysis.")
        learned_file_button = self._button(r, "Browse", self.browse_classifier, "Select the learned classifier file used during learned/all analysis.")
        learned_file_button.pack(side=tk.LEFT)
        self._track_dependency("learned_classifier", learned_backend_combo, learned_file_entry, learned_file_button)
        r = ttk.Frame(analysis); r.pack(fill=tk.X, pady=2)
        self._labeled_entry(r, "Config:", self.config_path, 28, "Category definitions, aliases, colors, tag patterns, and model label mapping.")
        self._button(r, "Browse", self.browse_config, "Select a category_config.json file.").pack(side=tk.LEFT)
        r = ttk.Frame(analysis); r.pack(fill=tk.X, pady=2)
        self._labeled_entry(r, "Overrides:", self.overrides_csv, 28, "Manual corrections CSV loaded before recommendations.")

        classifier = ttk.LabelFrame(groups, text="Classifier", padding=10)
        groups.add(classifier, text="Classifier")
        r = ttk.Frame(classifier); r.pack(fill=tk.X, pady=2)
        self._label(r, "Preset:", "Light is fast and uses existing report/detail features. Heavy presets train from audio; empty limits mean all tagged files and all chunks.").pack(side=tk.LEFT)
        preset = ttk.Combobox(r, textvariable=self.classifier_preset, values=classifier_presets.labels(), state="readonly", width=18)
        preset.pack(side=tk.LEFT, padx=5)
        preset.bind("<<ComboboxSelected>>", self.on_classifier_preset_selected)
        self._label(r, "Training source:", "Current loaded tracks uses the rows already shown in the table. Selected folders reload from folders. Input CSV reloads from the CSV field.").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Combobox(r, textvariable=self.training_source, values=("Current loaded tracks", "Selected folders", "Input CSV"), state="readonly", width=20).pack(side=tk.LEFT, padx=5)
        r = ttk.Frame(classifier); r.pack(fill=tk.X, pady=2)
        self._label(r, "Backend:", "light uses MAEST scores plus metadata features; heavy trains an audio classifier from whole tracks; auto chooses by file extension.").pack(side=tk.LEFT)
        backend_combo = ttk.Combobox(r, textvariable=self.classifier_backend, values=("light", "heavy", "auto"), state="readonly", width=8)
        backend_combo.pack(side=tk.LEFT, padx=5)
        backend_combo.bind("<<ComboboxSelected>>", self.on_classifier_backend_selected)
        classifier_use_entry = self._labeled_entry(r, "Use:", self.classifier_path, 24, "Existing classifier file used by learned/all analysis after it has already been trained.")
        classifier_use_button = self._button(r, "Browse", self.browse_classifier, "Select a trained classifier file for learned/all analysis.")
        classifier_use_button.pack(side=tk.LEFT)
        self._track_dependency("learned_classifier", classifier_use_entry, classifier_use_button)
        r = ttk.Frame(classifier); r.pack(fill=tk.X, pady=2)
        classifier_input_entry = self._labeled_entry(r, "Input:", self.classifier_input, 24, "Optional details CSV for light training. It supplies MAEST/model feature columns when the main rows do not have them.")
        classifier_input_button = self._button(r, "Browse", self.browse_classifier_input, "Select an optional details CSV used during light training.")
        classifier_input_button.pack(side=tk.LEFT)
        self._track_dependency("light_training", classifier_input_entry, classifier_input_button)
        self._labeled_entry(r, "Output:", self.classifier_output, 24, "Where the new trained model will be saved. Use this path later in Use classifier.")
        self._button(r, "Save as", self.browse_classifier_output, "Choose where the trained classifier will be saved.").pack(side=tk.LEFT)
        r = ttk.Frame(classifier); r.pack(fill=tk.X, pady=2)
        heavy_epochs_entry = self._labeled_entry(r, "Epochs:", self.heavy_epochs, 5, "Number of heavy-model training passes over the training data.")
        heavy_batch_entry = self._labeled_entry(r, "Batch:", self.heavy_batch_size, 5, "Number of audio chunks processed per training step.")
        heavy_lr_entry = self._labeled_entry(r, "LR:", self.heavy_learning_rate, 8, "Learning rate for heavy-model training.")
        heavy_max_files_entry = self._labeled_entry(r, "Max files:", self.heavy_max_files, 7, "Optional tagged-file limit for experiments. Empty means use all tagged files from the training source.")
        heavy_max_chunks_entry = self._labeled_entry(r, "Max chunks:", self.heavy_max_chunks, 7, "Optional chunks per file. Empty means use the whole song split into 30-second chunks.")
        self._track_dependency("heavy_training", heavy_epochs_entry, heavy_batch_entry, heavy_lr_entry, heavy_max_files_entry, heavy_max_chunks_entry)

        eval_group = ttk.LabelFrame(groups, text="Evaluation / Calibration / Actions", padding=10)
        groups.add(eval_group, text="Actions")
        r = ttk.Frame(eval_group); r.pack(fill=tk.X)
        self._labeled_entry(r, "Prediction:", self.prediction_column, 24, "CSV column used as the prediction during evaluation.")
        self._labeled_entry(r, "Truth:", self.truth_column, 24, "CSV column used as the known correct category, usually your current Grouping tag.")
        self._labeled_entry(r, "Tuned config:", self.calibration_output, 24, "Suggested config output. Calibration does not overwrite category_config.json directly.")
        self._labeled_entry(r, "Mismatches:", self.mismatch_output, 28, "CSV report with rows where prediction and truth disagree.")
        write_after = ttk.Checkbutton(r, text="Write after report dry-run", variable=self.write_after_report)
        write_after.pack(side=tk.LEFT, padx=8)
        ToolTip(write_after, "After analysis, run the write workflow as a dry-run using the chosen value/color columns.")
        value_column_entry = self._labeled_entry(r, "Value column:", self.value_column, 16, "Column used for grouping-only writes or write-after-report dry-run.")
        color_column_entry = self._labeled_entry(r, "Color column:", self.after_report_color_column, 16, "Optional color column used by write-after-report dry-run.")
        self._track_dependency("write_after_report_columns", value_column_entry, color_column_entry)

        ttk.Label(
            eval_group,
            text="Run estimate, analysis, training, evaluation, and calibration from the Actions menu.",
        ).pack(anchor="w", pady=(8, 0))
        self.notebook_tooltips.append(NotebookToolTip(self, groups, {
            0: "Output files for reports, details, progress resume cache, and logs.",
            1: "Analysis source selection: tag rules, MAEST audio model, learned classifier, and recommendation priority.",
            2: "Classifier files and training parameters for light/heavy learned models.",
            3: "Evaluation, calibration, and write-after-report settings.",
        }))

    def _build_progress_group(self, parent):
        frame = ttk.LabelFrame(parent, text="Progress", padding=10)
        frame.pack(fill=tk.X, pady=6)
        ToolTip(frame, "Shows current phase, current file, processed count, ETA, and whether cancellation is pending.")
        self.progress = ttk.Progressbar(frame, mode="determinate")
        self.progress.pack(fill=tk.X)
        self.status_label = ttk.Label(frame, text="Ready")
        self.status_label.pack(fill=tk.X, pady=(5, 0))
        ttk.Label(frame, textvariable=self.pending_tags_status).pack(fill=tk.X, pady=(2, 0))

    def _build_table_and_editor(self, parent):
        table_frame = ttk.Frame(parent)
        table_frame.pack(fill=tk.BOTH, expand=True)
        bulk = ttk.LabelFrame(table_frame, text="Bulk Correction", padding=6)
        bulk.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        bulk.columnconfigure(8, weight=1)
        ttk.Label(bulk, textvariable=self.selection_info, width=16).grid(row=0, column=0, sticky="w")
        target_label = self._label(bulk, "Target:", "Category to apply to every selected row as target_grouping.")
        target_label.grid(row=0, column=1, sticky="w", padx=(8, 2))
        bulk_combo = ttk.Combobox(bulk, textvariable=self.bulk_target_grouping, values=self.category_names, width=18)
        bulk_combo.grid(row=0, column=2, sticky="w", padx=4)
        bulk_combo.bind("<<ComboboxSelected>>", self.on_bulk_grouping_selected)
        color_label = self._label(bulk, "Color:", "Target Color value to save alongside the selected rows.")
        color_label.grid(row=0, column=3, sticky="w", padx=(8, 2))
        ttk.Entry(bulk, textvariable=self.bulk_target_color, width=12).grid(row=0, column=4, sticky="w", padx=4)
        self._button(bulk, "Apply", self.apply_bulk_correction, "Apply the bulk target/category values to all selected table rows.").grid(row=0, column=5, padx=(8, 4))
        self._button(bulk, "Save CSV", self.save_current_csv, "Save the edited table rows to the configured main CSV.").grid(row=0, column=6, padx=4)
        self._button(bulk, "Review", self.open_selected_review, "Open a detailed correction and playback window for the selected track.").grid(row=0, column=7, padx=4, sticky="w")
        ttk.Label(bulk, textvariable=self.pending_tags_status).grid(row=0, column=8, padx=(8, 4), sticky="e")
        self._button(bulk, "Dry-run pending", lambda: self.write_pending_tags(False), "Preview tag writes for all rows with pending target/recommended values.").grid(row=0, column=9, padx=4)
        self._button(bulk, "Write pending", lambda: self.write_pending_tags(True), "Write all pending target/recommended values to MP3 tags.").grid(row=0, column=10, padx=4)
        filter_label = self._label(bulk, "Filter:", "Filter the visible table rows. The full loaded row set stays in memory.")
        filter_label.grid(row=1, column=0, sticky="w", pady=(5, 0))
        filter_combo = ttk.Combobox(
            bulk,
            textvariable=self.table_filter,
            values=("All tracks", "Missing Grouping", "Tagged", "Pending tags", "Needs review"),
            state="readonly",
            width=18,
        )
        filter_combo.grid(row=1, column=1, sticky="w", padx=(8, 4), pady=(5, 0))
        filter_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_table_filter())
        self._button(bulk, "Clear dry-run", lambda: self.clear_selected_tags(False), "Preview clearing Grouping and Color tags from selected rows.").grid(row=1, column=9, padx=4, pady=(5, 0))
        self._button(bulk, "Clear tags", lambda: self.clear_selected_tags(True), "Clear Grouping and Color tags from selected rows after confirmation.").grid(row=1, column=10, padx=4, pady=(5, 0))
        note_label = self._label(bulk, "Note:", "Optional correction note written to manual_overrides.csv.")
        note_label.grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(5, 0))
        ttk.Entry(bulk, textvariable=self.bulk_note).grid(row=1, column=3, columnspan=2, sticky="ew", padx=(8, 0), pady=(5, 0))
        self._button(bulk, "Match playlist", self.match_label_playlist, "Match exported label playlists against the currently loaded tracks and prepare pending target tags.").grid(row=1, column=5, padx=4, pady=(5, 0), sticky="w")
        ToolTip(bulk, "Select multiple rows in the table, choose a category, then apply one correction to all selected tracks.")

        columns = (
            "file_name", "id3_grouping_normalized", "id3_color", "tag_suggested_grouping",
            "model_audio_suggested_grouping", "learned_suggested_grouping", "recommended_grouping",
            "target_grouping", "target_color", "recommended_source", "recommended_confidence", "model_audio_bpm",
        )
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=8, selectmode="extended")
        headings = {
            "file_name": "File", "id3_grouping_normalized": "Current Grouping", "id3_color": "Current Color",
            "tag_suggested_grouping": "Tag Guess", "model_audio_suggested_grouping": "MAEST Guess",
            "learned_suggested_grouping": "Learned Guess", "recommended_grouping": "Recommended",
            "target_grouping": "Target Grouping", "target_color": "Target Color",
            "recommended_source": "Source", "recommended_confidence": "Confidence", "model_audio_bpm": "BPM",
        }
        self.column_headings = dict(headings)
        widths = {"file_name": 240, "id3_grouping_normalized": 115, "id3_color": 95, "tag_suggested_grouping": 110,
                  "model_audio_suggested_grouping": 110, "learned_suggested_grouping": 110, "recommended_grouping": 110,
                  "target_grouping": 110, "target_color": 95, "recommended_source": 70, "recommended_confidence": 80, "model_audio_bpm": 55}
        for column in columns:
            self.tree.heading(column, text=headings[column], command=lambda selected=column: self.toggle_table_sort(selected))
            self.tree.column(column, width=widths[column], stretch=column == "file_name")
        self.tree.tag_configure("current", background="#ffe0a3")
        self.tree.tag_configure("done", background="#dcf7df")
        self.tree.tag_configure("completed", background="#eef3f8")
        self.tree.tag_configure("needs_review", background="#ffd6d6")
        self.tree.tag_configure("error", background="#ffd1d1")
        self.tree.tag_configure("queued", background="")
        yscroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self._virtual_yview)
        self.virtual_yscroll = yscroll
        xscroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(xscrollcommand=xscroll.set)
        self.tree.grid(row=1, column=0, sticky="nsew")
        yscroll.grid(row=1, column=1, sticky="ns")
        xscroll.grid(row=2, column=0, sticky="ew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(1, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self.on_row_selected)
        self.tree.bind("<Double-1>", self.open_selected_review)
        self.tree.bind("<Button-3>", self.show_table_menu)
        self.tree.bind("<MouseWheel>", self._on_virtual_mousewheel)
        self.tree.bind("<Button-4>", lambda _event: self._scroll_virtual_table(-3))
        self.tree.bind("<Button-5>", lambda _event: self._scroll_virtual_table(3))
        self.tree.bind("<Prior>", lambda _event: self._scroll_virtual_table(-self._virtual_page_size()))
        self.tree.bind("<Next>", lambda _event: self._scroll_virtual_table(self._virtual_page_size()))
        self.tree.bind("<Home>", lambda _event: self._set_virtual_table_start(0))
        self.tree.bind("<End>", lambda _event: self._set_virtual_table_start(max(0, len(self.filtered_row_indexes) - self.virtual_table_window)))
        self.table_menu = tk.Menu(self, tearoff=False)
        self.table_menu.add_command(label="Review / Correct", command=self.open_selected_review)
        self.table_menu.add_command(label="Play / Pause", command=self.toggle_play_pause)
        self.table_menu.add_command(label="Open externally", command=self.open_selected_external)
        self.table_menu.add_separator()
        self.table_menu.add_command(label="Clear Tags Dry Run", command=lambda: self.clear_selected_tags(False))
        self.table_menu.add_command(label="Clear Tags", command=lambda: self.clear_selected_tags(True))

    def _build_review_tab(self):
        outer = ttk.Frame(self.review_tab)
        outer.pack(fill=tk.BOTH, expand=True)
        editor = ttk.LabelFrame(outer, text="Manual Correction", padding=10)
        editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        player = ttk.LabelFrame(outer, text="Player", padding=10)
        player.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))

        ttk.Label(editor, textvariable=self.selected_info, wraplength=320).pack(fill=tk.X)
        self._label(editor, "Target Grouping:", "Manual category for the selected row. This updates target_grouping and can be saved as an override.").pack(anchor="w", pady=(8, 0))
        self.target_combo = ttk.Combobox(editor, textvariable=self.selected_target_grouping, values=self.category_names, width=28)
        self.target_combo.pack(fill=tk.X)
        self._label(editor, "Target Color:", "Manual color value for the selected row. It stays raw, for example #999999 or cyan.").pack(anchor="w", pady=(8, 0))
        ttk.Entry(editor, textvariable=self.selected_target_color).pack(fill=tk.X)
        self._label(editor, "Note:", "Optional explanation for the manual correction.").pack(anchor="w", pady=(8, 0))
        ttk.Entry(editor, textvariable=self.selected_note).pack(fill=tk.X)
        apply_button = self._button(editor, "Apply Correction", self.apply_correction, "Apply the selected-row correction to the table and manual overrides.")
        apply_button.pack(fill=tk.X, pady=(10, 2))
        save_button = self._button(editor, "Save CSV", self.save_current_csv, "Save the current in-memory rows to the configured main CSV.")
        save_button.pack(fill=tk.X, pady=2)
        dry_button = self._button(editor, "Write Tags Dry Run", lambda: self.write_selected_tags(False), "Preview tag writes for the selected row without modifying the MP3.")
        dry_button.pack(fill=tk.X, pady=2)
        write_button = self._button(editor, "Write Tags", lambda: self.write_selected_tags(True), "Write Grouping/Color tags for the selected row.")
        write_button.pack(fill=tk.X, pady=2)

        self._play_pause_button(player).pack(side=tk.LEFT)
        self._playback_button(player, "■", self.stop_playback).pack(side=tk.LEFT)
        self._playback_button(player, "↗", self.open_selected_external).pack(side=tk.LEFT, padx=4)
        self.seek = ttk.Scale(player, from_=0, to=300, variable=self.playback_seek, orient=tk.HORIZONTAL)
        self.seek.pack(fill=tk.X, pady=6)
        self._bind_seek_control(self.seek)
        ToolTip(self.seek, "Seek within the currently playing track.")
        ttk.Label(player, textvariable=self.playback_time).pack(anchor="w")

    def _build_log(self, parent, expand=False):
        log_frame = ttk.LabelFrame(parent, text="Log", padding=6)
        log_frame.pack(fill=tk.BOTH if expand else tk.X, expand=expand, pady=(8, 0))
        self.log = tk.Text(log_frame, height=12 if expand else 4, wrap="word")
        self.log.pack(fill=tk.BOTH if expand else tk.X, expand=expand)

    def _build_write_tab(self):
        form = ttk.LabelFrame(self.write_tab, text="Write Grouping / Color from CSV", padding=10)
        form.pack(fill=tk.X)
        row = ttk.Frame(form); row.pack(fill=tk.X, pady=3)
        self._labeled_entry(row, "CSV:", self.write_csv, 64, "CSV file used as the source for writing tags.")
        self._button(row, "Browse", self.browse_write_csv, "Select the CSV file to use for tag writing.").pack(side=tk.LEFT)
        row = ttk.Frame(form); row.pack(fill=tk.X, pady=3)
        self._labeled_entry(row, "Value column:", self.value_column, 20, "For grouping-only write mode.")
        self._labeled_entry(row, "Grouping column:", self.grouping_column, 20, "CSV column containing Grouping values to write.")
        self._labeled_entry(row, "Color column:", self.color_column, 20, "CSV column containing Color values to write.")
        only_empty = ttk.Checkbutton(row, text="Only when empty", variable=self.only_when_empty)
        only_empty.pack(side=tk.LEFT, padx=12)
        ToolTip(only_empty, "Skip files that already have the target tag filled.")
        apply_write = ttk.Checkbutton(row, text="Apply write", variable=self.apply_write)
        apply_write.pack(side=tk.LEFT, padx=5)
        ToolTip(apply_write, "Actually write MP3 tags. When off, the write action is only a dry-run.")
        row = ttk.Frame(form); row.pack(fill=tk.X, pady=(8, 0))
        write_tags = self._button(row, "Dry-run / write tags", self.run_write_tags, "Write or preview Grouping and Color using the configured columns.")
        write_tags.pack(side=tk.LEFT)
        write_grouping = self._button(row, "Dry-run / write grouping only", self.run_write_grouping_only, "Write or preview Grouping only using the Value column.")
        write_grouping.pack(side=tk.LEFT, padx=5)
        log_frame = ttk.LabelFrame(self.write_tab, text="Write log", padding=6)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=8)
        self.write_log = tk.Text(log_frame, height=20, wrap="word")
        self.write_log.pack(fill=tk.BOTH, expand=True)

    def add_folder(self):
        folder = filedialog.askdirectory(title="Select music folder")
        if folder and folder not in self.source_paths:
            self.source_paths.append(folder)
            self._refresh_folder_list()
            self.preview_sources()

    def add_subfolders_from_parent(self):
        parent = filedialog.askdirectory(title="Select parent folder")
        if not parent:
            return
        subfolders = [str(path) for path in sorted(Path(parent).iterdir()) if path.is_dir()]
        dialog = tk.Toplevel(self)
        dialog.title("Select subfolders")
        dialog.geometry("700x420")
        listbox = tk.Listbox(dialog, selectmode=tk.EXTENDED)
        listbox.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        for path in subfolders:
            listbox.insert(tk.END, path)
        def accept():
            for index in listbox.curselection():
                path = listbox.get(index)
                if path not in self.source_paths:
                    self.source_paths.append(path)
            dialog.destroy()
            self._refresh_folder_list()
            self.preview_sources()
        self._button(dialog, "Add Selected", accept, "Add all selected subfolders as recursive sources.").pack(pady=6)

    def manage_sources(self):
        dialog = tk.Toplevel(self)
        dialog.title("Sources")
        dialog.geometry("760x360")
        listbox = tk.Listbox(dialog, selectmode=tk.EXTENDED)
        listbox.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        def refresh():
            listbox.delete(0, tk.END)
            for path in self.source_paths:
                listbox.insert(tk.END, path)
            self._refresh_folder_list()

        def remove_selected():
            selected = set(listbox.curselection())
            removed = [path for index, path in enumerate(self.source_paths) if index in selected]
            self.source_paths = [path for index, path in enumerate(self.source_paths) if index not in selected]
            self._remove_preview_rows_for_sources(removed)
            refresh()
            self.preview_sources()

        def add_one():
            folder = filedialog.askdirectory(title="Select music folder", parent=dialog)
            if folder and folder not in self.source_paths:
                self.source_paths.append(folder)
                refresh()
                self.preview_sources()

        def clear_all():
            self.source_paths = []
            self.rows = []
            self._clear_table_state()
            refresh()
            self.status_label.configure(text="Folders cleared.")

        buttons = ttk.Frame(dialog)
        buttons.pack(fill=tk.X, padx=8, pady=(0, 8))
        self._button(buttons, "Add Folder", add_one, "Add one more source folder.").pack(side=tk.LEFT)
        self._button(buttons, "Remove Selected", remove_selected, "Remove selected source folders from this run.").pack(side=tk.LEFT, padx=5)
        self._button(buttons, "Clear", clear_all, "Remove all selected source folders and clear the preview table.").pack(side=tk.LEFT)
        self._button(buttons, "Close", dialog.destroy, "Close source management.").pack(side=tk.RIGHT)
        refresh()

    def remove_selected_folders(self):
        self.manage_sources()

    def clear_folders(self):
        self.source_paths = []
        self._refresh_folder_list()
        self.rows = []
        self._clear_table_state()
        self.status_label.configure(text="Folders cleared.")

    def _refresh_folder_list(self):
        if not self.source_paths:
            self.source_summary.set("No source selected")
        elif len(self.source_paths) == 1:
            self.source_summary.set(Path(self.source_paths[0]).name or self.source_paths[0])
        else:
            self.source_summary.set(f"{len(self.source_paths)} source folders")

    def _remove_preview_rows_for_sources(self, removed_sources):
        if not removed_sources:
            return
        self.rows = gui_services.rows_without_source_folders(self.rows, removed_sources)
        self.message_queue.put(("rows_loaded", self.rows))

    def browse_input_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if path:
            self.input_csv.set(path)
            self.preview_sources()

    def browse_output_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if path:
            self.output_csv.set(path)

    def browse_details_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if path:
            self.details_csv.set(path)

    def browse_write_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if path:
            self.write_csv.set(path)

    def browse_config(self):
        path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if path:
            self.config_path.set(path)

    def _audio_model_description(self, preset):
        status = preset.get("status", "")
        model_id = preset.get("model_id") or "no model id"
        return (
            f"{preset.get('name', 'Model')} | rank {preset.get('rank', '?')} | {status} | "
            f"{preset.get('speed', 'unknown speed')} | {model_id}. "
            f"{preset.get('expected_accuracy', '')} {preset.get('description', '')}"
        ).strip()

    def on_audio_model_preset_selected(self, _event=None):
        preset = audio_model_catalog.find_by_label(self.audio_model_preset.get(), self.audio_model_presets)
        if not preset:
            return
        self.audio_model_description.set(self._audio_model_description(preset))
        if preset.get("kind") == "learned":
            self.mode.set("learned")
            return
        if preset.get("status") != "supported":
            return
        if preset.get("model_id"):
            self.audio_model_id.set(preset["model_id"])
            if self.mode.get() == "learned":
                self.mode.set("model")

    def show_audio_model_catalog(self):
        messagebox.showinfo("Audio model presets", audio_model_catalog.format_catalog(self.audio_model_presets))

    def reload_env_file(self, show_status=True):
        status = app_env.load_env_file(self.env_file.get().strip() or ".env")
        self.hf_token_status.set(f"HF token: {app_env.hf_token_status()}")
        message = app_env.env_status_message(status)
        app_logging.log_info(message)
        if show_status and hasattr(self, "status_label"):
            self.status_label.configure(text=message)
            self._append_log(message)

    def on_classifier_preset_selected(self, _event=None):
        preset = classifier_presets.get(self.classifier_preset.get())
        self.classifier_backend.set(preset["backend"])
        self._sync_classifier_paths_for_backend(preset["backend"])
        if preset["backend"] == "heavy":
            self.heavy_epochs.set(str(preset["epochs"]))
            self.heavy_batch_size.set(str(preset["batch_size"]))
            self.heavy_learning_rate.set(str(preset["learning_rate"]))
            self.heavy_max_files.set("" if preset["max_files"] is None else str(preset["max_files"]))
            self.heavy_max_chunks.set("" if preset["max_chunks_per_file"] is None else str(preset["max_chunks_per_file"]))
        self.status_label.configure(text=preset["description"])

    def on_classifier_backend_selected(self, _event=None):
        backend = self.classifier_backend.get()
        self._sync_classifier_paths_for_backend(backend)

    def _sync_classifier_paths_for_backend(self, backend):
        classifier_path, classifier_output = gui_services.sync_classifier_paths_for_backend(
            backend,
            self.classifier_path.get().strip(),
            self.classifier_output.get().strip(),
        )
        self.classifier_path.set(classifier_path)
        self.classifier_output.set(classifier_output)

    def show_model_comparison_window(self, comparison_rows, fieldnames):
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
            listbox.delete(0, tk.END)
            for path in paths:
                listbox.insert(tk.END, path)

        def add_files():
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
        category_combo = ttk.Combobox(
            options_frame,
            textvariable=category_value,
            values=[infer_label] + self.category_names,
            state="readonly",
            width=28,
        )
        category_combo.grid(row=0, column=1, sticky="w", padx=8, pady=2)
        self._label(options_frame, "Min score:", "Strict artist/title similarity threshold. 0.94 is conservative.").grid(row=1, column=0, sticky="w")
        ttk.Entry(options_frame, textvariable=min_score_value, width=8).grid(row=1, column=1, sticky="w", padx=8, pady=2)
        self._label(options_frame, "Output CSV:", "CSV report with every playlist row, local match, score, status, and target tag values.").grid(row=2, column=0, sticky="w")
        output_row = ttk.Frame(options_frame)
        output_row.grid(row=2, column=1, sticky="ew", padx=8, pady=2)
        output_row.columnconfigure(0, weight=1)
        ttk.Entry(output_row, textvariable=output_value).grid(row=0, column=0, sticky="ew")

        def browse_output():
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
        options = self._label_playlist_options_dialog()
        if not options:
            return
        if not self.rows and not self.source_paths and not self.input_csv.get().strip():
            messagebox.showinfo("No local tracks", "Load local tracks first, or add source folders before matching a playlist.")
            return

        def worker():
            try:
                def phase(message):
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

    def browse_classifier(self):
        path = filedialog.askopenfilename(filetypes=[("Model files", "*.joblib *.pt"), ("All files", "*.*")])
        if path:
            self.classifier_path.set(path)
            self.classifier_backend.set(learning.detect_classifier_backend(path))

    def browse_classifier_input(self):
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if path:
            self.classifier_input.set(path)

    def browse_classifier_output(self):
        path = filedialog.asksaveasfilename(filetypes=[("Model files", "*.joblib *.pt"), ("All files", "*.*")])
        if path:
            self.classifier_output.set(path)

    def _append_log(self, message, write=False):
        app_logging.log_info(message)
        target = self.write_log if write else self.log
        target.insert(tk.END, message + "\n")
        target.see(tk.END)

    def _set_busy(self, busy):
        self.config(cursor="")
        self.abort_button.configure(state="normal" if busy else "disabled")
        if busy and self.prevent_sleep.get() and not self.prevent_sleep_active:
            self.prevent_sleep_active = power.prevent_sleep()
            if self.prevent_sleep_active:
                self._append_log("Windows sleep prevention enabled while task is running.")
            elif power.is_windows():
                self._append_log("Windows sleep prevention could not be enabled.")
        if not busy:
            self.progress.stop()
            self.progress.configure(mode="determinate")
            if self.prevent_sleep_active:
                power.allow_sleep()
                self.prevent_sleep_active = False
                self._append_log("Windows sleep prevention released.")

    def _start_worker(self, target):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("Busy", "A task is already running.")
            return
        self._save_gui_settings()
        self.cancel_token = CancelToken()
        self._set_busy(True)
        self.worker_thread = threading.Thread(target=target, daemon=True, name="ClaveTaggerWorker")
        self.worker_thread.start()

    def abort_current_task(self):
        if self.cancel_token:
            self.cancel_token.cancel()
            self.status_label.configure(text="Cancelling after current step...")
            self._append_log("Cancellation requested.")

    def _optional_int(self, value):
        return int(value) if str(value).strip() else None

    def _report_options(self):
        return gui_services.ReportOptions(
            source_paths=list(self.source_paths), input_csv=self.input_csv.get().strip(),
            output_csv=self.output_csv.get().strip(), details_csv=self.details_csv.get().strip(),
            model_comparison_csv=self.model_comparison_csv.get().strip(),
            progress_json=self.progress_json.get().strip(), config_path=self.config_path.get().strip(),
            classifier_path=self.classifier_path.get().strip(), classifier_input=self.classifier_input.get().strip(),
            classifier_output=self.classifier_output.get().strip(), classifier_backend=self.classifier_backend.get(),
            recommendation_priority=self.recommendation_priority.get(), mode=self.mode.get(), audio_model_id=self.audio_model_id.get().strip(), model_full_track=self.model_full_track.get(), use_details=self.use_details.get(),
            prediction_column=self.prediction_column.get().strip(), truth_column=self.truth_column.get().strip(),
            overrides_csv=self.overrides_csv.get().strip(), log_file=self.log_file.get().strip(), env_file=self.env_file.get().strip(),
            write_after_report=self.write_after_report.get(), value_column=self.value_column.get().strip(),
            color_column_after_report=self.after_report_color_column.get().strip(),
            only_missing_grouping=self.only_missing_grouping.get(), cancel_token=self.cancel_token,
            artifact_policy="resume", artifact_backup_dir="backups",
        )

    def _train_options(self):
        return gui_services.TrainOptions(
            source_paths=list(self.source_paths), input_csv=self.input_csv.get().strip(),
            details_csv=self.details_csv.get().strip(), config_path=self.config_path.get().strip(),
            classifier_path=self.classifier_path.get().strip(), classifier_input=self.classifier_input.get().strip(),
            classifier_output=self.classifier_output.get().strip(), classifier_backend=self.classifier_backend.get(),
            classifier_preset=classifier_presets.name_for_label(self.classifier_preset.get()),
            training_source=self.training_source.get(),
            mode=self.mode.get(), use_details=self.use_details.get(), heavy_epochs=int(self.heavy_epochs.get() or "8"),
            heavy_batch_size=int(self.heavy_batch_size.get() or "8"), heavy_learning_rate=float(self.heavy_learning_rate.get() or "0.001"),
            heavy_max_files=self._optional_int(self.heavy_max_files.get()), heavy_max_chunks_per_file=self._optional_int(self.heavy_max_chunks.get()),
            truth_column=self.truth_column.get().strip(), log_file=self.log_file.get().strip(), env_file=self.env_file.get().strip(), cancel_token=self.cancel_token,
            artifact_policy="resume", artifact_backup_dir="backups",
        )

    def _write_options(self, grouping_column=None, color_column=None, apply_write=None):
        return gui_services.WriteOptions(
            csv_path=self.write_csv.get().strip(), config_path=self.config_path.get().strip(),
            grouping_column=grouping_column if grouping_column is not None else self.grouping_column.get().strip(),
            color_column=color_column if color_column is not None else self.color_column.get().strip(),
            apply_write=self.apply_write.get() if apply_write is None else apply_write, only_when_empty=self.only_when_empty.get(),
        )

    def _choose_artifact_policy(self, action, options):
        found = gui_services.detect_existing_artifacts(action, options)
        if not found:
            return "resume"

        result = tk.StringVar(value="")
        dialog = tk.Toplevel(self)
        dialog.title("Existing cache/CSV files")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding=14)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            frame,
            text=f"{action.title()} found existing runtime files.",
            font=("", 10, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            frame,
            text="Use them to resume, or start fresh by moving them to a timestamped backup folder.",
            wraplength=520,
        ).pack(anchor="w", pady=(6, 8))
        listbox = tk.Listbox(frame, width=82, height=min(8, max(3, len(found))))
        listbox.pack(fill=tk.X)
        for path in found:
            listbox.insert(tk.END, str(path))
        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X, pady=(12, 0))

        def choose(value):
            result.set(value)
            dialog.destroy()

        ttk.Button(buttons, text="Use existing cache/CSV", command=lambda: choose("resume")).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Start fresh with backup", command=lambda: choose("fresh")).pack(side=tk.LEFT, padx=8)
        ttk.Button(buttons, text="Cancel", command=lambda: choose("")).pack(side=tk.RIGHT)
        dialog.protocol("WM_DELETE_WINDOW", lambda: choose(""))
        dialog.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - dialog.winfo_width()) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")
        self.wait_window(dialog)
        return result.get() or None

    def preview_sources(self):
        if not self.source_paths and not self.input_csv.get().strip():
            self.rows = []
            self._clear_table_state()
            self.message_queue.put(("rows_loaded", []))
            self.message_queue.put(("status", "Preview cleared. Add a folder or input CSV when ready."))
            return
        def worker():
            try:
                self.message_queue.put(("phase", "Preview: scanning folders and reading current tags..."))
                rows = gui_services.preview_rows(
                    self.source_paths,
                    self.input_csv.get().strip(),
                    self.config_path.get().strip(),
                    progress_callback=lambda payload: self.message_queue.put(("load_progress", payload)),
                )
                self.rows = rows
                self.message_queue.put(("rows_loaded", rows))
                self.message_queue.put(("status", f"Preview loaded {len(rows)} tracks."))
            except Exception as error:
                app_logging.log_exception("preview failed", error)
                self.message_queue.put(("error", str(error)))
            finally:
                self.message_queue.put(("done", None))
        self._start_worker(worker)

    def estimate_report(self):
        def worker():
            try:
                def phase(message):
                    self.message_queue.put(("phase", message))
                _rows, status = gui_services.estimate_report(
                    self._report_options(),
                    status_callback=phase,
                    progress_callback=lambda payload: self.message_queue.put(("load_progress", payload)),
                )
                self.message_queue.put(("status", status))
            except Exception as error:
                app_logging.log_exception("estimate failed", error)
                self.message_queue.put(("error", str(error)))
            finally:
                self.message_queue.put(("done", None))
        self._start_worker(worker)

    def run_report(self):
        current_table_rows = self._rows_in_table_order() if self.rows else []
        options = self._report_options()
        policy = self._choose_artifact_policy("analyze", options)
        if policy is None:
            return
        options.artifact_policy = policy

        def worker():
            try:
                def phase(message):
                    self.message_queue.put(("phase", message))

                if current_table_rows:
                    phase("Analyze: using the current table order...")
                    rows = current_table_rows
                else:
                    phase("Analyze: scanning folders and reading current tags...")
                    rows = gui_services.preview_rows(
                        options.source_paths,
                        options.input_csv,
                        options.config_path,
                        progress_callback=lambda payload: self.message_queue.put(("load_progress", payload)),
                    )
                self.rows = rows
                self.message_queue.put(("rows_loaded", rows))
                phase(f"Analyze: loaded {len(rows)} tracks. Preparing initial recommendations...")
                gui_services.refresh_recommendations(rows, options.mode, options.recommendation_priority)
                if options.only_missing_grouping:
                    skipped = 0
                    for row in rows:
                        row["_analysis_skipped_existing_grouping"] = gui_services.has_existing_grouping(row)
                        if row["_analysis_skipped_existing_grouping"]:
                            row["_gui_status"] = "done"
                            skipped += 1
                    if skipped:
                        phase(f"Analyze: {skipped} already tagged tracks marked done; first yellow row is the next missing Grouping.")
                self.message_queue.put(("rows_refresh", rows))
                phase(f"Analyze: starting {options.mode} report...")
                rows, status = gui_services.run_report(
                    options,
                    lambda payload: self.message_queue.put(("model_progress", payload)),
                    lambda payload: self.message_queue.put(("learned_progress", payload)),
                    rows=rows,
                    status_callback=phase,
                )
                self.rows = rows
                self.message_queue.put(("rows_analyzed", rows))
                self.message_queue.put(("status", status))
            except CancelledError:
                self.message_queue.put(("status", "Cancelled. Completed progress was preserved."))
            except Exception as error:
                app_logging.log_exception("analyze failed", error)
                self.message_queue.put(("error", str(error)))
            finally:
                self.message_queue.put(("done", None))
        self._start_worker(worker)

    def compare_audio_models(self):
        options = self._report_options()
        policy = self._choose_artifact_policy("compare", options)
        if policy is None:
            return
        options.artifact_policy = policy

        def worker():
            try:
                def phase(message):
                    self.message_queue.put(("phase", message))
                phase("Compare models: scanning folders and reading current tags...")
                rows = gui_services.preview_rows(
                    options.source_paths,
                    options.input_csv,
                    options.config_path,
                    progress_callback=lambda payload: self.message_queue.put(("load_progress", payload)),
                )
                self.rows = rows
                self.message_queue.put(("rows_loaded", rows))
                rows, comparison_rows, fieldnames, status = gui_services.compare_audio_models(
                    options,
                    lambda payload: self.message_queue.put(("model_progress", payload)),
                    rows=rows,
                    status_callback=phase,
                )
                self.rows = rows
                self.message_queue.put(("rows_refresh", rows))
                self.message_queue.put(("comparison_result", (comparison_rows, fieldnames)))
                self.message_queue.put(("status", status))
            except CancelledError:
                self.message_queue.put(("status", "Audio model comparison cancelled. Completed progress was preserved."))
            except Exception as error:
                app_logging.log_exception("audio model comparison failed", error)
                self.message_queue.put(("error", str(error)))
            finally:
                self.message_queue.put(("done", None))
        self._start_worker(worker)

    def train_classifier(self):
        options = self._train_options()
        policy = self._choose_artifact_policy("train", options)
        if policy is None:
            return
        options.artifact_policy = policy

        def worker():
            try:
                def train_callback(payload):
                    self.message_queue.put(("training_progress", payload))
                def phase(message):
                    self.message_queue.put(("phase", message))
                rows = None
                if options.training_source == "Current loaded tracks":
                    phase("Training: using current loaded tracks...")
                    rows = list(self.rows) if self.rows else gui_services.preview_rows(
                        options.source_paths,
                        options.input_csv,
                        options.config_path,
                        progress_callback=lambda payload: self.message_queue.put(("load_progress", payload)),
                    )
                elif options.training_source == "Selected folders":
                    phase("Training: scanning selected folders and reading current tags...")
                    rows = gui_services.preview_rows(
                        options.source_paths,
                        "",
                        options.config_path,
                        progress_callback=lambda payload: self.message_queue.put(("load_progress", payload)),
                    )
                elif options.training_source == "Input CSV":
                    phase("Training: loading rows from input CSV...")
                    rows = gui_services.preview_rows(
                        [],
                        self.input_csv.get().strip(),
                        options.config_path,
                        progress_callback=lambda payload: self.message_queue.put(("load_progress", payload)),
                    )
                self.rows = rows
                self.message_queue.put(("rows_loaded", rows))
                phase(f"Training: loaded {len(rows)} tracks. Starting classifier workflow...")
                rows, _trained, status = gui_services.train_classifier(
                    options,
                    progress_callback=train_callback,
                    rows=rows,
                    status_callback=phase,
                )
                self.rows = rows
                self.message_queue.put(("rows_refresh", rows))
                self.message_queue.put(("status", status))
            except CancelledError:
                self.message_queue.put(("status", "Training cancelled."))
            except Exception as error:
                app_logging.log_exception("training failed", error)
                self.message_queue.put(("error", str(error)))
            finally:
                self.message_queue.put(("done", None))
        self._start_worker(worker)

    def evaluate_report(self):
        def worker():
            try:
                def phase(message):
                    self.message_queue.put(("phase", message))
                options = gui_services.EvaluationOptions(list(self.source_paths), self.input_csv.get(), self.mode.get(), self.config_path.get(), self.prediction_column.get(), self.truth_column.get())
                _rows, status = gui_services.evaluate_report(
                    options,
                    status_callback=phase,
                    progress_callback=lambda payload: self.message_queue.put(("load_progress", payload)),
                )
                self.message_queue.put(("status", status))
            except Exception as error:
                app_logging.log_exception("evaluation failed", error)
                self.message_queue.put(("error", str(error)))
            finally:
                self.message_queue.put(("done", None))
        self._start_worker(worker)

    def calibrate_report(self):
        def worker():
            try:
                def phase(message):
                    self.message_queue.put(("phase", message))
                input_csv = self.input_csv.get().strip() or self.output_csv.get().strip()
                options = gui_services.CalibrationOptions(input_csv, self.calibration_output.get().strip(), self.mismatch_output.get().strip(), self.truth_column.get().strip())
                _tuned, _examples, status = gui_services.calibrate(options, status_callback=phase)
                self.message_queue.put(("status", status))
            except Exception as error:
                app_logging.log_exception("calibration failed", error)
                self.message_queue.put(("error", str(error)))
            finally:
                self.message_queue.put(("done", None))
        self._start_worker(worker)

    def run_write_tags(self):
        def worker():
            try:
                def phase(message):
                    self.message_queue.put(("phase", message))
                changes, skipped = gui_services.run_write_tags(
                    self._write_options(),
                    lambda msg: self.message_queue.put(("write_log", msg)),
                    progress_callback=lambda payload: self.message_queue.put(("write_progress", payload)),
                    status_callback=phase,
                )
                self.message_queue.put(("status", f"Write tags finished. Planned changes: {len(changes)} | skipped: {skipped}"))
            except Exception as error:
                app_logging.log_exception("write tags failed", error)
                self.message_queue.put(("error", str(error)))
            finally:
                self.message_queue.put(("done", None))
        self._start_worker(worker)

    def run_write_grouping_only(self):
        def worker():
            try:
                def phase(message):
                    self.message_queue.put(("phase", message))
                changes, skipped = gui_services.run_write_tags(
                    self._write_options(grouping_column=self.value_column.get().strip(), color_column=""),
                    lambda msg: self.message_queue.put(("write_log", msg)),
                    progress_callback=lambda payload: self.message_queue.put(("write_progress", payload)),
                    status_callback=phase,
                )
                self.message_queue.put(("status", f"Write grouping finished. Planned changes: {len(changes)} | skipped: {skipped}"))
            except Exception as error:
                app_logging.log_exception("write grouping failed", error)
                self.message_queue.put(("error", str(error)))
            finally:
                self.message_queue.put(("done", None))
        self._start_worker(worker)

    def _selected_row(self):
        selected = self.tree.selection()
        if not selected:
            return None
        file_path = selected[0]
        for row in self.rows:
            if row.get("file_path") == file_path:
                return row
        return None

    def _selected_rows(self):
        selected = set(self.tree.selection())
        return [row for row in self.rows if row.get("file_path") in selected]

    def _rows_in_table_order(self):
        return list(self.rows)

    def on_row_selected(self, _event=None):
        row = self._selected_row()
        selected_count = len(self.tree.selection())
        self.selection_info.set(f"{selected_count} selected" if selected_count else "No tracks selected")
        if not row:
            return
        self.selected_info.set(f"{row.get('file_name', '')}\nRecommended: {row.get('recommended_grouping', '')} ({row.get('recommended_source', '')})")
        self.selected_target_grouping.set(row.get("target_grouping") or row.get("recommended_grouping", ""))
        self.selected_target_color.set(row.get("target_color") or row.get("id3_color", ""))
        self.selected_note.set(row.get("manual_note", ""))

    def show_table_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.tree.focus(item)
            self.on_row_selected()
            self.table_menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def _review_details_text(self, row):
        fields = [
            ("File", row.get("file_name", "")),
            ("Path", row.get("file_path", "")),
            ("Artist", row.get("artist", "")),
            ("Title", row.get("title", "")),
            ("Album", row.get("album", "")),
            ("Genre", row.get("genre", "")),
            ("Current Grouping", row.get("id3_grouping_normalized", "")),
            ("Raw Grouping", row.get("id3_grouping", "")),
            ("Current Color", row.get("id3_color", "")),
            ("Tag Guess", f"{row.get('tag_suggested_grouping', '')} ({row.get('tag_confidence', '')})"),
            ("Tag Reason", row.get("tag_reason", "")),
            ("MAEST Guess", f"{row.get('model_audio_suggested_grouping', '')} ({row.get('model_audio_confidence', '')})"),
            ("MAEST BPM", row.get("model_audio_bpm", "")),
            ("MAEST Top Labels", row.get("model_audio_top_labels", "")),
            ("MAEST Reason", row.get("model_audio_reason", "")),
            ("Learned Guess", f"{row.get('learned_suggested_grouping', '')} ({row.get('learned_confidence', '')})"),
            ("Learned Reason", row.get("learned_reason", "")),
            ("Recommended", f"{row.get('recommended_grouping', '')} ({row.get('recommended_source', '')}, {row.get('recommended_confidence', '')})"),
            ("Target Grouping", row.get("target_grouping", "")),
            ("Target Color", row.get("target_color", "")),
        ]
        return "\n".join(f"{label}: {value}" for label, value in fields if value)

    def open_selected_review(self, _event=None):
        if _event is not None and hasattr(_event, "y"):
            item = self.tree.identify_row(_event.y)
            if item:
                self.tree.selection_set(item)
                self.tree.focus(item)
        row = self._selected_row()
        if not row:
            messagebox.showinfo("No track", "Select a track first.")
            return
        self.on_row_selected()
        window = tk.Toplevel(self)
        window.title(f"Review - {row.get('file_name', '')}")
        window.geometry("860x560+80+80")
        window.transient(self)

        container = ttk.Frame(window, padding=10)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(0, weight=3)
        container.columnconfigure(1, weight=2)
        container.rowconfigure(0, weight=1)

        detail_frame = ttk.LabelFrame(container, text="Track Details", padding=8)
        detail_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        details = tk.Text(detail_frame, wrap="word", height=20)
        details.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        detail_scroll = ttk.Scrollbar(detail_frame, orient=tk.VERTICAL, command=details.yview)
        detail_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        details.configure(yscrollcommand=detail_scroll.set)
        details.insert("1.0", self._review_details_text(row))
        details.configure(state="disabled")

        def refresh_review_details():
            current = self._selected_row()
            if not current:
                return
            window.title(f"Review - {current.get('file_name', '')}")
            details.configure(state="normal")
            details.delete("1.0", tk.END)
            details.insert("1.0", self._review_details_text(current))
            details.configure(state="disabled")

        def move_review(offset):
            if not self.filtered_row_indexes:
                return
            selected = self.tree.selection()
            selected_path = selected[0] if selected else row.get("file_path", "")
            row_by_path = {current.get("file_path", ""): index for index, current in enumerate(self.rows)}
            current_row_index = row_by_path.get(selected_path, self.filtered_row_indexes[0])
            try:
                current_position = self.filtered_row_indexes.index(current_row_index)
            except ValueError:
                current_position = 0
            next_position = min(len(self.filtered_row_indexes) - 1, max(0, current_position + offset))
            next_row = self.rows[self.filtered_row_indexes[next_position]]
            self._scroll_row_into_view(next_row)
            next_item = next_row.get("file_path", "")
            if next_item in self.row_by_path:
                self.tree.selection_set(next_item)
                self.tree.focus(next_item)
                self.tree.see(next_item)
            self.on_row_selected()
            refresh_review_details()

        def apply_and_refresh():
            self.apply_correction()
            refresh_review_details()

        def apply_and_next():
            self.apply_correction()
            move_review(1)

        edit_frame = ttk.LabelFrame(container, text="Correction / Playback", padding=8)
        edit_frame.grid(row=0, column=1, sticky="nsew")
        edit_frame.columnconfigure(0, weight=1)
        nav = ttk.Frame(edit_frame)
        nav.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self._button(nav, "<", lambda: move_review(-1), "Move to the previous track in the main table without closing this review window.").pack(side=tk.LEFT)
        self._button(nav, ">", lambda: move_review(1), "Move to the next track in the main table without closing this review window.").pack(side=tk.LEFT, padx=4)
        self._button(nav, "Apply >", apply_and_next, "Apply the current manual correction, then move to the next track.").pack(side=tk.LEFT)
        self._label(edit_frame, "Target Grouping:", "Manual category for this track.").grid(row=1, column=0, sticky="w")
        target_combo = ttk.Combobox(edit_frame, textvariable=self.selected_target_grouping, values=self.category_names, width=28)
        target_combo.grid(row=2, column=0, sticky="ew", pady=(2, 8))
        target_combo.bind("<<ComboboxSelected>>", self.on_target_grouping_selected)
        self._label(edit_frame, "Target Color:", "Raw Color tag value to save, for example #999999 or cyan.").grid(row=3, column=0, sticky="w")
        ttk.Entry(edit_frame, textvariable=self.selected_target_color).grid(row=4, column=0, sticky="ew", pady=(2, 8))
        self._label(edit_frame, "Note:", "Optional note saved to manual_overrides.csv.").grid(row=5, column=0, sticky="w")
        ttk.Entry(edit_frame, textvariable=self.selected_note).grid(row=6, column=0, sticky="ew", pady=(2, 8))

        buttons = ttk.Frame(edit_frame)
        buttons.grid(row=7, column=0, sticky="ew", pady=(4, 10))
        self._button(buttons, "Apply Correction", apply_and_refresh, "Apply correction to this row and manual overrides.").pack(side=tk.LEFT)
        self._button(buttons, "Save CSV", self.save_current_csv, "Save current table to the main CSV.").pack(side=tk.LEFT, padx=4)

        write_buttons = ttk.Frame(edit_frame)
        write_buttons.grid(row=8, column=0, sticky="ew", pady=(0, 12))
        self._button(write_buttons, "Write Dry Run", lambda: self.write_selected_tags(False), "Preview tag writes for this track.").pack(side=tk.LEFT)
        self._button(write_buttons, "Write Tags", lambda: self.write_selected_tags(True), "Write Grouping/Color for this track.").pack(side=tk.LEFT, padx=4)
        self._button(write_buttons, "Clear Dry Run", lambda: self.clear_selected_tags(False), "Preview clearing Grouping and Color for this track.").pack(side=tk.LEFT)
        self._button(write_buttons, "Clear Tags", lambda: self.clear_selected_tags(True), "Clear Grouping and Color for this track after confirmation.").pack(side=tk.LEFT, padx=4)

        player = ttk.LabelFrame(edit_frame, text="Player", padding=8)
        player.grid(row=9, column=0, sticky="ew")
        self._play_pause_button(player).pack(side=tk.LEFT)
        self._playback_button(player, "■", self.stop_playback).pack(side=tk.LEFT)
        self._playback_button(player, "↗", self.open_selected_external).pack(side=tk.LEFT, padx=4)
        seek = ttk.Scale(player, from_=0, to=300, variable=self.playback_seek, orient=tk.HORIZONTAL)
        seek.pack(fill=tk.X, expand=True, padx=4)
        self._bind_seek_control(seek)
        ttk.Label(edit_frame, textvariable=self.playback_time).grid(row=10, column=0, sticky="w", pady=(6, 0))

    def on_bulk_grouping_selected(self, _event=None):
        grouping = self.bulk_target_grouping.get().strip()
        if grouping:
            self.bulk_target_color.set(config.category_to_color(grouping))

    def on_target_grouping_selected(self, _event=None):
        grouping = self.selected_target_grouping.get().strip()
        if grouping:
            self.selected_target_color.set(config.category_to_color(grouping))

    def apply_correction(self):
        row = self._selected_row()
        if not row:
            messagebox.showinfo("No track", "Select a track first.")
            return
        row["manual_grouping"] = self.selected_target_grouping.get().strip()
        row["manual_color"] = self.selected_target_color.get().strip()
        row["target_grouping"] = row["manual_grouping"]
        row["target_color"] = row["manual_color"]
        row["manual_note"] = self.selected_note.get().strip()
        row.pop("_suppress_pending_recommendation", None)
        gui_services.save_manual_override(self.overrides_csv.get(), row, row["manual_grouping"], row["manual_color"], row["manual_note"])
        gui_services.refresh_recommendations(self.rows, self.mode.get(), self.recommendation_priority.get())
        self._update_pending_path(row)
        self._insert_or_update_row(row, status="done")
        self._append_log(f"Manual correction saved for {row.get('file_name', '')}.")

    def apply_bulk_correction(self):
        selected_rows = self._selected_rows()
        if not selected_rows:
            messagebox.showinfo("No tracks", "Select one or more tracks in the table first.")
            return
        grouping = self.bulk_target_grouping.get().strip()
        if not grouping:
            messagebox.showinfo("No category", "Choose a target grouping first.")
            return
        updated = gui_services.apply_manual_corrections(
            self.rows,
            [row.get("file_path", "") for row in selected_rows],
            grouping,
            self.bulk_target_color.get().strip(),
            self.bulk_note.get().strip(),
            self.overrides_csv.get().strip(),
            self.mode.get(),
            self.recommendation_priority.get(),
            self.config_path.get().strip(),
        )
        for row in selected_rows:
            row.pop("_suppress_pending_recommendation", None)
            self._update_pending_path(row)
            self._insert_or_update_row(row, status="done")
        self._append_log(f"Bulk correction saved for {updated} tracks.")

    def save_current_csv(self):
        if not self.rows:
            return
        core.write_csv(self.output_csv.get(), self.rows, core.MAIN_FIELDNAMES)
        self._append_log(f"Saved {self.output_csv.get()}.")

    def _write_candidate_grouping(self, row):
        target = (row.get("target_grouping") or "").strip()
        if target:
            return target
        if row.get("_suppress_pending_recommendation"):
            return ""
        recommended = (row.get("recommended_grouping") or "").strip()
        confidence = row.get("recommended_confidence", "")
        if recommended and recommended != "Needs review" and confidence not in {"", "review", "low"}:
            return recommended
        return ""

    def _write_candidate_color(self, row, grouping):
        target = (row.get("target_color") or "").strip()
        if target:
            return target
        return config.category_to_color(grouping) if grouping else ""

    def _row_has_pending_tag_write(self, row):
        grouping = self._write_candidate_grouping(row)
        if not grouping:
            return False
        target_category = config.normalize_value_to_category(grouping)
        if target_category == "Needs review":
            return False
        current_category = row.get("id3_grouping_normalized", "")
        if current_category != target_category:
            return True
        color = self._write_candidate_color(row, grouping)
        return bool(color and row.get("id3_color", "") != color)

    def _rebuild_pending_tag_paths(self, rows=None):
        rows = self.rows if rows is None else rows
        self.pending_tag_paths = {
            row.get("file_path", "")
            for row in rows
            if row.get("file_path") and self._row_has_pending_tag_write(row)
        }
        self._update_pending_title()

    def _update_pending_path(self, row):
        file_path = row.get("file_path", "")
        if not file_path:
            return
        if self._row_has_pending_tag_write(row):
            self.pending_tag_paths.add(file_path)
        else:
            self.pending_tag_paths.discard(file_path)
        self._update_pending_title()

    def _pending_tag_rows(self):
        return [
            row
            for row in self.rows
            if row.get("file_path", "") in self.pending_tag_paths and self._row_has_pending_tag_write(row)
        ]

    def _prepared_pending_tag_rows(self):
        prepared = []
        for row in self._pending_tag_rows():
            grouping = self._write_candidate_grouping(row)
            copy = dict(row)
            copy["target_grouping"] = grouping
            copy["target_color"] = self._write_candidate_color(row, grouping)
            prepared.append(copy)
        return prepared

    def _update_pending_title(self):
        count = len(self.pending_tag_paths)
        self.pending_tags_status.set(f"Pending tags: {count}")
        suffix = f" - {count} pending tag{'s' if count != 1 else ''}" if count else ""
        self.title(f"{'* ' if count else ''}{app_paths.APP_NAME}{suffix}")

    def _changed_paths_from_changes(self, changes):
        return {file_path for file_path, _row_changes in changes if file_path}

    def _read_metadata_for_paths(self, paths):
        return {path: id3_tags.read_id3(path) for path in paths if path}

    def write_pending_tags(self, apply_write):
        pending_rows = self._prepared_pending_tag_rows()
        if not pending_rows:
            messagebox.showinfo("No pending tags", "There are no pending tag writes.")
            return
        if apply_write and not messagebox.askyesno("Write pending tags", f"Write Grouping/Color tags for {len(pending_rows)} tracks?"):
            return

        def worker():
            try:
                def phase(message):
                    self.message_queue.put(("phase", message))
                changes, _skipped = gui_services.run_write_rows(
                    pending_rows,
                    self.config_path.get().strip(),
                    "target_grouping",
                    "target_color",
                    apply_write=apply_write,
                    only_when_empty=False,
                    log_callback=lambda msg: self.message_queue.put(("write_log", msg)),
                    progress_callback=lambda payload: self.message_queue.put(("write_progress", payload)),
                    status_callback=phase,
                )
                if apply_write:
                    self.message_queue.put(("metadata_refresh", self._read_metadata_for_paths(self._changed_paths_from_changes(changes))))
                self.message_queue.put(("status", f"{'Wrote' if apply_write else 'Dry-run complete for'} {len(pending_rows)} pending tag rows."))
            except Exception as error:
                app_logging.log_exception("pending write failed", error)
                self.message_queue.put(("error", str(error)))
            finally:
                self.message_queue.put(("done", None))

        self._start_worker(worker)

    def write_selected_tags(self, apply_write):
        row = self._selected_row()
        if not row:
            return
        selected_path = row.get("file_path", "")

        def worker():
            try:
                def phase(message):
                    self.message_queue.put(("phase", message))
                changes, _skipped = gui_services.run_write_rows(
                    [dict(row)],
                    self.config_path.get().strip(),
                    self.grouping_column.get().strip(),
                    self.color_column.get().strip(),
                    apply_write=apply_write,
                    only_when_empty=self.only_when_empty.get(),
                    log_callback=lambda msg: self.message_queue.put(("write_log", msg)),
                    progress_callback=lambda payload: self.message_queue.put(("write_progress", payload)),
                    status_callback=phase,
                )
                if apply_write and selected_path:
                    self.message_queue.put(("metadata_refresh", self._read_metadata_for_paths(self._changed_paths_from_changes(changes))))
                self.message_queue.put(("status", f"{'Wrote' if apply_write else 'Dry-run complete for'} selected track tags."))
            except Exception as error:
                app_logging.log_exception("selected write failed", error)
                self.message_queue.put(("error", str(error)))
            finally:
                self.message_queue.put(("done", None))

        self._start_worker(worker)

    def clear_selected_tags(self, apply_write):
        selected_rows = self._selected_rows()
        if not selected_rows:
            messagebox.showinfo("No tracks", "Select one or more tracks first.")
            return
        if apply_write and not messagebox.askyesno("Clear selected tags", f"Clear Grouping and Color tags for {len(selected_rows)} selected tracks?"):
            return

        rows_to_clear = [dict(row) for row in selected_rows]

        def worker():
            try:
                def phase(message):
                    self.message_queue.put(("phase", message))
                changes, _skipped = gui_services.run_clear_rows(
                    rows_to_clear,
                    self.config_path.get().strip(),
                    apply_write=apply_write,
                    log_callback=lambda msg: self.message_queue.put(("write_log", msg)),
                    progress_callback=lambda payload: self.message_queue.put(("write_progress", payload)),
                    status_callback=phase,
                )
                if apply_write:
                    changed_paths = self._changed_paths_from_changes(changes)
                    self.message_queue.put(("clear_row_targets", changed_paths))
                    self.message_queue.put(("metadata_refresh", self._read_metadata_for_paths(changed_paths)))
                self.message_queue.put(("status", f"{'Cleared' if apply_write else 'Dry-run complete for'} {len(selected_rows)} selected tracks."))
            except Exception as error:
                app_logging.log_exception("clear selected tags failed", error)
                self.message_queue.put(("error", str(error)))
            finally:
                self.message_queue.put(("done", None))

        self._start_worker(worker)

    def _load_pygame(self):
        import warnings

        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import pygame
        return pygame

    def _track_duration(self, file_path):
        try:
            from mutagen.mp3 import MP3

            return float(MP3(file_path).info.length)
        except Exception:
            return 0.0

    def _load_track_into_mixer(self, pygame, file_path):
        if self.playback_buffer_path != file_path or self.playback_buffer is None:
            with open(file_path, "rb") as handle:
                self.playback_buffer = io.BytesIO(handle.read())
            self.playback_buffer_path = file_path
        self.playback_buffer.seek(0)
        try:
            pygame.mixer.music.load(self.playback_buffer, namehint=Path(file_path).suffix.lstrip(".") or "mp3")
            self._append_log(f"Loaded into memory: {Path(file_path).name}.")
        except TypeError:
            pygame.mixer.music.load(self.playback_buffer)
            self._append_log(f"Loaded into memory: {Path(file_path).name}.")
        except Exception as error:
            app_logging.log_exception("memory playback load failed", error)
            self.playback_buffer = None
            self.playback_buffer_path = ""
            pygame.mixer.music.load(file_path)
            self._append_log(f"Memory playback load failed, streaming from file: {Path(file_path).name}.")

    def _format_time(self, seconds):
        seconds = max(0, int(seconds or 0))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def _update_playback_progress(self):
        if not self.playing_file:
            return
        try:
            pygame = self._load_pygame()
            position = self.playback_offset + max(0.0, pygame.mixer.music.get_pos() / 1000.0)
            if self.playback_duration:
                position = min(position, self.playback_duration)
                self.playback_seek.set(position)
            self.playback_time.set(f"{self._format_time(position)} / {self._format_time(self.playback_duration)}")
            if pygame.mixer.music.get_busy():
                self.after(500, self._update_playback_progress)
            elif not self.playback_paused:
                self.playing_file = ""
                self._update_play_pause_buttons()
        except Exception:
            pass

    def _seek_value_from_pointer(self, event):
        width = max(1, event.widget.winfo_width())
        ratio = min(1.0, max(0.0, event.x / width))
        maximum = float(self.playback_duration or event.widget.cget("to") or 0.0)
        return ratio * maximum

    def _preview_seek_from_pointer(self, event):
        target = self._seek_value_from_pointer(event)
        self.playback_seek.set(target)
        self.playback_time.set(f"{self._format_time(target)} / {self._format_time(self.playback_duration)}")
        return "break"

    def _seek_from_pointer(self, event):
        target = self._seek_value_from_pointer(event)
        self.playback_seek.set(target)
        self.playback_time.set(f"{self._format_time(target)} / {self._format_time(self.playback_duration)}")
        if self.playing_file:
            self.seek_playback()
        return "break"

    def play_selected(self):
        row = self._selected_row()
        if not row:
            messagebox.showinfo("No track", "Select a track in the table first.")
            return
        try:
            pygame = self._load_pygame()
            pygame.mixer.init()
            self._load_track_into_mixer(pygame, row["file_path"])
            pygame.mixer.music.play()
            self.playing_file = row["file_path"]
            self.playback_paused = False
            self.playback_duration = self._track_duration(row["file_path"])
            self.playback_offset = 0.0
            self._set_seek_range(self.playback_duration)
            if self.playback_duration:
                self.playback_seek.set(0)
            self.playback_time.set(f"00:00 / {self._format_time(self.playback_duration)}")
            self._update_play_pause_buttons()
            self._update_playback_progress()
            self._append_log(f"Playing {row.get('file_name', '')}.")
        except ModuleNotFoundError:
            self._append_log("pygame is not installed; opening the selected track externally.")
            self.open_selected_external()
        except Exception as error:
            app_logging.log_exception("playback failed", error)
            self._append_log(f"Playback failed: {error}; opening externally.")
            self.open_selected_external()

    def toggle_play_pause(self):
        row = self._selected_row()
        selected_file = row.get("file_path") if row else ""
        try:
            pygame = self._load_pygame()
            if not self.playing_file:
                self.play_selected()
                return
            if selected_file and selected_file != self.playing_file:
                self.play_selected()
                return
            if self.playback_paused:
                pygame.mixer.music.unpause()
                self.playback_paused = False
                self._update_play_pause_buttons()
                self._update_playback_progress()
            else:
                pygame.mixer.music.pause()
                self.playback_paused = True
                self._update_play_pause_buttons()
        except Exception:
            pass

    def pause_playback(self):
        self.toggle_play_pause()

    def stop_playback(self):
        try:
            pygame = self._load_pygame()
            pygame.mixer.music.stop()
            self.playing_file = ""
            self.playback_paused = False
            self.playback_offset = 0.0
            self.playback_seek.set(0)
            self.playback_time.set(f"00:00 / {self._format_time(self.playback_duration)}")
            self._update_play_pause_buttons()
        except Exception:
            pass

    def seek_playback(self, _event=None):
        if not self.playing_file:
            return
        try:
            pygame = self._load_pygame()
            self.playback_offset = float(self.playback_seek.get())
            pygame.mixer.music.play(start=self.playback_offset)
            self.playback_paused = False
            self._update_play_pause_buttons()
            self._update_playback_progress()
        except Exception:
            pass

    def open_selected_external(self):
        row = self._selected_row()
        if row and row.get("file_path"):
            os.startfile(row["file_path"])
        else:
            messagebox.showinfo("No track", "Select a track in the table first.")

    def _insert_or_update_row(self, row, status=None):
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
        return (
            row.get("file_name", ""), row.get("id3_grouping_normalized", ""), row.get("id3_color", ""),
            row.get("tag_suggested_grouping", ""), row.get("model_audio_suggested_grouping", ""),
            row.get("learned_suggested_grouping", ""), row.get("recommended_grouping", ""),
            row.get("target_grouping", ""), row.get("target_color", ""),
            row.get("recommended_source", ""), row.get("recommended_confidence", ""), row.get("model_audio_bpm", ""),
        )

    def _row_display_tag(self, row, status=None):
        tag = status or row.get("_gui_status", "queued")
        if row.get("_analysis_skipped_existing_grouping"):
            tag = "done"
        elif tag not in {"queued", "current"} and row.get("recommended_grouping") == "Needs review":
            tag = "needs_review"
        row["_gui_status"] = tag
        return tag

    def _row_matches_table_filter(self, row):
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
        self._refresh_filtered_rows(keep_start=False)
        self._render_virtual_table()

    def toggle_table_sort(self, column):
        self.sort_column, self.sort_direction = virtual_table.next_sort_state(
            self.sort_column,
            self.sort_direction,
            column,
        )
        self._update_sort_headings()
        self._refresh_filtered_rows(keep_start=False)
        self._render_virtual_table()

    def _reset_table_sort(self):
        self.sort_column = ""
        self.sort_direction = "none"
        self._update_sort_headings()

    def _update_sort_headings(self):
        if not getattr(self, "tree", None):
            return
        for column, label in self.column_headings.items():
            suffix = ""
            if column == self.sort_column:
                suffix = " ↑" if self.sort_direction == "asc" else (" ↓" if self.sort_direction == "desc" else "")
            self.tree.heading(column, text=f"{label}{suffix}", command=lambda selected=column: self.toggle_table_sort(selected))

    def _refresh_filtered_rows(self, keep_start=True):
        indexes = virtual_table.matching_indexes(self.rows, self._row_matches_table_filter)
        self.filtered_row_indexes = virtual_table.sorted_indexes(
            self.rows,
            indexes,
            self.sort_column,
            self.sort_direction,
            numeric_columns={"model_audio_bpm"},
        )
        if not keep_start:
            self.virtual_table_start = 0
        self.virtual_table_start = virtual_table.clamp_start(
            self.virtual_table_start,
            len(self.filtered_row_indexes),
            self.virtual_table_window,
        )

    def _render_virtual_table(self, start=None, preserve_selection=True):
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
        if not self.virtual_yscroll:
            return
        first, last = virtual_table.scrollbar_fractions(
            self.virtual_table_start,
            len(self.filtered_row_indexes),
            self.virtual_table_window,
        )
        self.virtual_yscroll.set(first, last)

    def _update_table_status(self, end=None):
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
        try:
            return max(1, int(self.tree["height"]))
        except Exception:
            return 8

    def _set_virtual_table_start(self, start):
        self._render_virtual_table(start=start)
        return "break"

    def _scroll_virtual_table(self, delta):
        self._render_virtual_table(start=self.virtual_table_start + int(delta))
        return "break"

    def _on_virtual_mousewheel(self, event):
        step = -1 if event.delta > 0 else 1
        units = max(1, abs(event.delta) // 120) * 3
        return self._scroll_virtual_table(step * units)

    def _virtual_yview(self, *args):
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
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.row_by_path = {}
        if update_status:
            self._update_pending_title()

    def _clear_table_state(self):
        self.pending_tag_paths = set()
        self.filtered_row_indexes = []
        self.virtual_table_start = 0
        self._reset_table()
        self._update_virtual_scrollbar()
        self._update_table_status()

    def _poll_queue(self):
        processed_messages = 0
        deadline = time.monotonic() + 0.035
        try:
            while processed_messages < 120 and time.monotonic() < deadline:
                kind, payload = self.message_queue.get_nowait()
                processed_messages += 1
                if kind == "rows_loaded":
                    self._rebuild_pending_tag_paths(payload)
                    self._reset_table_sort()
                    self.progress.stop()
                    self.progress.configure(mode="determinate", maximum=max(1, len(payload)), value=0)
                    for row in payload:
                        self._row_display_tag(row, "queued")
                    self._refresh_filtered_rows(keep_start=False)
                    self._render_virtual_table(preserve_selection=False)
                    self._append_log(f"Loaded {len(payload)} rows.")
                elif kind == "rows_refresh":
                    self._rebuild_pending_tag_paths(payload)
                    self._refresh_filtered_rows(keep_start=True)
                    self._render_virtual_table()
                elif kind == "rows_analyzed":
                    self._rebuild_pending_tag_paths(payload)
                    for row in payload:
                        status = self._completed_status_for_row(row)
                        self._row_display_tag(row, status)
                    self._refresh_filtered_rows(keep_start=True)
                    self._render_virtual_table()
                elif kind == "metadata_refresh":
                    metadata_by_path = payload or {}
                    refreshed = 0
                    for row in self.rows:
                        file_path = row.get("file_path", "")
                        if file_path not in metadata_by_path:
                            continue
                        row.update(metadata_by_path[file_path])
                        self._update_pending_path(row)
                        if file_path in self.row_by_path:
                            self._insert_or_update_row(row)
                        refreshed += 1
                    self._refresh_filtered_rows(keep_start=True)
                    self._render_virtual_table()
                    self._append_log(f"Refreshed current tags for {refreshed} changed rows.")
                elif kind == "clear_row_targets":
                    cleared_paths = set(payload or [])
                    for row in self.rows:
                        if row.get("file_path", "") not in cleared_paths:
                            continue
                        for key in ("manual_grouping", "manual_color", "target_grouping", "target_color"):
                            row[key] = ""
                        row["_suppress_pending_recommendation"] = True
                        self._update_pending_path(row)
                        if row.get("file_path", "") in self.row_by_path:
                            self._insert_or_update_row(row)
                    self._refresh_filtered_rows(keep_start=True)
                    self._render_virtual_table()
                elif kind == "phase":
                    self.progress.stop()
                    self.progress.configure(mode="determinate")
                    self.status_label.configure(text=payload)
                    self._append_log(payload)
                elif kind == "load_progress":
                    total = max(1, int(payload.get("total") or 1))
                    processed = int(payload.get("processed") or 0)
                    self.progress.stop()
                    self.progress.configure(mode="determinate", maximum=total, value=min(processed, total))
                    message = payload.get("message", str(payload))
                    self.status_label.configure(text=message)
                    if payload.get("event") == "load_start":
                        self._append_log(message)
                elif kind == "write_progress":
                    total = max(1, int(payload.get("total") or 1))
                    processed = int(payload.get("processed") or 0)
                    self.progress.stop()
                    self.progress.configure(mode="determinate", maximum=total, value=min(processed, total))
                    message = payload.get("message", str(payload))
                    self.status_label.configure(text=message)
                elif kind == "playlist_match_progress":
                    total = max(1, int(payload.get("total") or 1))
                    processed = int(payload.get("processed") or 0)
                    self.progress.stop()
                    self.progress.configure(mode="determinate", maximum=total, value=min(processed, total))
                    message = payload.get("message", str(payload))
                    self.status_label.configure(text=message)
                elif kind == "model_progress":
                    if payload["event"] == "model_cached_rows":
                        gui_services.refresh_recommendations(self.rows, self.mode.get(), self.recommendation_priority.get())
                        for row in payload.get("rows", []):
                            status = self._completed_status_for_row(row)
                            row["_gui_status"] = status
                            self._insert_or_update_row(row, status=status)
                        self.status_label.configure(text=payload["message"])
                        self._append_log(payload["message"])
                    elif payload["event"] == "model_loading":
                        self.progress.stop()
                        self.progress.configure(mode="determinate", maximum=max(1, payload["pending"]), value=0)
                        self.status_label.configure(text=f"{payload['message']} | Processed 0/{payload['pending']}")
                        self._append_log(payload["message"])
                    elif payload["event"] == "model_file_start":
                        self.progress.stop()
                        self.progress.configure(mode="determinate", maximum=max(1, payload["pending"]), value=payload["processed"])
                        self._mark_current(payload["row"])
                        self.status_label.configure(text=f"Analyzing {payload['processed'] + 1}/{payload['pending']} | {payload['row'].get('file_name', '')}")
                        self._append_log(payload["message"])
                    elif payload["event"] == "model_file_done":
                        self.progress.stop()
                        self.progress.configure(mode="determinate", maximum=max(1, payload["pending"]), value=payload["processed"])
                        gui_services.refresh_recommendations(self.rows, self.mode.get(), self.recommendation_priority.get())
                        status = self._completed_status_for_row(payload["row"])
                        payload["row"]["_gui_status"] = status
                        self._insert_or_update_row(payload["row"], status=status)
                        self.status_label.configure(text=f"Processed {payload['processed']}/{payload['pending']} | {payload['row'].get('file_name', '')} | ETA {core.format_duration(payload['eta_seconds'])}")
                        self._append_log(payload["message"])
                    else:
                        self.progress.stop()
                        total = max(1, int(payload.get("total") or payload.get("pending") or 1))
                        processed = int(payload.get("processed") or total)
                        self.progress.configure(mode="determinate", maximum=total, value=min(processed, total))
                        message = payload.get("message", str(payload))
                        self.status_label.configure(text=message)
                        self._append_log(message)
                elif kind == "learned_progress":
                    if payload["event"] == "learned_file_start":
                        self.progress.stop()
                        self.progress.configure(mode="determinate", maximum=max(1, payload["pending"]), value=payload["processed"])
                        self._mark_current(payload["row"])
                        self.status_label.configure(text=f"Learned {payload['processed'] + 1}/{payload['pending']} | {payload['row'].get('file_name', '')}")
                    else:
                        self.progress.stop()
                        self.progress.configure(mode="determinate", maximum=max(1, payload["pending"]), value=payload["processed"])
                        gui_services.refresh_recommendations(self.rows, self.mode.get(), self.recommendation_priority.get())
                        status = self._completed_status_for_row(payload["row"])
                        payload["row"]["_gui_status"] = status
                        self._insert_or_update_row(payload["row"], status=status)
                        self.status_label.configure(text=f"Learned {payload['processed']}/{payload['pending']} | {payload['row'].get('file_name', '')}")
                    self._append_log(payload["message"])
                elif kind == "training_progress":
                    total = max(1, int(payload.get("total") or 1))
                    processed = int(payload.get("processed") or 0)
                    self.progress.stop()
                    self.progress.configure(mode="determinate", maximum=total, value=min(processed, total))
                    row = payload.get("row")
                    if row:
                        if payload.get("status") == "current":
                            self._mark_current(row, payload.get("after_status"))
                        else:
                            status = payload.get("status") or "done"
                            row["_gui_status"] = status
                            row.pop("_previous_gui_status", None)
                            self._insert_or_update_row(row, status=status)
                    message = payload.get("message", str(payload))
                    if payload.get("event") == "training_batch_done":
                        eta = core.format_duration(payload.get("eta_seconds", 0))
                        message = f"{message} | ETA {eta}"
                    self.status_label.configure(text=message)
                    self._append_log(message)
                elif kind == "comparison_result":
                    comparison_rows, fieldnames = payload
                    self.show_model_comparison_window(comparison_rows, fieldnames)
                elif kind == "playlist_match_result":
                    match_rows, summary = payload
                    updated_paths = set(summary.get("updated_paths", []))
                    for row in self.rows:
                        if row.get("file_path", "") not in updated_paths:
                            continue
                        row["_gui_status"] = "done"
                        self._update_pending_path(row)
                        if row.get("file_path", "") in self.row_by_path:
                            self._insert_or_update_row(row, status="done")
                    self._refresh_filtered_rows(keep_start=True)
                    self._render_virtual_table()
                    self._append_log(
                        f"Playlist match CSV saved: {summary.get('output_csv', '')}. "
                        f"Prepared {summary.get('updated', 0)} pending tag row(s)."
                    )
                    self.show_playlist_match_window(match_rows, summary)
                elif kind == "status":
                    self.progress.stop()
                    self.progress.configure(mode="determinate")
                    self.status_label.configure(text=payload)
                    self._append_log(payload)
                elif kind == "write_log":
                    self._append_log(payload, write=True)
                elif kind == "error":
                    self.status_label.configure(text=f"Error: {payload}")
                    self._append_log(f"ERROR: {payload}")
                    messagebox.showerror("Error", payload)
                elif kind == "done":
                    self._set_busy(False)
        except queue.Empty:
            pass
        self.after(15 if processed_messages else 150, self._poll_queue)


if __name__ == "__main__":
    MusicCategoryGui().mainloop()
