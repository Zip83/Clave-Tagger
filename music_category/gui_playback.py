"""Playback controls and pygame integration for the Tkinter GUI."""

import io
import os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from . import app_logging


class GuiPlaybackMixin:
    """In-app playback, seek, and external-player fallback."""

    def _playback_button(self, parent, text, command):
        """Create a small playback control button with the correct tooltip."""
        tips = {
            "play_selected": "Play the selected track.",
            "toggle_play_pause": "Play, pause, or resume the selected track.",
            "pause_playback": "Pause or resume playback.",
            "stop_playback": "Stop playback.",
            "open_selected_external": "Open the selected track in the system player.",
        }
        button = self._button(parent, text, command, tips.get(getattr(command, "__name__", ""), "Playback control."), width=6)
        self.playback_buttons.append(button)
        return button

    def _play_pause_button(self, parent):
        """Create a play/pause toggle and track it for icon refreshes."""
        button = self._playback_button(parent, "Play", self.toggle_play_pause)
        self.play_pause_buttons.append(button)
        return button

    def _update_play_pause_buttons(self):
        """Refresh every play/pause button to match the current playback state."""
        text = "Play" if self.playback_paused or not self.playing_file else "Pause"
        for button in self.play_pause_buttons:
            try:
                button.configure(text=text)
            except tk.TclError:
                pass

    def _bind_seek_control(self, scale):
        """Attach click-and-drag seek behavior to a Tk scale widget."""
        self.seek_controls.append(scale)
        scale.bind("<Button-1>", self._seek_from_pointer)
        scale.bind("<B1-Motion>", self._preview_seek_from_pointer)
        scale.bind("<ButtonRelease-1>", self._seek_from_pointer)

    def _set_seek_range(self, duration):
        """Update all seek controls to the selected track duration."""
        maximum = max(float(duration or 0.0), 1.0)
        for scale in self.seek_controls:
            try:
                scale.configure(to=maximum)
            except tk.TclError:
                pass

    def _load_pygame(self):
        """Import pygame quietly so the GUI can fall back when it is missing."""
        import warnings

        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import pygame
        return pygame

    def _track_duration(self, file_path):
        """Read an MP3 duration for the selected track when mutagen can parse it."""
        try:
            from mutagen.mp3 import MP3

            return float(MP3(file_path).info.length)
        except Exception:
            return 0.0

    def _load_track_into_mixer(self, pygame, file_path):
        """Load the selected track into pygame, preferring an in-memory buffer."""
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
        """Format a playback position as mm:ss for labels."""
        seconds = max(0, int(seconds or 0))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def _update_playback_progress(self):
        """Poll pygame playback position and update seek/time widgets."""
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
        """Translate a mouse x-position on the seek scale into seconds."""
        width = max(1, event.widget.winfo_width())
        ratio = min(1.0, max(0.0, event.x / width))
        maximum = float(self.playback_duration or event.widget.cget("to") or 0.0)
        return ratio * maximum

    def _preview_seek_from_pointer(self, event):
        """Preview the target playback position while dragging the seek scale."""
        target = self._seek_value_from_pointer(event)
        self.playback_seek.set(target)
        self.playback_time.set(f"{self._format_time(target)} / {self._format_time(self.playback_duration)}")
        return "break"

    def _seek_from_pointer(self, event):
        """Seek to the clicked position and resume playback if a track is active."""
        target = self._seek_value_from_pointer(event)
        self.playback_seek.set(target)
        self.playback_time.set(f"{self._format_time(target)} / {self._format_time(self.playback_duration)}")
        if self.playing_file:
            self.seek_playback()
        return "break"

    def play_selected(self):
        """Start playback for the selected table row or fall back externally."""
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
        """Toggle playback for the current or newly selected track."""
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
        """Compatibility alias for the play/pause toggle."""
        self.toggle_play_pause()

    def stop_playback(self):
        """Stop active playback and reset the visible seek position."""
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
        """Restart pygame playback from the current seek control value."""
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
        """Open the selected file in the operating system's default player."""
        row = self._selected_row()
        if row and row.get("file_path"):
            os.startfile(row["file_path"])
        else:
            messagebox.showinfo("No track", "Select a track in the table first.")
