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

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import core
from . import settings
from . import winplace
from .widgets.layers_panel import LayersPanel
from .worker import BuildSettings
from .worker_bridge import WorkerBridge
from .bend import DEFAULT_NEUTRAL_FACTOR, DEFAULT_SLICE_ANGLE
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

# Where the settings pair lives, and why: settings.py.
DEFAULT_CONFIG_PATH = settings.DEFAULT_CONFIG_PATH

# How the board body is built. One dropdown rather than a pile of checkboxes:
# the three are alternatives, and "inspect + layer colors" ticked together
# would have to mean something, which it does not.
BOARD_MODES = [
    ("solid",   "Solid"),
    ("layers",  "Solid colored layers"),
    ("inspect", "Not stitched"),
]
# The file stores the keys; settings.py validates against its own list.
assert tuple(k for k, _ in BOARD_MODES) == settings.BOARD_MODE_KEYS


def _mode_label(key: str) -> str:
    return dict(BOARD_MODES).get(key, BOARD_MODES[0][1])


def _mode_key(label: str) -> str:
    return next((k for k, l in BOARD_MODES if l == label), BOARD_MODES[0][0])


# The z datum, as a two-item dropdown. The variable behind it still holds the
# "top"/"bottom" keys the rest of the tool uses.
Z_LABELS = {"top": "Top of board", "bottom": "Bottom of board"}
Z_KEYS = {v: k for k, v in Z_LABELS.items()}

# Two kinds of color square, and they must not look alike. A DISPLAY swatch
# only reports what a dropdown already chose - the board theme, the silk ink -
# and clicking it does nothing. A PICKER swatch opens a color chooser. The
# picker is raised like a button and takes the hand cursor; the display one is
# flat with a hairline border and no cursor change.
SWATCH = dict(width=22, height=22)
DISPLAY_SWATCH = dict(SWATCH, highlightthickness=1, highlightbackground="#888",
                      relief="flat", borderwidth=0)
PICKER_SWATCH = dict(SWATCH, highlightthickness=0, relief="raised",
                     borderwidth=2, cursor="hand2")

# The grey a swatch wears when it does not apply - the mode ignores it, or a
# build is running. One name, because "looks live but is not" is the exact
# complaint this colour answers.
INACTIVE_SWATCH = "#d9d9d9"

# The rim choices are what the settings file stores - the label IS the value -
# so they live in settings.py; here for the widgets and for the tests.
RIM_SAME, RIM_CREAM, RIM_CUSTOM = settings.RIM_SAME, settings.RIM_CREAM, settings.RIM_CUSTOM

# Log lines arrive from core as plain text, so severity is inferred from how the
# line opens. core labels its own non-fatal lines with a "warning:" prefix, which
# is what colors them here AND marks them in the CLI's plain-text output - so
# prefer adding the prefix at the log() call over adding a pattern below.
# Match lowercase: _append_log lowercases before testing.
ERROR_PREFIXES = ("error", "traceback")
WARNING_PREFIXES = ("warning", "ignored", "ignoring")
# Advice rather than trouble: nothing is wrong, but a setting would serve this
# board better and the reader has to be able to find the line again.
NOTE_PREFIXES = ("note",)


# BuildSettings lives in worker.py, because it crosses the process boundary and
# that module must not drag tkinter into the child. Imported here so
# `from .gui import BuildSettings` keeps working.
__all__ = ["StepBuilderApp", "BuildSettings"]


# The merge lives in settings.py since round 72 (plan C1); this name stays
# because tests/test_config_merge.py imports it from here.
_merge_config = settings.merge_config


