from __future__ import annotations

import queue
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .builder import (
    DiskBuildError,
    ProgressEvent,
    build_disk,
    find_source_tracks,
    natural_sort_key,
)


class DiskBuilderGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title("Music Disk Builder")
        self.geometry("540x740")
        self.minsize(540, 740)
        self.maxsize(540, 740)

        self.event_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.building = False

        # Track order matches the order written to the disk.
        self.tracks: list[Path] = []
        self.drag_item: str | None = None

        self.phase_var = tk.StringVar()
        self.source_var = tk.StringVar()
        self.artist_var = tk.StringVar()
        self.comment_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready.")
        self.system_status_var = tk.StringVar(value="● SYSTEM READY")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.track_count_var = tk.StringVar(value="0 tracks")

        self._configure_styles()
        self._build_ui()

        self.after(100, self._process_events)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")

        bg = "#080d16"
        panel = "#111a27"
        panel_alt = "#172334"
        border = "#30465c"
        text = "#dcecff"
        muted = "#71869c"
        cyan = "#56d9ff"
        cyan_bright = "#8cecff"
        cyan_dark = "#269bc0"
        selected = "#163d55"

        self.configure(bg=bg)

        style.configure("TFrame", background=bg)

        style.configure(
            "Panel.TFrame",
            background=panel,
            borderwidth=1,
            relief="solid",
        )

        style.configure(
            "TLabel",
            background=bg,
            foreground=text,
            font=("TkDefaultFont", 10),
        )

        style.configure(
            "Muted.TLabel",
            background=bg,
            foreground=muted,
            font=("TkDefaultFont", 9),
        )

        style.configure(
            "Title.TLabel",
            background=bg,
            foreground="#e8f6ff",
            font=("TkDefaultFont", 14, "bold"),
        )

        style.configure(
            "System.TLabel",
            background=bg,
            foreground=cyan,
            font=("TkFixedFont", 8),
        )

        style.configure(
            "Status.TLabel",
            background=bg,
            foreground="#8daabd",
            font=("TkDefaultFont", 9),
        )

        style.configure(
            "TEntry",
            fieldbackground=panel_alt,
            background=panel_alt,
            foreground=text,
            insertcolor=cyan_bright,
            bordercolor=border,
            lightcolor=border,
            darkcolor=border,
            padding=4,
        )

        style.map(
            "TEntry",
            bordercolor=[("focus", cyan)],
            lightcolor=[("focus", cyan)],
            darkcolor=[("focus", cyan_dark)],
        )

        style.configure(
            "TButton",
            background=panel_alt,
            foreground=text,
            bordercolor=border,
            padding=(12, 6),
            font=("TkDefaultFont", 9),
        )

        style.map(
            "TButton",
            background=[
                ("active", "#203449"),
                ("pressed", "#152536"),
            ],
            foreground=[
                ("disabled", "#4d6073"),
                ("active", cyan_bright),
            ],
            bordercolor=[("active", cyan)],
        )

        style.configure(
            "Accent.TButton",
            background="#122638",
            foreground=cyan_bright,
            bordercolor=cyan,
            padding=(12, 6),
            font=("TkDefaultFont", 10, "bold"),
        )

        style.map(
            "Accent.TButton",
            background=[
                ("active", "#1b4055"),
                ("pressed", "#0d1d2b"),
            ],
            foreground=[("active", "#ffffff")],
            bordercolor=[("active", cyan_bright)],
        )

        style.configure(
            "Treeview",
            background=panel,
            fieldbackground=panel,
            foreground=text,
            bordercolor=border,
            borderwidth=0,
            rowheight=16,
            font=("TkDefaultFont", 10),
        )

        style.configure(
            "Treeview.Heading",
            background=panel_alt,
            foreground="#7898b2",
            bordercolor=border,
            borderwidth=0,
            font=("TkDefaultFont", 9, "bold"),
            padding=(8, 8),
        )

        style.map(
            "Treeview",
            background=[("selected", selected)],
            foreground=[("selected", "#ffffff")],
        )

        style.configure(
            "Vertical.TScrollbar",
            background="#1b2d3f",
            troughcolor="#0b121c",
            bordercolor="#0b121c",
            arrowcolor="#607f98",
            relief="flat",
            borderwidth=0,
            arrowsize=8,
        )

        style.map(
            "Vertical.TScrollbar",
            background=[("active", cyan_dark)],
            arrowcolor=[("active", cyan_bright)],
        )

        style.configure(
            "Horizontal.TProgressbar",
            background=cyan,
            troughcolor="#0b141f",
            bordercolor="#0b141f",
            lightcolor=cyan_bright,
            darkcolor=cyan_dark,
            thickness=8,
        )

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=4)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x", pady=(0, 5))

        ttk.Label(
            header,
            text="Music Disk Builder",
            style="Title.TLabel",
        ).pack(side="left", anchor="w")

        ttk.Label(
            header,
            textvariable=self.system_status_var,
            style="System.TLabel",
        ).pack(side="right", anchor="e")

        tk.Frame(
            root,
            height=1,
            background="#24384b",
        ).pack(fill="x", pady=(0, 7))

        settings_panel = ttk.Frame(root, style="Panel.TFrame")
        settings_panel.pack(fill="x", pady=(0, 4), padx=1)

        settings_row = ttk.Frame(
            settings_panel,
            style="Panel.TFrame",
        )
        settings_row.pack(fill="x", padx=4, pady=(4, 2))

        ttk.Label(
            settings_row,
            text="PHASE:",
            foreground="#71869c",
        ).pack(side="left", padx=(0, 8))

        self.phase_entry = ttk.Entry(
            settings_row,
            textvariable=self.phase_var,
            width=10,
        )
        self.phase_entry.pack(side="left", padx=(0, 16))

        ttk.Label(
            settings_row,
            text="SRC:",
            foreground="#71869c",
        ).pack(side="left", padx=(0, 8))

        self.source_entry = ttk.Entry(
            settings_row,
            textvariable=self.source_var,
        )
        self.source_entry.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 8),
        )

        self.browse_button = ttk.Button(
            settings_row,
            text="Browse...",
            command=self._browse_source,
        )
        self.browse_button.pack(side="right")

        artist_comment_row = ttk.Frame(
            settings_panel,
            style="Panel.TFrame",
        )
        artist_comment_row.pack(fill="x", padx=4, pady=(2, 4))

        ttk.Label(
            artist_comment_row,
            text="ARTIST:",
            foreground="#71869c",
        ).pack(side="left", padx=(0, 8))

        self.artist_entry = ttk.Entry(
            artist_comment_row,
            textvariable=self.artist_var,
            width=18,
        )
        self.artist_entry.pack(side="left", padx=(0, 16))

        ttk.Label(
            artist_comment_row,
            text="COMMENT:",
            foreground="#71869c",
        ).pack(side="left", padx=(0, 8))

        self.comment_entry = ttk.Entry(
            artist_comment_row,
            textvariable=self.comment_var,
            width=24,
        )
        self.comment_entry.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 8),
        )

        track_header = ttk.Frame(root)
        track_header.pack(fill="x", pady=(4, 4))

        track_title_frame = ttk.Frame(track_header)
        track_title_frame.pack(side="left")

        ttk.Label(
            track_title_frame,
            text="TRACKS",
            foreground="#dcecff",
            font=("TkDefaultFont", 11, "bold"),
        ).pack(side="left")

        ttk.Label(
            track_title_frame,
            text="  Drag to reorder",
            style="Muted.TLabel",
        ).pack(side="left")

        ttk.Label(
            track_header,
            textvariable=self.track_count_var,
            style="Muted.TLabel",
        ).pack(side="right")

        list_frame = ttk.Frame(root, style="Panel.TFrame")
        list_frame.pack(
            fill="both",
            expand=True,
            pady=(0, 8),
        )

        self.track_tree = ttk.Treeview(
            list_frame,
            columns=("number", "filename"),
            show="headings",
            selectmode="browse",
        )

        self.track_tree.heading("number", text="#")
        self.track_tree.heading("filename", text="Filename")

        self.track_tree.column(
            "number",
            width=60,
            minwidth=60,
            anchor="center",
            stretch=False,
        )
        self.track_tree.column(
            "filename",
            width=500,
            minwidth=200,
            anchor="w",
            stretch=True,
        )

        self.track_tree.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(1, 0),
            pady=1,
        )

        scrollbar = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.track_tree.yview,
            style="Vertical.TScrollbar",
        )
        scrollbar.pack(
            side="right",
            fill="y",
            padx=(0, 1),
            pady=1,
        )

        self.track_tree.configure(yscrollcommand=scrollbar.set)

        self.track_tree.bind("<ButtonPress-1>", self._drag_start)
        self.track_tree.bind("<B1-Motion>", self._drag_motion)
        self.track_tree.bind("<ButtonRelease-1>", self._drag_end)
        self.track_tree.bind("<Up>", self._keyboard_move_up)
        self.track_tree.bind("<Down>", self._keyboard_move_down)

        controls = ttk.Frame(root)
        controls.pack(fill="x", pady=(0, 12))

        self.add_button = ttk.Button(
            controls,
            text="Load Source",
            command=self._load_source,
        )
        self.add_button.pack(side="left")

        self.move_up_button = ttk.Button(
            controls,
            text="↑ Move Up",
            command=self._move_selected_up,
        )
        self.move_up_button.pack(side="left", padx=(8, 0))

        self.move_down_button = ttk.Button(
            controls,
            text="↓ Move Down",
            command=self._move_selected_down,
        )
        self.move_down_button.pack(side="left", padx=(8, 0))

        self.remove_button = ttk.Button(
            controls,
            text="Remove",
            command=self._remove_selected,
        )
        self.remove_button.pack(side="left", padx=(8, 0))

        self.reset_button = ttk.Button(
            controls,
            text="Reset Order",
            command=self._reset_order,
        )
        self.reset_button.pack(side="left", padx=(8, 0))

        self.build_button = ttk.Button(
            root,
            text="BUILD DISK",
            command=self._start_build,
            style="Accent.TButton",
        )
        self.build_button.pack(fill="x", pady=(4, 16))

        progress_frame = ttk.Frame(root)
        progress_frame.pack(fill="x", pady=(0, 4))

        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
        )
        self.progress_bar.pack(fill="x", ipady=2)

        ttk.Label(
            root,
            textvariable=self.status_var,
            style="Status.TLabel",
        ).pack(anchor="w", pady=(5, 10))

        ttk.Label(root, text="Log:").pack(anchor="w")

        log_frame = ttk.Frame(root, style="Panel.TFrame")
        log_frame.pack(fill="both", expand=True)

        self.log_text = tk.Text(
            log_frame,
            height=8,
            state="disabled",
            wrap="word",
            background="#080d14",
            foreground="#9fb5c8",
            insertbackground="#8cecff",
            selectbackground="#163d55",
            selectforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            padx=12,
            pady=10,
            font=("TkFixedFont", 9),
        )
        self.log_text.pack(
            side="left",
            fill="both",
            expand=True,
            padx=1,
            pady=1,
        )

        scrollbar = ttk.Scrollbar(
            log_frame,
            orient="vertical",
            command=self.log_text.yview,
            style="Vertical.TScrollbar",
        )
        scrollbar.pack(
            side="right",
            fill="y",
            padx=(0, 1),
            pady=1,
        )

        self.log_text.configure(yscrollcommand=scrollbar.set)

        self.log_text.tag_configure(
            "log_normal",
            foreground="#9fb5c8",
        )
        self.log_text.tag_configure(
            "log_progress",
            foreground="#70cbe8",
        )
        self.log_text.tag_configure(
            "log_complete",
            foreground="#8cecff",
        )
        self.log_text.tag_configure(
            "log_error",
            foreground="#e9a84b",
        )

    def _log(self, message: str) -> None:
        self.log_text.configure(state="normal")

        if "ERROR" in message or "FAILED" in message:
            tag = "log_error"
        elif "COMPLETE" in message:
            tag = "log_complete"
        elif message.startswith("["):
            tag = "log_progress"
        else:
            tag = "log_normal"

        self.log_text.insert("end", message + "\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"

        for widget in (
            self.phase_entry,
            self.artist_entry,
            self.comment_entry,
            self.source_entry,
            self.browse_button,
            self.add_button,
            self.move_up_button,
            self.move_down_button,
            self.remove_button,
            self.reset_button,
            self.build_button,
        ):
            widget.configure(state=state)

    def _update_track_count(self) -> None:
        count = len(self.tracks)
        self.track_count_var.set(
            f"{count} track{'s' if count != 1 else ''}"
        )

    def _browse_source(self) -> None:
        directory = filedialog.askdirectory(
            title="Select source directory",
        )

        if not directory:
            return

        self.source_var.set(directory)
        self._load_source()

    def _load_source(self) -> None:
        source_text = self.source_var.get().strip()

        if not source_text:
            messagebox.showerror(
                "Missing Source",
                "Please select a source directory.",
            )
            return

        source = Path(source_text)

        if not source.exists():
            messagebox.showerror(
                "Invalid Source",
                f"Source directory does not exist:\n\n{source}",
            )
            return

        if not source.is_dir():
            messagebox.showerror(
                "Invalid Source",
                f"Source path is not a directory:\n\n{source}",
            )
            return

        try:
            source_tracks = find_source_tracks(source)
        except DiskBuildError as exc:
            messagebox.showerror("Invalid Source", str(exc))
            return

        self.tracks = [path for _, path in source_tracks]
        self._refresh_track_list()

        count = len(self.tracks)
        self.status_var.set(
            f"Loaded {count} track{'s' if count != 1 else ''}."
        )
        self.system_status_var.set("● SYSTEM READY")

        self._log(
            f"Loaded {count} track{'s' if count != 1 else ''} from {source}"
        )

    def _refresh_track_list(
        self,
        selected_index: int | None = None,
    ) -> None:
        self.track_tree.delete(*self.track_tree.get_children())

        for index, path in enumerate(self.tracks, start=1):
            self.track_tree.insert(
                "",
                "end",
                iid=str(index - 1),
                values=(f"{index:02d}", path.name),
            )

        self._update_track_count()

        if not self.tracks:
            return

        if selected_index is None:
            selected_index = 0

        selected_index = max(
            0,
            min(selected_index, len(self.tracks) - 1),
        )

        item_id = str(selected_index)

        self.track_tree.selection_set(item_id)
        self.track_tree.focus(item_id)
        self.track_tree.see(item_id)

    def _selected_index(self) -> int | None:
        selection = self.track_tree.selection()

        if not selection:
            return None

        try:
            return int(selection[0])
        except ValueError:
            return None

    def _drag_start(self, event: tk.Event) -> None:
        item = self.track_tree.identify_row(event.y)

        if not item:
            self.drag_item = None
            return

        self.drag_item = item
        self.track_tree.selection_set(item)
        self.track_tree.focus(item)

    def _drag_motion(self, event: tk.Event) -> None:
        if self.drag_item is None:
            return

        target = self.track_tree.identify_row(event.y)

        if not target or target == self.drag_item:
            return

        try:
            old_index = int(self.drag_item)
            target_index = int(target)
        except ValueError:
            return

        if not (
            0 <= old_index < len(self.tracks)
            and 0 <= target_index < len(self.tracks)
        ):
            return

        if old_index == target_index:
            return

        track = self.tracks.pop(old_index)

        if old_index < target_index:
            target_index -= 1

        self.tracks.insert(target_index, track)
        self._refresh_track_list(selected_index=target_index)
        self.drag_item = str(target_index)

    def _drag_end(self, event: tk.Event) -> None:
        self.drag_item = None

    def _move_selected_up(self) -> None:
        index = self._selected_index()

        if index is None or index <= 0:
            return

        self.tracks[index - 1], self.tracks[index] = (
            self.tracks[index],
            self.tracks[index - 1],
        )
        self._refresh_track_list(selected_index=index - 1)

    def _move_selected_down(self) -> None:
        index = self._selected_index()

        if index is None or index >= len(self.tracks) - 1:
            return

        self.tracks[index], self.tracks[index + 1] = (
            self.tracks[index + 1],
            self.tracks[index],
        )
        self._refresh_track_list(selected_index=index + 1)

    def _remove_selected(self) -> None:
        index = self._selected_index()

        if index is None:
            return

        path = self.tracks.pop(index)

        selected_index = None
        if self.tracks:
            selected_index = min(index, len(self.tracks) - 1)

        self._refresh_track_list(selected_index=selected_index)
        self.status_var.set(f"Removed {path.name}.")

    def _reset_order(self) -> None:
        if not self.tracks:
            return

        self.tracks.sort(key=natural_sort_key)
        self._refresh_track_list()
        self.status_var.set("Order reset by filename.")

    def _keyboard_move_up(self, event: tk.Event) -> str:
        self._move_selected_up()
        return "break"

    def _keyboard_move_down(self, event: tk.Event) -> str:
        self._move_selected_down()
        return "break"

    def _start_build(self) -> None:
        if self.building:
            return

        phase = self.phase_var.get().strip()
        artist_name = self.artist_var.get().strip()
        comment = self.comment_var.get().strip()

        if not phase:
            messagebox.showerror(
                "Missing Phase",
                "Please enter a phase letter.",
            )
            self.phase_entry.focus_set()
            return

        if not artist_name:
            messagebox.showerror(
                "Missing Artist",
                "Please enter an artist name.",
            )
            self.artist_entry.focus_set()
            return

        if not comment:
            messagebox.showerror(
                "Missing Comment",
                "Please enter a comment.",
            )
            self.comment_entry.focus_set()
            return

        if not self.tracks:
            messagebox.showerror(
                "No Tracks",
                "Please load a source directory containing tracks.",
            )
            return

        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

        self.progress_var.set(0)
        self.status_var.set("Starting build...")
        self.system_status_var.set("● BUILDING")
        self.building = True
        self._set_controls_enabled(False)

        self._log("=== Music Disk Builder ===")
        self._log("")
        self._log(f"Phase:  {phase}")
        self._log(f"Tracks: {len(self.tracks)}")
        self._log("")
        self._log("Track order:")

        for index, path in enumerate(self.tracks, start=1):
            self._log(f"  {index:02d}. {path.name}")

        self._log("")

        ordered_tracks = [
            (index, path)
            for index, path in enumerate(self.tracks, start=1)
        ]

        thread = threading.Thread(
            target=self._build_worker,
            args=(phase, artist_name, comment, ordered_tracks),
            daemon=True,
        )
        thread.start()

    def _build_worker(
        self,
        phase: str,
        artist_name: str,
        comment: str,
        source_tracks: list[tuple[int, Path]],
    ) -> None:
        try:
            build_disk(
                phase,
                source_tracks,
                artist_name=artist_name,
                comment=comment,
                progress_callback=self._progress_callback,
            )
            self.event_queue.put(("complete", None))

        except DiskBuildError as exc:
            self.event_queue.put(("error", str(exc)))

        except Exception as exc:
            self.event_queue.put(
                (
                    "unexpected_error",
                    (str(exc), traceback.format_exc()),
                )
            )

    # Called from the worker thread; Tkinter updates stay on the main thread.
    def _progress_callback(self, event: ProgressEvent) -> None:
        self.event_queue.put(("progress", event))

    def _process_events(self) -> None:
        try:
            while True:
                event_type, payload = self.event_queue.get_nowait()

                if event_type == "progress":
                    self._handle_progress(payload)  # type: ignore[arg-type]

                elif event_type == "complete":
                    self._handle_complete()

                elif event_type == "error":
                    self._handle_error(str(payload))

                elif event_type == "unexpected_error":
                    message, details = payload  # type: ignore[misc]
                    self._handle_unexpected_error(
                        str(message),
                        str(details),
                    )

        except queue.Empty:
            pass

        self.after(100, self._process_events)

    def _handle_progress(self, event: ProgressEvent) -> None:
        percent = event.fraction * 100

        self.progress_var.set(percent)
        self.status_var.set(
            f"{percent:.1f}% — {event.message}"
        )

        if event.current is None:
            self._log(
                f"[{percent:6.2f}%] {event.message}"
            )

    def _handle_complete(self) -> None:
        self.building = False
        self._set_controls_enabled(True)

        self.progress_var.set(100)
        self.status_var.set("Build complete.")
        self.system_status_var.set("● COMPLETE")

        self._log("")
        self._log("=== COMPLETE ===")

        messagebox.showinfo(
            "Build Complete",
            "The disk was built successfully.",
        )

    def _handle_error(self, message: str) -> None:
        self.building = False
        self._set_controls_enabled(True)

        self.status_var.set("Build failed.")
        self.system_status_var.set("● ERROR")

        self._log("")
        self._log(f"ERROR: {message}")

        messagebox.showerror(
            "Build Failed",
            message,
        )

    def _handle_unexpected_error(
        self,
        message: str,
        details: str,
    ) -> None:
        self.building = False
        self._set_controls_enabled(True)

        self.status_var.set("Unexpected error.")
        self.system_status_var.set("● ERROR")

        self._log("")
        self._log(f"UNEXPECTED ERROR: {message}")
        self._log("")
        self._log(details)

        messagebox.showerror(
            "Unexpected Error",
            message,
        )


def main() -> None:
    app = DiskBuilderGUI()
    app.mainloop()


if __name__ == "__main__":
    main()