"""
Tkinter front-end for the STEP builder.

Deliberately thin: everything it does goes through stepbuilder.core, so new
actions can be added without touching the geometry code. To add a button, drop
one line into _build_actions() and write the handler; _run_in_worker() takes
care of threading, logging and re-enabling the UI.

Prefill from Allegro: launch with the paths already filled by passing them on
the command line, or by setting them via the config file the SKILL side writes.
"""

from __future__ import annotations

import json
import os
import queue
import re
import threading
import tkinter as tk
import traceback
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import core
from .core import DEFAULT_FLAT_HEIGHT
from .colors import (
    BOARD_THEMES,
    CREAM_DIELECTRIC,
    DEFAULT_LAYER_COLORS,
    DEFAULT_SILK,
    DEFAULT_THEME,
    LAYER_KINDS,
    SILK_COLORS,
    SILK_ORDER,
    THEME_ORDER,
    parse_hex,
    resolve_board_color,
)

# Every user-facing setting lives in ONE file, simple3d_config.json, shared with
# the SKILL side - which is why it sits next to the package rather than in the
# home directory. The launcher passes its path with --config; run standalone,
# the package's own folder is the documented install layout.
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "simple3d_config.json"

# How the board body is built. One dropdown rather than a pile of checkboxes:
# the three are alternatives, and "inspect + layer colours" ticked together
# would have to mean something, which it does not.
BOARD_MODES = [
    ("solid",   "Solid (one colour)"),
    ("layers",  "Layer colours"),
    ("inspect", "Inspect layers (separate parts)"),
]


def _mode_label(key: str) -> str:
    return dict(BOARD_MODES).get(key, BOARD_MODES[0][1])


def _mode_key(label: str) -> str:
    return next((k for k, l in BOARD_MODES if l == label), BOARD_MODES[0][0])


RIM_SAME = "Same as board"
RIM_CREAM = "Cream (dielectric)"
RIM_CUSTOM = "Custom..."

# Log lines arrive from core as plain text, so severity is inferred from how the
# line opens. core labels its own non-fatal lines with a "warning:" prefix, which
# is what colours them here AND marks them in the CLI's plain-text output - so
# prefer adding the prefix at the log() call over adding a pattern below.
# Match lowercase: _append_log lowercases before testing.
ERROR_PREFIXES = ("error", "traceback")
WARNING_PREFIXES = ("warning", "ignored", "ignoring")


@dataclass(frozen=True)
class BuildSettings:
    """Everything a build needs, snapshotted off the widgets on the main thread.

    Tk variables belong to the thread running mainloop: reading a StringVar from
    the worker enters the Tcl interpreter from a second thread, which raises
    "main thread is not in main loop" on a non-threaded Tcl and is a data race
    on a threaded one. So the worker never touches self.<var>.get() - it gets
    one of these, taken in on_generate() before the thread starts. Frozen so a
    later widget edit cannot change the build already in flight.
    """

    step_dirs: tuple[str, ...]
    json_file: str
    output_dir: str
    z_datum: str
    board_color: tuple[int, int, int] | None
    rim_color: tuple[int, int, int] | None
    silk_top: bool
    silk_bottom: bool
    silk_color: tuple[int, int, int] | None
    silk_flat: bool
    silk_flat_height: float
    silk_layers_off: frozenset[str]
    minimize: bool
    board_mode: str
    layer_colors: dict
    ignore_soldermask: bool
    brd_name: str | None
    dated_name: bool