class StepBuilderApp(tk.Tk):
    def __init__(self, config_path: Path | None = None) -> None:
        super().__init__()
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self.title("Simple 3D - StepBuilder")
        self.minsize(760, 560)

        # A process, not a thread: OCC can die outright and take the whole
        # interpreter with it, and with a thread that means this window
        # vanishing with nothing written anywhere. See worker.py; the bridge
        # starts it, drains its queue and notices it die (worker_bridge.py).
        # What it reports lands in the _on_* methods below, on the Tk thread.
        self._bridge = WorkerBridge(
            on_log=self._append_log, on_progress=self._on_progress,
            on_done=self._on_done, on_error=self._on_error, on_crash=self._on_crash)

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
        # The whole-board file the export writes beside the variant ones.
        # On by default: it only exists when the Allegro side was told to
        # write it, and someone who asked for it usually wants it built.
        self.build_full = tk.BooleanVar(value=True)
        self.board_mode = tk.StringVar(value=BOARD_MODES[0][1])
        self.layer_colors: dict[str, tuple[int, int, int]] = dict(DEFAULT_LAYER_COLORS)
        self.ignore_soldermask = tk.BooleanVar(value=False)
        # On by default: a board whose designer went to the trouble of defining
        # bend areas is a board meant to be seen folded, and a design with none
        # is unaffected either way.
        self.fold_bends = tk.BooleanVar(value=True)
        # Config-only, no widget, same as silk_flat_height: numbers you set once
        # for a board, not something to press on every build. The anchor is the
        # point that stays in the XY plane (the origin by convention) and the
        # neutral factor is where the neutral axis sits in the stack.
        self.fold_anchor: tuple[float, float] | str | None = None
        self.fold_neutral: float = DEFAULT_NEUTRAL_FACTOR
        self.fold_slice_angle: float = DEFAULT_SLICE_ANGLE

        # Prefill state, set by prefill_jobs() when launched from Allegro.
        # Note: there is deliberately NO cached job list - jobs are resolved
        # from the JSON field at Generate time (see _generate).
        self._brd_name: str | None = None      # base name for dated output
        self._dated_name: bool = False
        self._config_problem: str | None = None
        # The local file has its own: a missing one is normal, but one
        # that will not parse must stop this window writing over it.
        self._local_problem: str | None = None
        # Busy is a state of the whole window, not just of the button: the
        # color swatches are Canvases with a click binding and no state to
        # disable, so they ask this instead. _frozen holds what each control
        # was before the build, to be put back exactly - see _freeze_inputs.
        self._busy = False
        self._frozen: dict = {}
        self._dimmed: dict = {}
        self._paths_from_launcher = False
        # Layers switched OFF, by name. Exclusions rather than inclusions: a
        # layer this build has never seen must default to ON, or a layer that
        # appears on a new board would silently go missing. The ticks
        # themselves live in the LayersPanel built by _build_ui.
        self._layers_off: set[str] = set()
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
        elif self._local_problem:
            self.after(150, lambda: self._append_log(
                f"warning: {self._local_problem}. Only the shipped defaults are "
                f"in use, and nothing will be saved until that file parses - it "
                f"is left untouched."))
        else:
            self.after(150, lambda: self._append_log(
                f"Settings loaded from {self._show_path(self.config_path)}"))
            # Named separately, because "why is this path not what the file
            # says" has one answer and it is this one.
            if self.local_config_path.exists():
                self.after(160, lambda: self._append_log(
                    f"Local settings on top: "
                    f"{self._show_path(self.local_config_path)}"))

    # ----------------------------------------------------------------- UI -- #

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)          # the log takes what is left

        # --- paths ---
        paths = ttk.LabelFrame(self, text="Input", padding=8)
        paths.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        paths.columnconfigure(1, weight=1)
        self._step_dirs_row(paths, 0)
        self._path_row(paths, 1, "JSON file", self.json_file, self._pick_json_file)
        self._path_row(paths, 2, "Output", self.output_dir, self._pick_output_dir)

        # --- board ---
        # Everything about the board body in one place, and everything about the
        # legend in the next. They were one "Options" block, which meant the two
        # unrelated halves of the window looked like one list of settings.
        # Board and Silk side by side rather than stacked. Stacked, the two
        # groups pushed the natural window height to 1004 px, which on a 1080p
        # screen fills it top to bottom on a first run; side by side the window
        # grows sideways instead, where there is room.
        mid = ttk.Frame(self)
        mid.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        # Board keeps its natural width and no more; every extra pixel goes to
        # Silk. Board options is a fixed set of dropdowns and swatches - widening
        # it only adds blank space - while the silk layer list is a column of
        # names that are routinely long enough to be cut off.
        mid.columnconfigure(0, weight=0)
        mid.columnconfigure(1, weight=1)

        opts = ttk.LabelFrame(mid, text="Board options", padding=8)
        opts.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        opts.columnconfigure(1, weight=1)
        opts.columnconfigure(3, weight=1)

        ttk.Label(opts, text="Board color").grid(row=0, column=0, sticky="w", pady=3)
        # Keep the combobox and its color swatch together in one frame so the
        # swatch sits directly beside the dropdown instead of being pushed to the
        # right edge by the expanding grid column.
        color_row = ttk.Frame(opts)
        color_row.grid(row=0, column=1, columnspan=2, sticky="w", padx=6)
        theme_box = ttk.Combobox(
            color_row, textvariable=self.theme, values=THEME_ORDER,
            state="readonly", width=11
        )
        theme_box.pack(side="left")
        self._swatch = tk.Canvas(color_row, **DISPLAY_SWATCH)
        self._swatch.pack(side="left", padx=(6, 0))
        theme_box.bind("<<ComboboxSelected>>", lambda e: self._update_swatch())

        ttk.Label(opts, text="Board edge color").grid(row=0, column=3, sticky="e", padx=(12, 6))
        self._rim_box = ttk.Combobox(
            opts, textvariable=self.rim_choice,
            values=[RIM_SAME, RIM_CREAM, RIM_CUSTOM], state="readonly", width=18
        )
        self._rim_box.grid(row=0, column=4, sticky="w")
        self._rim_box.bind("<<ComboboxSelected>>", lambda e: self._update_rim_swatch())
        # A picker, not a typed hex string: the same idiom as every other color
        # in the window, and it cannot be given a value that does not parse.
        # Greyed until Custom is chosen, so it is obvious when it does nothing.
        self._rim_swatch = tk.Canvas(opts, **PICKER_SWATCH)
        self._rim_swatch.grid(row=0, column=5, sticky="w", padx=(6, 0))
        self._rim_swatch.bind("<Button-1>", lambda e: self._pick_rim_color())

        # A two-item dropdown rather than two radios: same choice, one row
        # instead of a row of its own. The variable still holds "top"/"bottom",
        # so the config and every caller are untouched.
        ttk.Label(opts, text="Z = 0 at").grid(row=1, column=0, sticky="w", pady=3)
        self._z_label = tk.StringVar(value=Z_LABELS[self.z_datum.get()])
        zbox = ttk.Combobox(opts, textvariable=self._z_label,
                            values=list(Z_LABELS.values()), state="readonly",
                            width=16)
        zbox.grid(row=1, column=1, sticky="w", padx=6)
        zbox.bind("<<ComboboxSelected>>", lambda e: self.z_datum.set(
            Z_KEYS[self._z_label.get()]))

        self._build_board_mode_row(opts)
        # Leaves the mask out of the board however the design defines it, and
        # closes the stack toward the core by what was removed.
        ttk.Checkbutton(opts,
                        text=("Do not include soldermask layers\n"
                              "(check total thickness!)"),
                        variable=self.ignore_soldermask).grid(
            row=4, column=0, columnspan=6, sticky="w", pady=(6, 0))

        # Off means the board is exported flat, which is how Allegro holds it
        # and how every export before this behaved. Nothing to grey out when a
        # board has no bends: the label says what it would do, and the log says
        # what it did.
        ttk.Checkbutton(opts, text="Fold flex bends",
                        variable=self.fold_bends).grid(
            row=5, column=0, columnspan=6, sticky="w", pady=(6, 0))

        # --- silkscreen ---
        silk = ttk.LabelFrame(mid, text="Silk options", padding=8)
        silk.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        silk.columnconfigure(0, weight=1)

        # The color is a closed two-item choice, not the free picker the board
        # rim gets: legend ink is white or black and nothing else, so offering
        # a free color here would only invite a value no fab can print.
        silk_row = ttk.Frame(silk)
        silk_row.grid(row=0, column=0, sticky="w")
        ttk.Label(silk_row, text="Silkscreen").pack(side="left")
        ttk.Checkbutton(silk_row, text="Top", variable=self.silk_top,
                        command=self._update_silk_row).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(silk_row, text="Bottom", variable=self.silk_bottom,
                        command=self._update_silk_row).pack(side="left", padx=(4, 0))
        self._silk_color_label = ttk.Label(silk_row, text="Color")
        self._silk_color_label.pack(side="left", padx=(12, 6))
        self.silk_box = ttk.Combobox(
            silk_row, textvariable=self.silk_color, values=SILK_ORDER,
            state="readonly", width=6
        )
        self.silk_box.pack(side="left")
        self._silk_swatch = tk.Canvas(silk_row, **DISPLAY_SWATCH)
        self._silk_swatch.pack(side="left", padx=(6, 0))
        self.silk_box.bind("<<ComboboxSelected>>", lambda e: self._update_silk_row())
        # Measured on a 150-polygon legend: 2191 kB as solids, 566 kB as
        # surfaces. Offered as a checkbox rather than done silently because it
        # is a real trade: the ink stops being a solid.
        # Its own row for the same reason as the swatches: a long label on a
        # shared line makes the group demand width the window does not have.
        self.silk_flat_check = ttk.Checkbutton(
            silk, text="Make surface (minimum file size)", variable=self.silk_flat
        )
        self.silk_flat_check.grid(row=1, column=0, sticky="w", pady=(4, 0))

        # --- silkscreen layers ---
        # Checkbuttons, not a multi-select Listbox: a highlighted row reads as
        # "current item", a tick reads as "included", and included is the
        # question. The list is built from the JSON that will actually be
        # built, so it can never offer a layer that would do nothing, and each
        # row carries its polygon count - that is what explains a large file.
        ttk.Separator(silk, orient="horizontal").grid(
            row=2, column=0, sticky="ew", pady=(8, 6))
        self.layers = LayersPanel(silk, side_wanted=self._side_wanted)
        self.layers.grid(row=3, column=0, sticky="ew")
        # Everything in the group that should grey out when both sides are off.
        # The two side checkboxes are deliberately NOT in here: they are how the
        # group is switched back on.
        self._silk_group_widgets = [self._silk_color_label, self.layers, *self.layers.buttons]

        # Neither a board setting nor a legend one - it shrinks the whole file,
        # component models included - so it sits on its own between the groups
        # and the log rather than being filed under one of them.
        # MFRPN DISABLED (property attachment unreliable); kept for future:
        # ttk.Checkbutton(checks, text="Append MFRPN to instance names",
        #                 variable=self.mfr_pn_in_name).pack(side="left")
        checks = ttk.Frame(self, padding=(8, 0))
        checks.grid(row=2, column=0, sticky="w")
        # Not "Minimise file size": the silk row already has a "minimum file
        # size" and the two do different things - that one drops the ink's
        # thickness, this one shares geometry and skips surface curves.
        ttk.Checkbutton(checks, text="Compact STEP (reuse component geometry)",
                        variable=self.minimize).pack(side="left")
        # Only meaningful with a folder queued: it decides whether the batch
        # includes the whole-board file. Pointed straight at that file, the
        # build happens anyway and the log says so.
        self._full_box = ttk.Checkbutton(
            checks, text="Build the full-board file too",
            variable=self.build_full)
        self._full_box.pack(side="left", padx=(16, 0))

        # --- log ---
        log_frame = ttk.LabelFrame(self, text="Log", padding=4)
        log_frame.grid(row=3, column=0, sticky="nsew", padx=8, pady=4)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        # wrap="word": build messages carry full paths and OCCT errors, which
        # ran off the right edge with no horizontal scrollbar to reach them.
        self.log_view = tk.Text(log_frame, height=10, wrap="word", state="disabled")
        self.log_view.grid(row=0, column=0, sticky="nsew")
        # Named, and skipped by _freeze_inputs, so the log stays readable
        # while the build runs. A ttk.Scrollbar has no -state option and
        # would survive the freeze anyway; the guard is for the day this
        # becomes a tk.Scrollbar, which does.
        self._log_scroll = ttk.Scrollbar(log_frame, command=self.log_view.yview)
        self._log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_view.configure(yscrollcommand=self._log_scroll.set)
        # severity colors: notes blue, warnings orange, errors dark red
        self.log_view.tag_configure("note", foreground="#1f6fb2")
        self.log_view.tag_configure("warning", foreground="#d9791e")
        self.log_view.tag_configure("error", foreground="#8b0000")
        self.log_view.tag_configure("success", foreground="#1a7f2e")

        # --- bottom ---
        bottom = ttk.Frame(self, padding=(8, 4, 8, 8))
        bottom.grid(row=4, column=0, sticky="ew")
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
        self._update_rim_swatch()
        self._update_silk_row()
        # Typing, pasting, Browse and the Allegro prefill all land in this one
        # variable, so one trace covers every way the JSON can change.
        self.json_file.trace_add("write", self._schedule_layer_refresh)
        self._refresh_layers()

    # --------------------------------------------------- window placement -- #

    def _virtual_screen(self) -> tuple[int, int, int, int]:
        """(x, y, w, h) of every monitor - winplace.virtual_screen; a method so a
        test can stand in a different desk."""
        return winplace.virtual_screen(self)

    def _geometry_is_reachable(self, w: int, h: int, x: int, y: int) -> bool:
        return winplace.geometry_is_reachable(self._virtual_screen(), w, h, x, y)

    FIRST_RUN_WIDTH = winplace.FIRST_RUN_WIDTH

    def _center_on_primary(self) -> None:
        winplace.center_on_primary(self, self.FIRST_RUN_WIDTH)

    def _restore_geometry(self) -> None:
        winplace.restore_geometry(
            self, self._saved_geometry, self._saved_state,
            reachable=self._geometry_is_reachable, center=self._center_on_primary,
            on_unreachable=lambda: self.after(200, lambda: self._append_log(
                "The remembered window position is off-screen (a monitor may "
                "have been disconnected); centred on the main screen instead.")))

    def _remember_geometry(self, _event=None) -> None:
        """Keep the last non-maximized geometry. Bound to <Configure>."""
        geometry = winplace.normal_geometry(self)
        if geometry is not None:
            self._last_normal_geometry = geometry

    def _build_board_mode_row(self, parent) -> None:
        """How the board body is built, and the color of each layer kind.

        Both live on one row: the swatches only mean anything in "Layer
        colors", so they are greyed out otherwise rather than hidden - a row
        that appears and disappears makes the window jump.
        """
        row = ttk.Frame(parent)
        row.grid(row=2, column=0, columnspan=6, sticky="w", pady=(6, 0))

        ttk.Label(row, text="Body stitching").pack(side="left")
        box = ttk.Combobox(row, textvariable=self.board_mode,
                           values=[label for _, label in BOARD_MODES],
                           state="readonly", width=21)
        box.pack(side="left", padx=(6, 0))
        box.bind("<<ComboboxSelected>>", lambda e: self._on_mode_changed())

        # The swatches take their own row: on one line with the dropdown they
        # made the group ask for 923 px, which forced the whole window wide.
        row = ttk.Frame(parent)
        row.grid(row=3, column=0, columnspan=6, sticky="w", pady=(4, 0))
        self._swatches: dict[str, tk.Canvas] = {}
        for key, label, _ in LAYER_KINDS:
            if key == "other":            # not a layer anyone sets on purpose
                continue
            cell = ttk.Frame(row)
            cell.pack(side="left", padx=(10, 0))
            canvas = tk.Canvas(cell, **dict(PICKER_SWATCH, width=18, height=18))
            canvas.pack(side="top")
            canvas.bind("<Button-1>", lambda e, k=key: self._pick_layer_color(k))
            ttk.Label(cell, text=label, foreground="#777").pack(side="top")
            self._swatches[key] = canvas

        # Sits at the end of the swatches, so what it resets is unambiguous:
        # these, back to Allegro's own material colors. The board theme and
        # the rim have their own controls and are not touched.
        self._reset_colors_btn = ttk.Button(row, text="Reset colors", width=14,
                                            command=self._reset_layer_colors)
        self._reset_colors_btn.pack(side="left", padx=(12, 0))
        self._update_layer_swatches()

    def _reset_layer_colors(self) -> None:
        self.layer_colors = dict(DEFAULT_LAYER_COLORS)
        self._update_layer_swatches()
        self._append_log("Layer colors reset to the Allegro material defaults")

    def _on_mode_changed(self) -> None:
        """Both the swatches and the rim controls depend on the stitching."""
        self._update_layer_swatches()
        self._update_rim_swatch()

    def _update_layer_swatches(self) -> None:
        # Both "Solid colored layers" and "Not stitched" paint by layer kind;
        # only plain "Solid" ignores these.
        active = _mode_key(self.board_mode.get()) in ("layers", "inspect")
        self._reset_colors_btn.state(["!disabled"] if active else ["disabled"])
        for key, canvas in self._swatches.items():
            rgb = self.layer_colors.get(key, DEFAULT_LAYER_COLORS[key])
            canvas.configure(bg="#%02x%02x%02x" % rgb if active else INACTIVE_SWATCH,
                             relief="raised" if active else "flat",
                             borderwidth=2 if active else 1,
                             cursor="hand2" if active else "")

    def _pick_layer_color(self, kind: str) -> None:
        if self._busy:
            return          # a Canvas cannot be greyed out; see _set_busy
        if _mode_key(self.board_mode.get()) not in ("layers", "inspect"):
            return
        from tkinter import colorchooser

        current = self.layer_colors.get(kind, DEFAULT_LAYER_COLORS[kind])
        rgb, _ = colorchooser.askcolor(
            color="#%02x%02x%02x" % current,
            title=f"Color for {dict((k, l) for k, l, _ in LAYER_KINDS)[kind]}")
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
        self._attach_edit_menu(self._step_text)
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
        entry = ttk.Entry(parent, textvariable=var)
        entry.grid(row=row, column=1, sticky="ew", padx=6, pady=3)
        self._attach_edit_menu(entry)
        ttk.Button(parent, text="Browse...", command=command).grid(
            row=row, column=2, pady=3
        )

    # ---- the right-click menu of a text field (round 78) ------------------ #

    EDIT_MENU = (("Cut", "<<Cut>>"), ("Copy", "<<Copy>>"), ("Paste", "<<Paste>>"),
                 (None, None), ("Select all", "<<SelectAll>>"))

    def _attach_edit_menu(self, widget) -> None:
        """Right-click: Cut / Copy / Paste / Select all. Tk's Entry and Text
        know the keyboard shortcuts but offer no menu of their own on Windows,
        and a path is the one thing everyone pastes."""
        widget.bind("<Button-3>", lambda event, w=widget: self._show_edit_menu(event, w))

    def _edit_menu(self, widget) -> tk.Menu:
        """The menu for *widget*, built fresh: it is four entries, and a menu
        that outlives the click would have to be told when the field is frozen."""
        menu = tk.Menu(self, tearoff=0)
        for label, event in self.EDIT_MENU:
            if label is None:
                menu.add_separator()
                continue
            menu.add_command(label=label,
                             command=lambda w=widget, e=event: (w.focus_set(), w.event_generate(e)))
        return menu

    def _show_edit_menu(self, event, widget) -> None:
        # A frozen field (a build is running) takes no edits, so no menu either;
        # the same rule the swatches follow.
        if self._busy:
            return
        menu = self._edit_menu(widget)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _update_swatch(self) -> None:
        rgb = BOARD_THEMES.get(self.theme.get(), (128, 128, 128))
        self._swatch.configure(bg="#%02x%02x%02x" % rgb)

    def set_theme(self, name: str) -> None:
        """Pick a board colour theme by name, swatch included - what the
        launcher's --color does (round 74, C6)."""
        self.theme.set(name)
        self._update_swatch()

    def _update_rim_swatch(self) -> None:
        # The rim color paints the side walls a different color from the faces,
        # which only means anything when the board IS one uniformly colored
        # solid. The other two stitchings decide every face themselves and
        # ignore it - generate() already says so in the log - so the control
        # greys out rather than sitting there looking live.
        solid = _mode_key(self.board_mode.get()) == "solid"
        self._rim_box.configure(state="readonly" if solid else "disabled")
        active = solid and self.rim_choice.get() == RIM_CUSTOM
        color = INACTIVE_SWATCH
        if active:
            try:
                color = "#%02x%02x%02x" % parse_hex(self.rim_custom.get())
            except ValueError:
                color = "#ffffff"
        self._rim_swatch.configure(bg=color,
                                   relief="raised" if active else "flat",
                                   borderwidth=2 if active else 1,
                                   cursor="hand2" if active else "")

    def _pick_rim_color(self) -> None:
        if self._busy:
            return          # a Canvas cannot be greyed out; see _set_busy
        if (_mode_key(self.board_mode.get()) != "solid"
                or self.rim_choice.get() != RIM_CUSTOM):
            return
        from tkinter import colorchooser

        try:
            current = "#%02x%02x%02x" % parse_hex(self.rim_custom.get())
        except ValueError:
            current = "#ffffff"
        rgb, _ = colorchooser.askcolor(color=current, title="Board edge color")
        if rgb:
            self.rim_custom.set("#%02X%02X%02X" % tuple(int(c) for c in rgb))
            self._update_rim_swatch()

    # ------------------------------------------------------- silk layers -- #

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
        field = self.json_file.get().strip()
        found: dict[str, dict[str, int]] = {}
        if field:
            jobs, _ = core.resolve_jobs(Path(field))
            # Several variants build in one press, so the list is their union:
            # a layer present in any of them is a layer you can switch off.
            for job in jobs:
                for side, counts in job.silkscreen_layers().items():
                    into = found.setdefault(side, {})
                    for layer, n in counts.items():
                        into[layer] = into.get(layer, 0) + n

        self.layers.refresh(found, self._layers_off)
        # A side switched off greys its layers out immediately, not on the next
        # refresh.
        self._update_silk_row()

    def _side_wanted(self, side: str) -> bool:
        return self.silk_top.get() if side == "top" else self.silk_bottom.get()

    def _current_layers_off(self) -> set[str]:
        """Layer names currently unticked."""
        return self.layers.current_layers_off()

    @property
    def _layer_vars(self) -> dict:
        """The panel's tick per layer - what _save_config and the tests read."""
        return self.layers.vars

    @property
    def _layer_rows(self) -> dict:
        return self.layers.rows

    def _update_silk_row(self) -> None:
        """Keep the ink swatch and the enabled state in step with the checkboxes."""
        on = self.silk_top.get() or self.silk_bottom.get()
        # Grey the layers of a side that is off. State only - the variables are
        # untouched, so the ticks come back exactly as they were.
        self.layers.update_sides()
        self.silk_box.configure(state="readonly" if on else "disabled")
        self.silk_flat_check.configure(state="normal" if on else "disabled")
        # With both sides off nothing in this group does anything, so the whole
        # group says so - the same rule the per-side layer greying already
        # follows, applied one level up. State only: no variable is touched, so
        # every tick comes back as it was when a side is switched on again.
        for widget in self._silk_group_widgets:
            try:
                widget.state(["!disabled"] if on else ["disabled"])
            except (AttributeError, tk.TclError):
                pass
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

        Raises ValueError if the custom rim color does not parse, which doubles
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
            build_full_board=self.build_full.get(),
            board_mode=_mode_key(self.board_mode.get()),
            layer_colors=dict(self.layer_colors),
            ignore_soldermask=self.ignore_soldermask.get(),
            fold_bends=self.fold_bends.get(),
            fold_anchor=self.fold_anchor,
            fold_neutral=self.fold_neutral,
            fold_slice_angle=self.fold_slice_angle,
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
            settings = self._snapshot()   # also validates the custom color
        except ValueError as exc:
            messagebox.showerror("Bad color", str(exc))
            return

        self._clear_log()
        self._run_in_worker(settings)

    # ------------------------------------------------------------ plumbing - #

    def _run_in_worker(self, settings: BuildSettings) -> None:
        if self._bridge.alive:
            return
        self._set_busy(True)
        self._bridge.start(settings)

    def _drain_queue(self) -> None:
        # The reschedule sits in a finally, and that is the whole point: this
        # method is the ONLY thing that keeps the loop alive, so anything that
        # escapes it - a Tk error in the log widget, an empty message where a
        # line was expected - would stop the window updating for the rest of the
        # session. The build then finishes invisibly: no log, no progress, no
        # completion. Cheaper to survive the exception than to enumerate them.
        try:
            self._drain_once()
        finally:
            self._drain_job = self.after(100, self._drain_queue)

    def _drain_once(self) -> None:
        self._bridge.drain_once()

    # What the bridge reports, on the Tk thread. Widgets are touched here and
    # nowhere in worker_bridge.py.

    def _on_progress(self, current: int, total: int, status: str | None) -> None:
        self.progress["maximum"] = max(total, 1)
        self.progress["value"] = current
        if status:
            self.status.set(status)

    def _on_done(self, message: str) -> None:
        self._append_log(message, "success")
        self.status.set(message)
        self._set_busy(False)

    def _on_error(self, message: str) -> None:
        self._append_log(message, "error")
        self.status.set("Failed")
        self._set_busy(False)
        # The last line, when there is one: a traceback's last line is the
        # exception itself. An empty message would leave splitlines() with
        # nothing to index.
        lines = message.strip().splitlines()
        messagebox.showerror("StepBuilder", lines[-1] if lines else "The build failed")

    def _on_crash(self, detail: str) -> None:
        """A build that died without saying so - WorkerBridge.check_alive."""
        self._set_busy(False)
        self.status.set("The build crashed")
        self._append_log(detail, "error")
        messagebox.showerror("StepBuilder", detail)

    def _walk(self, parent=None):
        """Every widget in the window, depth first."""
        for child in (parent or self).winfo_children():
            yield child
            yield from self._walk(child)

    def _freeze_inputs(self) -> None:
        """Disable every control for the duration of a build.

        **The previous state of each widget is remembered, not assumed.** Half
        this window is greyed out by its own rules at any moment - the rim color
        outside Solid mode, a side's silkscreen layers when that side is off,
        the layer swatches in Solid - and re-enabling everything afterwards
        would quietly switch those back on. So each widget's own `state` is
        recorded and put back exactly.

        The log stays enabled: a build is precisely when someone wants to read
        and scroll it. The action button stays live too - it is the Cancel
        button while the build runs.

        Freezing twice would record "disabled" as the state to restore and
        leave the window dead after the build. Nothing does that today - a
        second Generate cannot start while a worker is alive - but the cost of
        being sure is one comparison.
        """
        if self._frozen:
            return
        self._frozen = {}
        # A tk.Text refuses edits when disabled but keeps its white field, and
        # a Canvas swatch keeps its colour whatever its state - so both go on
        # looking live while everything around them greys out. They are dimmed
        # by hand, to the same grey the window already uses for a swatch that
        # does not apply, and put back from what was recorded.
        self._dimmed = {}
        for canvas in (self._swatch, self._rim_swatch, self._silk_swatch,
                       *self._swatches.values()):
            self._dimmed[canvas] = {k: canvas.cget(k) for k in
                                    ("bg", "relief", "borderwidth", "cursor")}
            canvas.configure(bg=INACTIVE_SWATCH, relief="flat", borderwidth=1,
                             cursor="")
        # The theme decides what disabled looks like, so ask it rather than
        # inventing a grey that matches this Windows and no other.
        style = ttk.Style(self)
        field = style.lookup("TEntry", "fieldbackground", ["disabled"]) or "#f0f0f0"
        text = style.lookup("TEntry", "foreground", ["disabled"]) or "#6d6d6d"
        self._dimmed[self._step_text] = {k: self._step_text.cget(k)
                                         for k in ("bg", "fg")}
        self._step_text.configure(bg=field, fg=text)
        for widget in self._walk():
            if widget in (self.log_view, self._log_scroll, self.generate_button):
                continue
            try:
                previous = widget.cget("state")
            except Exception:
                continue          # frames, canvases: nothing to disable
            try:
                widget.configure(state="disabled")
            except Exception:
                continue
            # str(): a ttk state comes back as a Tcl object, and putting that
            # back verbatim is fine, but the tests compare against "readonly".
            self._frozen[widget] = str(previous)

    def _thaw_inputs(self) -> None:
        for widget, previous in self._frozen.items():
            try:
                widget.configure(state=previous)
            except Exception:
                pass
        self._frozen = {}
        for widget, options in self._dimmed.items():
            try:
                widget.configure(**options)
            except Exception:
                pass
        self._dimmed = {}

    def _set_busy(self, busy: bool) -> None:
        # The flag is what the click handlers on the color swatches test: a
        # Canvas has no state to disable, so those are guarded rather than
        # greyed - see _pick_rim_color and _pick_layer_color.
        self._busy = busy
        if busy:
            self._freeze_inputs()
            # One button, two jobs. A build takes minutes on a real board, so
            # leaving no way out of it is not an option; and a Cancel that sits
            # beside a live-looking Generate would be the second confusing
            # thing. The label says which one it is.
            self.generate_button.configure(text="Cancel", command=self.on_cancel)
            self.status.set("Working...")
            self.progress["value"] = 0
        else:
            self._thaw_inputs()
            self.generate_button.configure(text="Generate", command=self.on_generate)

    def on_cancel(self) -> None:
        """Stop the running build.

        The build is a child PROCESS, so this is a real kill rather than a
        polite request - which is the only thing that works: OCCT spends
        minutes inside a single boolean and nothing checks a flag in there.

        What it costs is said out loud: the file being written at that moment
        can be left half finished, and a half-written STEP is not obviously
        broken when you open it.
        """
        if not self._bridge.alive:
            return
        self._append_log("Cancelled. Any file being written just now may be "
                         "incomplete - check its size, or build it again.",
                         "warning")
        self._bridge.cancel()
        self._set_busy(False)
        self.status.set("Cancelled")

    def _append_log(self, message: str, severity: str | None = None) -> None:
        # Auto-detect severity from the message if not given, so plain "log"
        # queue items are colored too.
        if severity is None:
            low = message.lstrip().lower()
            if low.startswith(ERROR_PREFIXES):
                severity = "error"
            elif low.startswith(WARNING_PREFIXES):
                severity = "warning"
            elif low.startswith(NOTE_PREFIXES):
                severity = "note"
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

    @property
    def local_config_path(self) -> Path:
        """The local file beside the tracked one - settings.local_config_path."""
        return settings.local_config_path(self.config_path)

    def _load_config(self) -> None:
        """The pair, merged and decoded by settings.load_gui_settings; here only
        the hand-over into the widgets. Runs BEFORE _build_ui, so the STEP
        folders buffer in set_step_dirs until their widget exists."""
        s, self._config_problem, self._local_problem = \
            settings.load_gui_settings(self.config_path)
        self.set_step_dirs(s.step_dirs)
        self.json_file.set(s.json_file)
        self.output_dir.set(s.output_dir)
        self.z_datum.set(s.z_datum)
        self.theme.set(s.theme)
        self.rim_choice.set(s.rim_choice)
        self.rim_custom.set(s.rim_custom)
        self.silk_top.set(s.silk_top)
        self.silk_bottom.set(s.silk_bottom)
        self.silk_color.set(s.silk_color)
        self.silk_flat.set(s.silk_flat)
        self._layers_off = s.layers_off
        self.silk_flat_height = s.silk_flat_height
        self.minimize.set(s.minimize)
        self.build_full.set(s.build_full)
        self.board_mode.set(_mode_label(s.board_mode))
        self.layer_colors = dict(s.layer_colors)
        self.ignore_soldermask.set(s.ignore_soldermask)
        self.fold_bends.set(s.fold_bends)
        self.fold_anchor = s.fold_anchor
        self.fold_neutral = s.fold_neutral
        self.fold_slice_angle = s.fold_slice_angle
        self._saved_geometry = s.window_geometry
        self._saved_state = s.window_state

    def _save_config(self) -> None:
        """Write the "gui" section into the LOCAL settings file.

        What the widgets hold, handed to settings.save_gui_settings, which
        owns the rules: the tracked file is never written, nothing is written
        unless both files were understood at load AND the local one reads
        cleanly now, only what differs from the shipped default is kept, and
        the paths Allegro supplied are not a setting. Why each of those is a
        rule is said there.
        """
        values = settings.GuiSettings(
            step_dirs=self.step_dirs(),
            z_datum=self.z_datum.get(),
            theme=self.theme.get(),
            rim_choice=self.rim_choice.get(),
            rim_custom=self.rim_custom.get(),
            silk_top=self.silk_top.get(),
            silk_bottom=self.silk_bottom.get(),
            silk_color=self.silk_color.get(),
            silk_flat=self.silk_flat.get(),
            silk_flat_height=self.silk_flat_height,
            # Only overwrite the remembered exclusions once a list has actually
            # been shown; an old JSON with no layers must not wipe them.
            layers_off=set(self._current_layers_off() if self._layer_vars
                           else self._layers_off),
            minimize=self.minimize.get(),
            build_full=self.build_full.get(),
            board_mode=_mode_key(self.board_mode.get()),
            layer_colors=dict(self.layer_colors),
            ignore_soldermask=self.ignore_soldermask.get(),
            fold_bends=self.fold_bends.get(),
            fold_anchor=self.fold_anchor,
            fold_neutral=self.fold_neutral,
            fold_slice_angle=self.fold_slice_angle,
            # The NON-maximized rect is stored even when closing maximized, so
            # un-maximizing later gives back a sane window.
            window_geometry=self._last_normal_geometry or self.geometry(),
            window_state="zoomed" if self.state() == "zoomed" else "normal",
            json_file=self.json_file.get(),
            output_dir=self.output_dir.get(),
        )
        settings.save_gui_settings(
            self.config_path, values,
            paths_from_launcher=self._paths_from_launcher,
            loaded_cleanly=(self._config_problem is None
                            and self._local_problem is None))

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
        # A build outlives its window otherwise: the child is a process now, and
        # closing the window while one is running would leave it grinding away
        # on a file nobody is waiting for.
        self._bridge.close()
        self.destroy()


def main(config_path: Path | None = None) -> None:
    StepBuilderApp(config_path).mainloop()
