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
import queue
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import core
from .colors import BOARD_THEMES, CREAM_DIELECTRIC, DEFAULT_THEME, THEME_ORDER, resolve_board_color

CONFIG_PATH = Path.home() / ".stepbuilder.json"

RIM_SAME = "Same as board"
RIM_CREAM = "Cream (dielectric)"
RIM_CUSTOM = "Custom..."


class StepBuilderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Simple 3D - StepBuilder")
        self.minsize(760, 560)

        self._queue: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None

        self.step_dir = tk.StringVar()
        self.json_file = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.status = tk.StringVar(value="Ready")

        self.z_datum = tk.StringVar(value="top")
        self.theme = tk.StringVar(value=DEFAULT_THEME)
        self.rim_choice = tk.StringVar(value=RIM_SAME)
        self.rim_custom = tk.StringVar(value="")
        # MFRPN DISABLED (property attachment unreliable); kept for future:
        # self.mfr_pn_in_name = tk.BooleanVar(value=False)
        self.minimize = tk.BooleanVar(value=True)

        # Prefill state, set by prefill_jobs() when launched from Allegro.
        # Note: there is deliberately NO cached job list - jobs are resolved
        # from the JSON field at Generate time (see _generate).
        self._brd_name: str | None = None      # base name for dated output
        self._dated_name: bool = False

        self._load_config()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_queue)

    # ----------------------------------------------------------------- UI -- #

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # --- paths ---
        paths = ttk.LabelFrame(self, text="Input", padding=8)
        paths.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        paths.columnconfigure(1, weight=1)
        self._path_row(paths, 0, "STEP files", self.step_dir, self._pick_step_dir)
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

        ttk.Label(opts, text="Board edge").grid(row=0, column=3, sticky="e", padx=(12, 6))
        rim_box = ttk.Combobox(
            opts, textvariable=self.rim_choice,
            values=[RIM_SAME, RIM_CREAM, RIM_CUSTOM], state="readonly", width=18
        )
        rim_box.grid(row=0, column=4, sticky="w")
        rim_box.bind("<<ComboboxSelected>>", lambda e: self._update_rim_entry())
        self.rim_entry = ttk.Entry(opts, textvariable=self.rim_custom, width=12)
        self.rim_entry.grid(row=1, column=4, sticky="w", pady=(2, 0))

        ttk.Label(opts, text="Z = 0 at").grid(row=1, column=0, sticky="w", pady=3)
        zrow = ttk.Frame(opts)
        zrow.grid(row=1, column=1, columnspan=2, sticky="w")
        ttk.Radiobutton(zrow, text="Top of board", variable=self.z_datum,
                        value="top").pack(side="left")
        ttk.Radiobutton(zrow, text="Bottom of board", variable=self.z_datum,
                        value="bottom").pack(side="left", padx=(10, 0))

        checks = ttk.Frame(opts)
        checks.grid(row=2, column=0, columnspan=5, sticky="w", pady=(6, 0))
        # MFRPN DISABLED (property attachment unreliable); kept for future:
        # ttk.Checkbutton(checks, text="Append MFRPN to instance names",
        #                 variable=self.mfr_pn_in_name).pack(side="left")
        ttk.Checkbutton(checks, text="Minimise file size",
                        variable=self.minimize).pack(side="left")

        # --- log ---
        log_frame = ttk.LabelFrame(self, text="Log", padding=4)
        log_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_view = tk.Text(log_frame, height=10, wrap="none", state="disabled")
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

    def _build_actions(self) -> None:
        """All action buttons live here. Add new ones alongside Generate."""
        self.generate_button = ttk.Button(
            self._actions, text="Generate", command=self.on_generate
        )
        self.generate_button.pack(side="left", padx=4)

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
        state = "normal" if self.rim_choice.get() == RIM_CUSTOM else "disabled"
        self.rim_entry.configure(state=state)

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
        if path := filedialog.askdirectory(title="Directory with footprint STEP files"):
            self.step_dir.set(path)

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

    def on_generate(self) -> None:
        if not self.step_dir.get() or not self.json_file.get() or not self.output_dir.get():
            messagebox.showwarning(
                "Missing input", "Please set the STEP directory, JSON file and output directory."
            )
            return
        try:
            self._rim_color()  # validate custom colour early
        except ValueError as exc:
            messagebox.showerror("Bad colour", str(exc))
            return

        self._clear_log()
        self._run_in_worker(self._generate)

    def _generate(self) -> None:
        """Runs on the worker thread. Builds one or many JSONs.

        The job list is resolved HERE, from the JSON field as it is right now -
        never from a cached queue. This way, browsing to a different file after
        an Allegro prefill builds exactly what the field shows.
        """
        field = Path(self.json_file.get())
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
        for jf in jobs:
            # Base name for the output file. With SEVERAL variants the stem of
            # each json (design_variant) must win, or every variant would get
            # the same name and only differ by collision underscores. The
            # launcher's brd_name (original-case board name) applies only when
            # there is a single json.
            if len(jobs) > 1:
                base = jf.stem
            else:
                base = self._brd_name or jf.stem
            output_name = (core.dated_output_name(base, self.output_dir.get())
                           if self._dated_name else None)
            result = core.generate(
                self.step_dir.get(),
                jf,
                self.output_dir.get(),
                output_name=output_name,
                z_datum=self.z_datum.get(),
                board_color=BOARD_THEMES.get(self.theme.get()),
                rim_color=self._rim_color(),
                # MFRPN DISABLED (kept for future): name_instances_with_mfr_pn=self.mfr_pn_in_name.get(),
                minimize_size=self.minimize.get(),
                log=lambda m: self._queue.put(("log", m)),
                progress=lambda i, n: self._queue.put(("progress", (i, n))),
            )
            total_placed += result.components_placed
            outputs.append(result.output.name)
            if result.missing_step_files:
                warnings.append(f"{result.output.name}: {len(result.missing_step_files)} STEP missing")
            # MFRPN DISABLED (kept for future):
            # if result.missing_mfr_pn:
            #     warnings.append(f"{result.output.name}: {len(result.missing_mfr_pn)} without MFRPN")

        summary = f"Done: {len(outputs)} file(s), {total_placed} component(s) placed"
        for w in warnings:
            self._queue.put(("log", "warning: " + w))
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
        self.after(100, self._drain_queue)

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
            if low.startswith("error") or low.startswith("traceback"):
                severity = "error"
            elif low.startswith("warning") or low.startswith("ignored") or low.startswith("ignoring"):
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

    def _load_config(self) -> None:
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self.step_dir.set(cfg.get("step_dir", ""))
        self.json_file.set(cfg.get("json_file", ""))
        self.output_dir.set(cfg.get("output_dir", ""))
        self.z_datum.set(cfg.get("z_datum", "top"))
        self.theme.set(cfg.get("theme", DEFAULT_THEME))
        # MFRPN DISABLED (kept for future):
        # self.mfr_pn_in_name.set(cfg.get("mfr_pn_in_name", False))
        self.minimize.set(cfg.get("minimize", True))

    def _save_config(self) -> None:
        try:
            CONFIG_PATH.write_text(
                json.dumps(
                    {
                        "step_dir": self.step_dir.get(),
                        "json_file": self.json_file.get(),
                        "output_dir": self.output_dir.get(),
                        "z_datum": self.z_datum.get(),
                        "theme": self.theme.get(),
                        # MFRPN DISABLED (kept for future):
                        # "mfr_pn_in_name": self.mfr_pn_in_name.get(),
                        "minimize": self.minimize.get(),
                    },
                    indent=1,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _on_close(self) -> None:
        self._save_config()
        self.destroy()


def main() -> None:
    StepBuilderApp().mainloop()