class StepBuilderApp(tk.Tk):
    def __init__(self, config_path: Path | None = None) -> None:
        super().__init__()
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self.title("Simple 3D - StepBuilder")
        self.minsize(760, 560)

        self._queue: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None

        # The STEP folders are a Text widget, not a StringVar, and _load_config
        # runs BEFORE _build_ui - so reads and writes buffer here until the
        # widget exists. Without this, loading the config would touch a widget
        # that has not been created yet.
        self._step_text: tk.Text | None = None
        self._pending_step_dirs: list[str] = []
        self.json_file = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.status = tk.StringVar(value="Ready")

        self.z_datum = tk.StringVar(value="top")
        self.theme = tk.StringVar(value=DEFAULT_THEME)
        self.rim_choice = tk.StringVar(value=RIM_SAME)
        self.rim_custom = tk.StringVar(value="")
        self.silk_top = tk.BooleanVar(value=True)
        self.silk_bottom = tk.BooleanVar(value=True)
        self.silk_color = tk.StringVar(value=DEFAULT_SILK)
        self.silk_flat = tk.BooleanVar(value=False)
        # Config-only, no widget: a display fudge you set once when a viewer
        # flickers, not something to press on every build. Plain float, not a
        # Tk variable, so the worker may read it straight off the snapshot.
        self.silk_flat_height = DEFAULT_FLAT_HEIGHT
        # MFRPN DISABLED (property attachment unreliable); kept for future:
        # self.mfr_pn_in_name = tk.BooleanVar(value=False)
        self.minimize = tk.BooleanVar(value=True)
        self.board_mode = tk.StringVar(value=BOARD_MODES[0][1])
        self.layer_colors: dict[str, tuple[int, int, int]] = dict(DEFAULT_LAYER_COLORS)
        self.ignore_soldermask = tk.BooleanVar(value=False)

        # Prefill state, set by prefill_jobs() when launched from Allegro.
        # Note: there is deliberately NO cached job list - jobs are resolved
        # from the JSON field at Generate time (see _generate).
        self._brd_name: str | None = None      # base name for dated output
        self._dated_name: bool = False
        self._config_problem: str | None = None
        self._paths_from_launcher = False
        # Layers switched OFF, by name. Exclusions rather than inclusions: a
        # layer this build has never seen must default to ON, or a layer that
        # appears on a new board would silently go missing.
        self._layers_off: set[str] = set()
        self._layer_vars: dict[str, tk.BooleanVar] = {}
        # Which side each checkbox belongs to, so switching a side off can grey
        # its layers out WITHOUT changing them - the ticks are still what gets
        # saved and what applies again when the side comes back.
        self._layer_rows: dict[str, list] = {"top": [], "bottom": []}
        self._layer_refresh_job = None
        self._drain_job = None

        # Window placement, remembered across runs. Filled by _load_config
        # (which runs before the widgets exist) and applied by
        # _restore_geometry once they do.
        self._saved_geometry: str | None = None
        self._saved_state: str = "normal"
        # The geometry to save is the NON-maximized one: self.geometry() on a
        # maximized window reports the maximized rect, and restoring that as a
        # normal window would come back full-screen-sized but not maximized.
        self._last_normal_geometry: str | None = None

        self._load_config()
        self._build_ui()
        self._restore_geometry()
        self.bind("<Configure>", self._remember_geometry)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._drain_job = self.after(100, self._drain_queue)
        # Say which settings file was used, always. When a path field comes up
        # unexpectedly empty, the first question is which file was read and
        # whether it parsed, and the answer used to be nowhere on screen.
        if self._config_problem:
            self.after(150, lambda: self._append_log(
                f"warning: {self._config_problem}. "
                f"Settings were not loaded, and will NOT be saved - the file is "
                f"left untouched. Restore simple3d_config.json from the "
                f"installation to fix this."))
        else:
            self.after(150, lambda: self._append_log(
                f"Settings loaded from {self._show_path(self.config_path)}"))

    # ----------------------------------------------------------------- UI -- #

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # --- paths ---
        paths = ttk.LabelFrame(self, text="Input", padding=8)
        paths.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        paths.columnconfigure(1, weight=1)
        self._step_dirs_row(paths, 0)
        self._path_row(paths, 1, "JSON file", self.json_file, self._pick_json_file)
        self._path_row(paths, 2, "Output", self.output_dir, self._pick_output_dir)

        # --- options ---
        opts = ttk.LabelFrame(self, text="Options", padding=8)
        opts.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        opts.columnconfigure(1, weight=1)
        opts.columnconfigure(3, weight=1)

        ttk.Label(opts, text="Board colour").grid(row=0, column=0, sticky="w", pady=3)
        # Keep the combobox and its colour swatch together in one frame so the
        # swatch sits directly beside the dropdown instead of being pushed to the
        # right edge by the expanding grid column.
        colour_row = ttk.Frame(opts)
        colour_row.grid(row=0, column=1, columnspan=2, sticky="w", padx=6)
        theme_box = ttk.Combobox(
            colour_row, textvariable=self.theme, values=THEME_ORDER, state="readonly", width=16
        )
        theme_box.pack(side="left")
        self._swatch = tk.Canvas(colour_row, width=22, height=22, highlightthickness=1,
                                 highlightbackground="#888")
        self._swatch.pack(side="left", padx=(6, 0))
        theme_box.bind("<<ComboboxSelected>>", lambda e: self._update_swatch())

        ttk.Label(opts, text="Board edge colour").grid(row=0, column=3, sticky="e", padx=(12, 6))
        rim_box = ttk.Combobox(
            opts, textvariable=self.rim_choice,
            values=[RIM_SAME, RIM_CREAM, RIM_CUSTOM], state="readonly", width=18
        )
        rim_box.grid(row=0, column=4, sticky="w")
        rim_box.bind("<<ComboboxSelected>>", lambda e: self._update_rim_entry())
        # HEX label sits directly left of the custom-colour field and greys out
        # with it, so it is obvious the field is only live for the Custom choice.
        self.rim_hex_label = ttk.Label(opts, text="HEX colour")
        self.rim_hex_label.grid(row=1, column=3, sticky="e", padx=(12, 6))
        self.rim_entry = ttk.Entry(opts, textvariable=self.rim_custom, width=12)
        self.rim_entry.grid(row=1, column=4, sticky="w", pady=(2, 0))

        ttk.Label(opts, text="Z = 0 at").grid(row=1, column=0, sticky="w", pady=3)
        zrow = ttk.Frame(opts)
        zrow.grid(row=1, column=1, columnspan=2, sticky="w")
        ttk.Radiobutton(zrow, text="Top of board", variable=self.z_datum,
                        value="top").pack(side="left")
        ttk.Radiobutton(zrow, text="Bottom of board", variable=self.z_datum,
                        value="bottom").pack(side="left", padx=(10, 0))

        # --- silkscreen ---
        # The colour is a closed two-item choice, not the free entry the board
        # rim gets: legend ink is white or black and nothing else, so offering
        # a hex field here would only invite a value no fab can print.
        silk_row = ttk.Frame(opts)
        silk_row.grid(row=2, column=0, columnspan=5, sticky="w", pady=(6, 0))
        ttk.Label(silk_row, text="Silkscreen").pack(side="left")
        ttk.Checkbutton(silk_row, text="Top", variable=self.silk_top,
                        command=self._update_silk_row).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(silk_row, text="Bottom", variable=self.silk_bottom,
                        command=self._update_silk_row).pack(side="left", padx=(4, 0))
        ttk.Label(silk_row, text="Colour").pack(side="left", padx=(12, 6))
        self.silk_box = ttk.Combobox(
            silk_row, textvariable=self.silk_color, values=SILK_ORDER,
            state="readonly", width=10
        )
        self.silk_box.pack(side="left")
        self._silk_swatch = tk.Canvas(silk_row, width=22, height=22, highlightthickness=1,
                                      highlightbackground="#888")
        self._silk_swatch.pack(side="left", padx=(6, 0))
        self.silk_box.bind("<<ComboboxSelected>>", lambda e: self._update_silk_row())
        # Measured on a 150-polygon legend: 2191 kB as solids, 566 kB as
        # surfaces. Offered as a checkbox rather than done silently because it
        # is a real trade: the ink stops being a solid.
        self.silk_flat_check = ttk.Checkbutton(
            silk_row, text="Flat (about 1/4 the size)", variable=self.silk_flat
        )
        self.silk_flat_check.pack(side="left", padx=(12, 0))

        # --- silkscreen layers ---
        # Checkbuttons, not a multi-select Listbox: a highlighted row reads as
        # "current item", a tick reads as "included", and included is the
        # question. The list is built from the JSON that will actually be
        # built, so it can never offer a layer that would do nothing, and each
        # row carries its polygon count - that is what explains a large file.
        layers_frame = ttk.LabelFrame(opts, text="Silkscreen layers", padding=4)
        layers_frame.grid(row=3, column=0, columnspan=5, sticky="ew", pady=(6, 0))
        layers_frame.columnconfigure(0, weight=1)

        self._layers_canvas = tk.Canvas(layers_frame, height=96, highlightthickness=0)
        self._layers_canvas.grid(row=0, column=0, sticky="ew")
        layers_scroll = ttk.Scrollbar(layers_frame, orient="vertical",
                                      command=self._layers_canvas.yview)
        layers_scroll.grid(row=0, column=1, sticky="ns")
        self._layers_canvas.configure(yscrollcommand=layers_scroll.set)
        self._layers_inner = ttk.Frame(self._layers_canvas)
        self._layers_window = self._layers_canvas.create_window(
            (0, 0), window=self._layers_inner, anchor="nw")
        self._layers_inner.bind(
            "<Configure>",
            lambda e: self._layers_canvas.configure(
                scrollregion=self._layers_canvas.bbox("all")))
        self._layers_canvas.bind(
            "<Configure>",
            lambda e: self._layers_canvas.itemconfigure(self._layers_window,
                                                        width=e.width))

        # The wheel over the panel must scroll it. Binding the canvas alone is
        # not enough: the pointer is nearly always over a Checkbutton or the
        # inner frame, and those consume the event, so the wheel only worked on
        # the scrollbar itself. Binding every child is worse - the list is
        # rebuilt constantly. So grab the wheel while the pointer is inside the
        # panel and release it on the way out, which leaves the wheel alone
        # everywhere else in the window.
        self._layers_canvas.bind("<Enter>", self._grab_wheel)
        self._layers_canvas.bind("<Leave>", self._release_wheel)

        layer_buttons = ttk.Frame(layers_frame)
        layer_buttons.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Button(layer_buttons, text="All", width=6,
                   command=lambda: self._set_all_layers(True)).pack(side="left")
        ttk.Button(layer_buttons, text="None", width=6,
                   command=lambda: self._set_all_layers(False)).pack(side="left", padx=(4, 0))

        checks = ttk.Frame(opts)
        checks.grid(row=4, column=0, columnspan=5, sticky="w", pady=(6, 0))
        # MFRPN DISABLED (property attachment unreliable); kept for future:
        # ttk.Checkbutton(checks, text="Append MFRPN to instance names",
        #                 variable=self.mfr_pn_in_name).pack(side="left")
        ttk.Checkbutton(checks, text="Minimise file size",
                        variable=self.minimize).pack(side="left")
        # Inspection mode. Only does anything on a multi-stackup board, and it
        # is deliberately not hidden away in the config file: it is the thing
        # you reach for when a stackup looks wrong and you want to take the
        # board apart by eye.
        # Leaves the mask out of the board however the design defines it, and
        # closes the stack toward the core by what was removed.
        ttk.Checkbutton(checks, text="Ignore soldermask layers",
                        variable=self.ignore_soldermask).pack(side="left", padx=(12, 0))

        self._build_board_mode_row(opts)

        # --- log ---
        log_frame = ttk.LabelFrame(self, text="Log", padding=4)
        log_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        # wrap="word": build messages carry full paths and OCCT errors, which
        # ran off the right edge with no horizontal scrollbar to reach them.
        self.log_view = tk.Text(log_frame, height=10, wrap="word", state="disabled")
        self.log_view.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, command=self.log_view.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_view.configure(yscrollcommand=scroll.set)
        # severity colours: warnings orange, errors dark red
        self.log_view.tag_configure("warning", foreground="#d9791e")
        self.log_view.tag_configure("error", foreground="#8b0000")
        self.log_view.tag_configure("success", foreground="#1a7f2e")

        # --- bottom ---
        bottom = ttk.Frame(self, padding=(8, 4, 8, 8))
        bottom.grid(row=3, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(bottom, mode="determinate")
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._actions = ttk.Frame(bottom)
        self._actions.grid(row=0, column=1, sticky="e")
        self._build_actions()
        ttk.Label(bottom, textvariable=self.status, foreground="#555").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )

        self._update_swatch()
        self._update_rim_entry()
        self._update_silk_row()
        # Typing, pasting, Browse and the Allegro prefill all land in this one
        # variable, so one trace covers every way the JSON can change.
        self.json_file.trace_add("write", self._schedule_layer_refresh)
        self._refresh_layers()

    # --------------------------------------------------- window placement -- #

    def _virtual_screen(self) -> tuple[int, int, int, int]:
        """(x, y, w, h) covering EVERY monitor, not just the primary one.

        Tk's winfo_screenwidth/height describe the primary display only, so a
        window legitimately sitting on a second monitor looks off-screen by
        those numbers - which is exactly the case this feature exists for.
        Windows reports the whole virtual desktop through GetSystemMetrics
        (SM_[XY]VIRTUALSCREEN / SM_C[XY]VIRTUALSCREEN), and a monitor left of
        the primary gives a negative origin.

        Falls back to the primary display if that call is unavailable, so this
        degrades to single-monitor behaviour rather than failing.
        """
        try:
            import ctypes

            metrics = ctypes.windll.user32.GetSystemMetrics
            x, y, w, h = (metrics(i) for i in (76, 77, 78, 79))
            if w > 0 and h > 0:
                return x, y, w, h
        except Exception:
            pass
        return 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()

    def _geometry_is_reachable(self, w: int, h: int, x: int, y: int) -> bool:
        """Can the user actually see and grab a window placed here?

        The case that matters: the window was last closed on a second monitor
        that is no longer attached. Restoring those coordinates puts it
        somewhere invisible with no way to drag it back, which reads as the
        program failing to start.
        """
        vx, vy, vw, vh = self._virtual_screen()
        if y < vy:
            return False                      # title bar above every screen
        visible_w = max(0, min(x + w, vx + vw) - max(x, vx))
        visible_h = max(0, min(y + h, vy + vh) - max(y, vy))
        return visible_w >= 120 and visible_h >= 40

    def _center_on_primary(self) -> None:
        """First run, or a remembered position that is no longer usable."""
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = max(0, (self.winfo_screenwidth() - w) // 2)
        y = max(0, (self.winfo_screenheight() - h) // 2)
        self.geometry(f"+{x}+{y}")

    def _restore_geometry(self) -> None:
        if self._saved_geometry:
            # Tk writes a negative coordinate as "+-1920", so the sign sits
            # after the plus. A bare "-1920" in a geometry string means
            # something else entirely (an offset from the right edge), which is
            # why this matches the "+" form only and centres on anything else.
            match = re.match(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$",
                             self._saved_geometry.strip())
            if match:
                w, h, x, y = (int(g) for g in match.groups())
                if self._geometry_is_reachable(w, h, x, y):
                    self.geometry(f"{w}x{h}+{x}+{y}")
                    if self._saved_state == "zoomed":
                        self.state("zoomed")
                    return
                self.after(200, lambda: self._append_log(
                    "The remembered window position is off-screen (a monitor may "
                    "have been disconnected); centred on the main screen instead."))
        self._center_on_primary()

    def _remember_geometry(self, _event=None) -> None:
        """Keep the last non-maximized geometry. Bound to <Configure>.

        Two filters, and the second one is not redundant: maximizing arrives as
        a Configure whose event can still be seen while state() reports
        "normal", so the maximized rect would be recorded as if the user had
        sized the window that way, and un-maximizing on the next run would give
        back a screen-sized window that is not maximized.
        """
        if self.state() != "normal":
            return
        near_screen = (self.winfo_width() >= self.winfo_screenwidth() - 20
                       and self.winfo_height() >= self.winfo_screenheight() - 80)
        if near_screen:
            return
        self._last_normal_geometry = self.geometry()

    def _build_board_mode_row(self, parent) -> None:
        """How the board body is built, and the colour of each layer kind.

        Both live on one row: the swatches only mean anything in "Layer
        colours", so they are greyed out otherwise rather than hidden - a row
        that appears and disappears makes the window jump.
        """
        row = ttk.Frame(parent)
        row.grid(row=4, column=0, columnspan=5, sticky="w", pady=(6, 0))

        ttk.Label(row, text="Board").pack(side="left")
        box = ttk.Combobox(row, textvariable=self.board_mode,
                           values=[label for _, label in BOARD_MODES],
                           state="readonly", width=28)
        box.pack(side="left", padx=(6, 0))
        box.bind("<<ComboboxSelected>>", lambda e: self._update_layer_swatches())

        self._swatches: dict[str, tk.Canvas] = {}
        for key, label, _ in LAYER_KINDS:
            if key == "other":            # not a layer anyone sets on purpose
                continue
            cell = ttk.Frame(row)
            cell.pack(side="left", padx=(10, 0))
            canvas = tk.Canvas(cell, width=18, height=18, highlightthickness=1,
                               highlightbackground="#888", cursor="hand2")
            canvas.pack(side="top")
            canvas.bind("<Button-1>", lambda e, k=key: self._pick_layer_color(k))
            ttk.Label(cell, text=label, foreground="#777").pack(side="top")
            self._swatches[key] = canvas
        self._update_layer_swatches()

    def _update_layer_swatches(self) -> None:
        active = _mode_key(self.board_mode.get()) == "layers"
        for key, canvas in self._swatches.items():
            rgb = self.layer_colors.get(key, DEFAULT_LAYER_COLORS[key])
            canvas.configure(bg="#%02x%02x%02x" % rgb if active else "#d9d9d9",
                             cursor="hand2" if active else "")

    def _pick_layer_color(self, kind: str) -> None:
        if _mode_key(self.board_mode.get()) != "layers":
            return
        from tkinter import colorchooser

        current = self.layer_colors.get(kind, DEFAULT_LAYER_COLORS[kind])
        rgb, _ = colorchooser.askcolor(
            color="#%02x%02x%02x" % current,
            title=f"Colour for {dict((k, l) for k, l, _ in LAYER_KINDS)[kind]}")
        if rgb:
            self.layer_colors[kind] = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
            self._update_layer_swatches()

    def _build_actions(self) -> None:
        """All action buttons live here. Add new ones alongside Generate."""
        self.generate_button = ttk.Button(
            self._actions, text="Generate", command=self.on_generate
        )
        self.generate_button.pack(side="left", padx=4)

    def _step_dirs_row(self, parent, row: int) -> None:
        """The STEP folders: an ordered search path, one folder per line.

        Multi-line rather than one field, because this is a precedence list and
        the order has to be visible AND editable: the first folder holding a
        given filename wins, which is how a project-local folder overrides the
        shared library. Editing the text is a faster way to reorder than any
        pair of up/down buttons, and pasting several paths at once works.

        Browse APPENDS instead of replacing - replacing would make adding a
        second folder require retyping the first.
        """
        ttk.Label(parent, text="STEP files").grid(row=row, column=0, sticky="nw", pady=3)
        box = ttk.Frame(parent)
        box.grid(row=row, column=1, sticky="ew", padx=6, pady=3)
        box.columnconfigure(0, weight=1)
        self._step_text = tk.Text(box, height=3, wrap="none", undo=True)
        self._step_text.grid(row=0, column=0, sticky="ew")
        # Flush whatever _load_config buffered before this widget existed.
        self.set_step_dirs(self._pending_step_dirs)
        bar = ttk.Scrollbar(box, command=self._step_text.yview)
        bar.grid(row=0, column=1, sticky="ns")
        self._step_text.configure(yscrollcommand=bar.set)
        # Inside the box, under the text - not in the parent grid, where it
        # would land in the cell the text box already occupies.
        ttk.Label(box, foreground="#777",
                  text="one folder per line; the first one holding a model wins").grid(
            row=1, column=0, sticky="w", pady=(2, 0))
        ttk.Button(parent, text="Add...", command=self._pick_step_dir).grid(
            row=row, column=2, sticky="n", pady=3)

    def step_dirs(self) -> list[str]:
        """The folders as an ordered list, blank lines dropped."""
        if self._step_text is None:
            return list(self._pending_step_dirs)
        raw = self._step_text.get("1.0", "end").splitlines()
        return [line.strip() for line in raw if line.strip()]

    def set_step_dirs(self, paths) -> None:
        values = [str(p) for p in paths]
        if self._step_text is None:
            self._pending_step_dirs = values
            return
        self._step_text.delete("1.0", "end")
        self._step_text.insert("1.0", "\n".join(values))

    def add_step_dir(self, path: str) -> None:
        """Append one folder, unless it is already listed."""
        current = self.step_dirs()
        if path in current:
            return
        self.set_step_dirs(current + [path])

    def _path_row(self, parent, row: int, label: str, var: tk.StringVar, command) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(parent, textvariable=var).grid(
            row=row, column=1, sticky="ew", padx=6, pady=3
        )
        ttk.Button(parent, text="Browse...", command=command).grid(
            row=row, column=2, pady=3
        )

    def _update_swatch(self) -> None:
        rgb = BOARD_THEMES.get(self.theme.get(), (128, 128, 128))
        self._swatch.configure(bg="#%02x%02x%02x" % rgb)

    def _update_rim_entry(self) -> None:
        active = self.rim_choice.get() == RIM_CUSTOM
        self.rim_entry.configure(state="normal" if active else "disabled")
        # Grey the HEX label in step with the field it labels.
        self.rim_hex_label.state(["!disabled"] if active else ["disabled"])

    # ------------------------------------------------------- silk layers -- #

    def _grab_wheel(self, _event=None) -> None:
        self.bind_all("<MouseWheel>", self._on_layers_wheel)
        # X11 reports the wheel as buttons 4 and 5; harmless on Windows.
        self.bind_all("<Button-4>", self._on_layers_wheel)
        self.bind_all("<Button-5>", self._on_layers_wheel)

    def _release_wheel(self, _event=None) -> None:
        self.unbind_all("<MouseWheel>")
        self.unbind_all("<Button-4>")
        self.unbind_all("<Button-5>")

    def _on_layers_wheel(self, event) -> None:
        # Nothing to scroll when the list already fits: without this the canvas
        # rubber-bands the content out of view on a short list.
        region = self._layers_canvas.bbox("all")
        if not region or region[3] - region[1] <= self._layers_canvas.winfo_height():
            return
        if getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        else:
            step = -1 if event.delta > 0 else 1
        self._layers_canvas.yview_scroll(step, "units")

    def _schedule_layer_refresh(self, *_args) -> None:
        """Rebuild the layer list shortly after the JSON path settles.

        Debounced: the field changes on every keystroke when a path is typed,
        and each refresh reads and parses the JSON.
        """
        if self._layer_refresh_job is not None:
            self.after_cancel(self._layer_refresh_job)
        self._layer_refresh_job = self.after(400, self._refresh_layers)

    def _refresh_layers(self) -> None:
        """Read the queued JSON(s) and redraw the checkbox list."""
        self._layer_refresh_job = None
        for child in self._layers_inner.winfo_children():
            child.destroy()

        field = self.json_file.get().strip()
        found: dict[str, dict[str, int]] = {}
        if field:
            jobs, _ = core.resolve_json_jobs(Path(field))
            # Several variants build in one press, so the list is their union:
            # a layer present in any of them is a layer you can switch off.
            for job in jobs:
                for side, counts in core.silkscreen_layers(job).items():
                    into = found.setdefault(side, {})
                    for layer, n in counts.items():
                        into[layer] = into.get(layer, 0) + n

        if not found:
            # grid, like the side columns below: pack and grid cannot both
            # manage children of one container, and this label shares
            # _layers_inner with them.
            ttk.Label(self._layers_inner, foreground="#777",
                      text="No layer information in this JSON — the whole "
                           "legend is built. Re-export to choose layers.").grid(
                row=0, column=0, sticky="w", padx=4, pady=2)
            self._layer_vars = {}
            self._layer_rows = {"top": [], "bottom": []}
            return

        # Keep the ticks the user already set for layers that are still here,
        # so a refresh does not undo a selection.
        previous = {name: var.get() for name, var in self._layer_vars.items()}
        self._layer_vars = {}

        # Side by side, not stacked: a board's two sides rarely have many
        # layers each, so two short columns fit where one long list would
        # scroll, and the sides stay comparable at a glance. Columns are
        # allocated only to sides that have layers, so a top-only board does
        # not leave a gap where Bottom would have been.
        self._layer_rows = {"top": [], "bottom": []}
        column = 0
        for side in ("top", "bottom"):
            if side not in found:
                continue
            side_frame = ttk.Frame(self._layers_inner)
            side_frame.grid(row=0, column=column, sticky="nw", padx=(0, 18))
            column += 1
            ttk.Label(side_frame, text=side.capitalize(),
                      foreground="#555").pack(anchor="w", padx=2, pady=(2, 0))
            for layer in sorted(found[side]):
                # A layer already switched off in the config starts unticked;
                # one this build has never seen starts ON. Storing exclusions
                # rather than inclusions is what makes that the default - a
                # layer that appears on a new board must not go missing
                # silently.
                state = previous.get(layer, layer not in self._layers_off)
                var = tk.BooleanVar(value=state)
                self._layer_vars[layer] = var
                box = ttk.Checkbutton(
                    side_frame, variable=var,
                    text=f"{layer}   ({found[side][layer]})",
                )
                box.pack(anchor="w", padx=(16, 4))
                self._layer_rows[side].append((layer, var, box))

        # A side switched off greys its layers out immediately, not on the next
        # refresh.
        self._update_silk_row()

    def _side_wanted(self, side: str) -> bool:
        return self.silk_top.get() if side == "top" else self.silk_bottom.get()

    def _set_all_layers(self, state: bool) -> None:
        """All / None, but only for sides that are switched on.

        A greyed-out side keeps its ticks. Changing them from here would edit a
        selection whose effect is not visible, and it is that same selection
        which gets saved to the config.
        """
        for side, rows in self._layer_rows.items():
            if not self._side_wanted(side):
                continue
            for _layer, var, _box in rows:
                var.set(state)

    def _current_layers_off(self) -> set[str]:
        """Layer names currently unticked."""
        return {name for name, var in self._layer_vars.items() if not var.get()}

    def _update_silk_row(self) -> None:
        """Keep the ink swatch and the enabled state in step with the checkboxes."""
        on = self.silk_top.get() or self.silk_bottom.get()
        # Grey the layers of a side that is off. State only - the variables are
        # untouched, so the ticks come back exactly as they were.
        for side, rows in self._layer_rows.items():
            state = "normal" if self._side_wanted(side) else "disabled"
            for _layer, _var, box in rows:
                box.configure(state=state)
        self.silk_box.configure(state="readonly" if on else "disabled")
        self.silk_flat_check.configure(state="normal" if on else "disabled")
        rgb = SILK_COLORS.get(self.silk_color.get(), (128, 128, 128))
        self._silk_swatch.configure(bg="#%02x%02x%02x" % rgb)

    # ------------------------------------------------------------ prefill -- #

    def _show_path(self, p) -> str:
        """Display paths with forward slashes consistently.

        Allegro sends '/', pathlib prints '\\' on Windows; mixing them in the
        fields looks broken. Forward slashes are valid on Windows and match what
        the launcher passes, so normalise to them for display. (The actual file
        operations use Path, which accepts either.)
        """
        return str(p).replace("\\", "/")

    def prefill_jobs(self, *, json_dir=None, json_file=None, brd_name=None,
                     dated_name=False, output_dir=None) -> None:
        """Prefill from the Allegro launcher.

        Explicit launch arguments ALWAYS win over paths remembered from a
        previous session: when Simple 3D is run for a new board, its JSON and
        output folder must replace whatever the config file held, otherwise the
        window would show the previous board's paths (and build it by mistake).

        This method only fills the visible fields and logs what is queued. The
        actual job list is resolved from the JSON field when Generate is
        pressed (core.resolve_json_jobs), so there is no hidden queue that can
        go stale if the user browses to a different file afterwards.

        json_dir: a folder of variant JSONs -> all are built on Generate.
        json_file: a single JSON.
        """
        self._brd_name = brd_name
        self._dated_name = dated_name
        # Paths that came from Allegro describe the board being exported, not a
        # preference, so they are not written back to the settings file - see
        # _save_config. Without this every export of a different board rewrote
        # jsonFile and outputDir, churning a file that is meant to hold
        # settings and losing to the next export anyway.
        if json_dir or json_file or output_dir:
            self._paths_from_launcher = True

        if output_dir:
            self.output_dir.set(self._show_path(output_dir))

        if json_file:
            self.json_file.set(self._show_path(json_file))
        elif json_dir:
            folder = Path(json_dir)
            jobs, ignored = core.resolve_json_jobs(folder)
            if ignored:
                self.after(200, lambda: self._append_log(
                    f"Ignored {len(ignored)} non-Simple-3D .json file(s): " +
                    ", ".join(j.name for j in ignored)))
            if len(jobs) == 1:
                self.json_file.set(self._show_path(jobs[0]))
            else:
                # several variants (or none): show the folder; Generate
                # re-resolves and, if empty, explains what it found.
                self.json_file.set(self._show_path(folder))
                if jobs:
                    self.after(250, lambda: self._append_log(
                        f"{len(jobs)} variant JSON(s) queued:\n  " +
                        "\n  ".join(j.name for j in jobs)))

        # Only fall back to deriving output from the json path if the launcher
        # did not supply one explicitly.
        if not output_dir and not self.output_dir.get() and (json_dir or json_file):
            self.output_dir.set(self._show_path(Path(json_dir or Path(json_file).parent)))

    # ------------------------------------------------------------ pickers -- #

    def _pick_step_dir(self) -> None:
        if path := filedialog.askdirectory(title="Add a directory of footprint STEP files"):
            self.add_step_dir(path)

    def _pick_json_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Intermediate JSON", filetypes=[("JSON", "*.json"), ("All", "*.*")]
        )
        if path:
            self.json_file.set(path)
            if not self.output_dir.get():
                self.output_dir.set(str(Path(path).parent))

    def _pick_output_dir(self) -> None:
        if path := filedialog.askdirectory(title="Output directory"):
            self.output_dir.set(path)

    # ------------------------------------------------------------ actions -- #

    def _rim_color(self):
        choice = self.rim_choice.get()
        if choice == RIM_SAME:
            return None
        if choice == RIM_CREAM:
            return CREAM_DIELECTRIC
        text = self.rim_custom.get().strip()
        if not text:
            return None
        return resolve_board_color(text)

    def _snapshot(self) -> BuildSettings:
        """Read every widget the build needs. MAIN THREAD ONLY - see BuildSettings.

        Raises ValueError if the custom rim colour does not parse, which doubles
        as the early validation on_generate wants.
        """
        return BuildSettings(
            step_dirs=tuple(self.step_dirs()),
            json_file=self.json_file.get(),
            output_dir=self.output_dir.get(),
            z_datum=self.z_datum.get(),
            board_color=BOARD_THEMES.get(self.theme.get()),
            rim_color=self._rim_color(),
            silk_top=self.silk_top.get(),
            silk_bottom=self.silk_bottom.get(),
            silk_color=SILK_COLORS.get(self.silk_color.get()),
            silk_flat=self.silk_flat.get(),
            silk_flat_height=self.silk_flat_height,
            silk_layers_off=frozenset(self._current_layers_off()),
            minimize=self.minimize.get(),
            board_mode=_mode_key(self.board_mode.get()),
            layer_colors=dict(self.layer_colors),
            ignore_soldermask=self.ignore_soldermask.get(),
            brd_name=self._brd_name,
            dated_name=self._dated_name,
        )

    def on_generate(self) -> None:
        if not self.step_dirs() or not self.json_file.get() or not self.output_dir.get():
            messagebox.showwarning(
                "Missing input",
                "Please set at least one STEP folder, the JSON file and the output directory."
            )
            return
        try:
            settings = self._snapshot()   # also validates the custom colour
        except ValueError as exc:
            messagebox.showerror("Bad colour", str(exc))
            return

        self._clear_log()
        self._run_in_worker(lambda: self._generate(settings))

    def _generate(self, settings: BuildSettings) -> None:
        """Runs on the worker thread. Builds one or many JSONs.

        Reads nothing from the widgets - everything comes from *settings*, taken
        on the main thread by _snapshot().

        The job list is resolved HERE, from the JSON path as it was when
        Generate was pressed - never from a cached queue. This way, browsing to
        a different file after an Allegro prefill builds exactly what the field
        showed at that moment.
        """
        field = Path(settings.json_file)
        jobs, ignored = core.resolve_json_jobs(field)

        for j in ignored:
            self._queue.put(("log", f"Ignoring non-Simple-3D json: {j.name}"))

        if not jobs:
            # Explain precisely what was found, so a wrong path, an empty
            # folder and a foreign json are distinguishable at a glance.
            if field.is_dir():
                entries = sorted(p.name for p in field.iterdir())
                detail = (f"Folder {self._show_path(field)} contains: "
                          + (", ".join(entries) if entries else "(empty)"))
            elif field.is_file():
                detail = (f"{self._show_path(field)} is not a Simple 3D "
                          'intermediate (missing the "format": "simple3d" '
                          "marker). Pick a JSON produced by "
                          "File -> Export -> Simple 3D.")
            else:
                detail = f"Path does not exist: {self._show_path(field)}"
            raise core.StepBuilderError(f"No JSON file to build.\n{detail}")

        total_placed = 0
        outputs = []
        warnings = []
        failures = []
        for jf in jobs:
            # Base name for the output file. With SEVERAL variants the stem of
            # each json (design_variant) must win, or every variant would get
            # the same name and only differ by collision underscores. The
            # launcher's brd_name (original-case board name) applies only when
            # there is a single json.
            if len(jobs) > 1:
                base = jf.stem
            else:
                base = settings.brd_name or jf.stem

            # One variant must not take the rest of the batch down with it: a
            # gap in board 2's outline should still leave boards 3..n built.
            # This mirrors the CLI, which counts failures and carries on.
            try:
                output_name = (core.dated_output_name(base, settings.output_dir)
                               if settings.dated_name else None)
                result = core.generate(
                    list(settings.step_dirs),
                    jf,
                    settings.output_dir,
                    output_name=output_name,
                    z_datum=settings.z_datum,
                    board_color=settings.board_color,
                    rim_color=settings.rim_color,
                    silk_top=settings.silk_top,
                    silk_bottom=settings.silk_bottom,
                    silk_color=settings.silk_color,
                    silk_flat=settings.silk_flat,
                    silk_flat_height=settings.silk_flat_height,
                    silk_layers_off=settings.silk_layers_off,
                    # MFRPN DISABLED (kept for future): name_instances_with_mfr_pn=...,
                    minimize_size=settings.minimize,
                    board_mode=settings.board_mode,
                    layer_colors=settings.layer_colors,
                    ignore_soldermask=settings.ignore_soldermask,
                    log=lambda m: self._queue.put(("log", m)),
                    progress=lambda i, n: self._queue.put(("progress", (i, n))),
                )
            except core.StepBuilderError as exc:
                failures.append(f"{jf.name}: {exc}")
                self._queue.put(("log", f"error ({jf.name}): {exc}"))
                continue
            except Exception:
                # Unexpected (a malformed JSON key, an OCCT failure): keep the
                # traceback so the bug is reportable, but still build the rest.
                failures.append(f"{jf.name}: unexpected error (see log)")
                self._queue.put(("log", f"error ({jf.name}):\n{traceback.format_exc()}"))
                continue

            total_placed += result.components_placed
            outputs.append(result.output.name)
            if result.silkscreen_solids:
                self._queue.put(("log", f"{result.output.name}: silkscreen "
                                        f"{result.silkscreen_solids} solid(s)"))
            if result.missing_step_files:
                warnings.append(f"{result.output.name}: {len(result.missing_step_files)} STEP missing")
            if result.embedded_not_on_disk:
                warnings.append(
                    f"{result.output.name}: {len(result.embedded_not_on_disk)} of "
                    f"those are in the board but not on disk (see the log)")
            # MFRPN DISABLED (kept for future):
            # if result.missing_mfr_pn:
            #     warnings.append(f"{result.output.name}: {len(result.missing_mfr_pn)} without MFRPN")

        for w in warnings:
            self._queue.put(("log", "warning: " + w))

        # Nothing built at all -> report as a failure, not a green "Done: 0".
        if failures and not outputs:
            self._queue.put(("error", f"All {len(failures)} job(s) failed:\n"
                                      + "\n".join(failures)))
            return

        summary = f"Done: {len(outputs)} file(s), {total_placed} component(s) placed"
        if failures:
            summary += f", {len(failures)} failed"
        self._queue.put(("done", summary))


    # ------------------------------------------------------------ plumbing - #

    def _run_in_worker(self, target) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._set_busy(True)

        def wrapper() -> None:
            try:
                target()
            except core.StepBuilderError as exc:
                self._queue.put(("error", str(exc)))
            except Exception:
                self._queue.put(("error", traceback.format_exc()))

        self._worker = threading.Thread(target=wrapper, daemon=True)
        self._worker.start()

    def _drain_queue(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "progress":
                    current, total = payload
                    self.progress["maximum"] = max(total, 1)
                    self.progress["value"] = current
                    self.status.set(f"Placing components {current}/{total}")
                elif kind == "done":
                    self._append_log(payload, "success")
                    self.status.set(payload)
                    self._set_busy(False)
                elif kind == "error":
                    self._append_log(payload, "error")
                    self.status.set("Failed")
                    self._set_busy(False)
                    messagebox.showerror("StepBuilder", payload.strip().splitlines()[-1])
        except queue.Empty:
            pass
        self._drain_job = self.after(100, self._drain_queue)

    def _set_busy(self, busy: bool) -> None:
        for child in self._actions.winfo_children():
            child.configure(state="disabled" if busy else "normal")
        if busy:
            self.status.set("Working...")
            self.progress["value"] = 0

    def _append_log(self, message: str, severity: str | None = None) -> None:
        # Auto-detect severity from the message if not given, so plain "log"
        # queue items are coloured too.
        if severity is None:
            low = message.lstrip().lower()
            if low.startswith(ERROR_PREFIXES):
                severity = "error"
            elif low.startswith(WARNING_PREFIXES):
                severity = "warning"
        self.log_view.configure(state="normal")
        text = message.rstrip() + "\n"
        if severity:
            self.log_view.insert("end", text, severity)
        else:
            self.log_view.insert("end", text)
        self.log_view.see("end")
        self.log_view.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_view.configure(state="normal")
        self.log_view.delete("1.0", "end")
        self.log_view.configure(state="disabled")

    # -------------------------------------------------------------- config - #

    def _read_config_file(self) -> tuple[dict, str | None]:
        """(document, problem). *problem* is None only when the file read cleanly.

        The distinction matters more than it looks: treating "could not read" as
        "empty" is what let a save write a document containing nothing but the
        "gui" section, destroying the silkscreen layer lists and the Allegro
        settings alongside it. Nothing may be written unless the existing file
        was understood first.

        Read as utf-8-sig, so a file an editor saved with a BOM still parses -
        that alone is enough to make json.loads fail on otherwise valid JSON.
        """
        if not self.config_path.exists():
            return {}, f"settings file not found: {self.config_path}"
        try:
            text = self.config_path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            return {}, f"cannot read {self.config_path}: {exc}"
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            return {}, f"{self.config_path.name} is not valid JSON: {exc}"
        if not isinstance(data, dict):
            return {}, f"{self.config_path.name} does not hold a JSON object"
        return data, None

    def _load_config(self) -> None:
        data, self._config_problem = self._read_config_file()
        gui = data.get("gui")
        if not isinstance(gui, dict):
            return
        # stepDirs (a list) is the shape. stepDir (a single string) is what a
        # config written before multi-folder support holds; it is read ONCE so
        # that setting survives the upgrade, and _save_config then drops it -
        # see there for why it is not mirrored back.
        dirs = gui.get("stepDirs")
        if isinstance(dirs, list):
            self.set_step_dirs([str(d).strip() for d in dirs if str(d).strip()])
        else:
            single = str(gui.get("stepDir", "")).strip()
            self.set_step_dirs([single] if single else [])
        self.json_file.set(gui.get("jsonFile", ""))
        self.output_dir.set(gui.get("outputDir", ""))
        self.z_datum.set(gui.get("zDatum", "top"))
        self.theme.set(gui.get("boardColor", DEFAULT_THEME))
        self.rim_choice.set(gui.get("boardEdge", RIM_SAME))
        self.rim_custom.set(gui.get("boardEdgeCustom", ""))
        self.silk_top.set(gui.get("silkscreenTop", True))
        self.silk_bottom.set(gui.get("silkscreenBottom", True))
        self.silk_color.set(gui.get("silkColor", DEFAULT_SILK))
        self.silk_flat.set(gui.get("silkscreenFlat", False))
        off = gui.get("silkscreenLayersOff")
        self._layers_off = set(off) if isinstance(off, list) else set()
        try:
            self.silk_flat_height = abs(float(gui.get("silkscreenFlatHeight",
                                                      DEFAULT_FLAT_HEIGHT)))
        except (TypeError, ValueError):
            self.silk_flat_height = DEFAULT_FLAT_HEIGHT
        # MFRPN DISABLED (kept for future):
        # self.mfr_pn_in_name.set(gui.get("mfrPnInName", False))
        self.minimize.set(gui.get("minimizeFileSize", True))
        # debugLayers was the previous shape of this setting: a single boolean
        # meaning "inspect". Read once so an existing config keeps working, and
        # dropped on save - see _save_config.
        mode = gui.get("boardMode")
        if not isinstance(mode, str) or mode not in dict(BOARD_MODES):
            mode = "inspect" if gui.get("debugLayers") else "solid"
        self.board_mode.set(_mode_label(mode))
        saved = gui.get("layerColors")
        if isinstance(saved, dict):
            for key, value in saved.items():
                if key in self.layer_colors:
                    try:
                        self.layer_colors[key] = parse_hex(str(value))
                    except ValueError:
                        pass
        self.ignore_soldermask.set(gui.get("ignoreSoldermask", False))
        geometry = gui.get("windowGeometry")
        self._saved_geometry = geometry if isinstance(geometry, str) else None
        self._saved_state = ("zoomed" if gui.get("windowState") == "zoomed"
                             else "normal")

    def _save_config(self) -> None:
        """Write the "gui" section back, leaving the rest of the file alone.

        Read-modify-write rather than a fresh document: the same file carries
        the silkscreen layer lists and the Allegro-side settings, and losing
        those on window close would be a great deal worse than forgetting a
        path.

        If the file cannot be read - missing, unparsable, whatever - NOTHING is
        written. That is the whole point. The previous version treated an
        unreadable file as an empty one and cheerfully wrote back a document
        holding only "gui", which is exactly how a user's settings file came
        back with every other section gone. A settings file this build does not
        understand is a file it has no business rewriting.

        A file that cannot be WRITTEN is still ignored silently: a read-only
        install directory must not turn closing the window into an error dialog.
        """
        # Two separate conditions, and missing the first one wiped a user's
        # stepDir. The file is re-read here, but what would be written comes
        # from the WIDGETS - and if the load failed at startup the widgets hold
        # defaults, not settings. So a config that was unreadable when the
        # window opened and readable by the time it closed (the user repaired
        # it meanwhile, which is exactly what happened) passed the save-time
        # check and wrote empty fields over good values.
        #
        # Nothing may be written unless the file was understood BOTH when it
        # was loaded and now.
        if self._config_problem is not None:
            return
        data, problem = self._read_config_file()
        if problem is not None:
            return
        # Merge into the existing section, do not replace it. The file is
        # hand-edited, so "gui" can hold keys this build does not know -
        # comments, a setting added by a later version, a value someone parked
        # there - and replacing the section wholesale would delete them on
        # window close. Same reasoning as preserving the other sections, one
        # level down.
        gui = data.get("gui")
        if not isinstance(gui, dict):
            gui = {}
        # The superseded single-folder key is REMOVED, not kept in step with the
        # first entry. Mirroring it would leave two keys meaning one thing
        # forever: stepDirs always wins, so a hand-edit of stepDir does nothing
        # and is silently overwritten on the next close. The read above has
        # already migrated any value it held.
        #
        # This is not the "preserve keys we do not understand" rule from the
        # config-safety work: that protects keys belonging to someone else. This
        # one is ours and superseded, and dropping it is the migration.
        gui.pop("stepDir", None)
        # Superseded by boardMode; the read above has already migrated it.
        gui.pop("debugLayers", None)
        dirs = self.step_dirs()
        gui.update({
            "stepDirs": dirs,
            "zDatum": self.z_datum.get(),
            "boardColor": self.theme.get(),
            "boardEdge": self.rim_choice.get(),
            "boardEdgeCustom": self.rim_custom.get(),
            "silkscreenTop": self.silk_top.get(),
            "silkscreenBottom": self.silk_bottom.get(),
            "silkColor": self.silk_color.get(),
            "silkscreenFlat": self.silk_flat.get(),
            "silkscreenFlatHeight": self.silk_flat_height,
            # Only overwrite the remembered exclusions once a list has actually
            # been shown; an old JSON with no layers must not wipe them.
            "silkscreenLayersOff": sorted(
                self._current_layers_off() if self._layer_vars else self._layers_off),
            # MFRPN DISABLED (kept for future):
            # "mfrPnInName": self.mfr_pn_in_name.get(),
            "minimizeFileSize": self.minimize.get(),
            "boardMode": _mode_key(self.board_mode.get()),
            "layerColors": {k: "#%02X%02X%02X" % v
                            for k, v in self.layer_colors.items()},
            "ignoreSoldermask": self.ignore_soldermask.get(),
            # Where the window was, so the next run comes up in the same place -
            # on the same monitor, which is the point on a multi-screen desk.
            # The non-maximized rect is stored even when closing maximized, so
            # un-maximizing later gives back a sane window.
            "windowGeometry": self._last_normal_geometry or self.geometry(),
            "windowState": "zoomed" if self.state() == "zoomed" else "normal",
        })
        # The board being exported is not a setting. When Allegro supplied
        # these, whatever the file already holds is left as it is; only a
        # standalone run - where the user picked the paths - records them.
        if not self._paths_from_launcher:
            gui["jsonFile"] = self.json_file.get()
            gui["outputDir"] = self.output_dir.get()
        data["gui"] = gui
        # Written to a temporary file and renamed into place. This file now
        # carries the SKILL side's configuration as well, so it must never be
        # left half written if the process dies mid-save.
        tmp = self.config_path.with_suffix(self.config_path.suffix + ".tmp")
        try:
            tmp.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n",
                           encoding="utf-8")
            os.replace(tmp, self.config_path)
        except OSError:
            try:
                tmp.unlink()
            except OSError:
                pass

    def _on_close(self) -> None:
        self._save_config()
        # The queue drain reschedules itself every 100 ms. Left pending, it
        # fires once more against a destroyed widget and Tk prints
        # 'invalid command name "..._drain_queue"' - invisible under pythonw,
        # but noise on the console for anyone running the GUI with python.
        for job in (self._drain_job, self._layer_refresh_job):
            if job is not None:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        self._drain_job = None
        self._layer_refresh_job = None
        self.destroy()


def main(config_path: Path | None = None) -> None:
    StepBuilderApp(config_path).mainloop()
