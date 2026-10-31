"""The silkscreen layer panel: a scrolled Top/Bottom list of checkboxes.

Checkbuttons, not a multi-select Listbox: a highlighted row reads as
"current item", a tick reads as "included", and included is the question.
The list is built from the JSON that will actually be built, so it can
never offer a layer that would do nothing, and each row carries its polygon
count - that is what explains a large file. Round 74, plan C4: the panel
out of the window, behaviour for behaviour (test_gui [7f]).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..build import SILK_SOURCES, legend_layers


class LayersPanel(ttk.LabelFrame):
    """The panel. `vars` is the tick per layer, `rows` the (layer, var, box)
    triples per side, `buttons` the All/None pair and the two legend-source
    choices (the window greys them with the rest of the silk group).
    *side_wanted* says whether a side is on; *source* holds where the legend
    comes from (build.SILK_SOURCES), *on_source* is called when it changes."""

    def __init__(self, master, *, side_wanted: Callable[[str], bool],
                 source: tk.StringVar | None = None,
                 on_source: Callable[[], None] | None = None, **kw) -> None:
        super().__init__(master, text="Layers", padding=4, **kw)
        self._side_wanted = side_wanted
        self.source = source if source is not None else tk.StringVar(value=SILK_SOURCES[0])
        self.vars: dict[str, tk.BooleanVar] = {}
        # Which side each checkbox belongs to, so switching a side off can grey
        # its layers out WITHOUT changing them - the ticks are still what gets
        # saved and what applies again when the side comes back.
        self.rows: dict[str, list] = {"top": [], "bottom": []}
        self.columnconfigure(0, weight=1)

        self._canvas = tk.Canvas(self, height=96, highlightthickness=0)
        self._canvas.grid(row=0, column=0, sticky="ew")
        scroll = ttk.Scrollbar(self, orient="vertical",
                                      command=self._canvas.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self._canvas.configure(yscrollcommand=scroll.set)
        self._inner = ttk.Frame(self._canvas)
        self._window = self._canvas.create_window(
            (0, 0), window=self._inner, anchor="nw")
        self._inner.bind(
            "<Configure>",
            lambda e: self._canvas.configure(
                scrollregion=self._canvas.bbox("all")))
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfigure(self._window,
                                                        width=e.width))

        # The wheel over the panel must scroll it. Binding the canvas alone is
        # not enough: the pointer is nearly always over a Checkbutton or the
        # inner frame, and those consume the event, so the wheel only worked on
        # the scrollbar itself. Binding every child is worse - the list is
        # rebuilt constantly. So grab the wheel while the pointer is inside the
        # panel and release it on the way out, which leaves the wheel alone
        # everywhere else in the window.
        self._canvas.bind("<Enter>", self.grab_wheel)
        self._canvas.bind("<Leave>", self.release_wheel)

        layer_buttons = ttk.Frame(self)
        layer_buttons.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        all_btn = ttk.Button(layer_buttons, text="All", width=6,
                             command=lambda: self.set_all(True))
        all_btn.pack(side="left")
        none_btn = ttk.Button(layer_buttons, text="None", width=6,
                              command=lambda: self.set_all(False))
        none_btn.pack(side="left", padx=(4, 0))
        # Where the legend comes from: the layers as drawn, or Allegro's
        # AUTOSILK copy of them (Auto Silkscreen, trimmed at the pads) - one or
        # the other, as Allegro's own 3D Canvas offers it; together they are
        # the legend twice (review 23.10.2026, R2-7). On the All/None row, not
        # a row of its own: the window has no height to spare.
        ttk.Label(layer_buttons, text="Legend from").pack(side="left", padx=(12, 4))
        drawn_btn = ttk.Radiobutton(layer_buttons, text="drawn layers", value=SILK_SOURCES[0],
                                    variable=self.source, command=on_source)
        drawn_btn.pack(side="left")
        auto_btn = ttk.Radiobutton(layer_buttons, text="AUTOSILK", value=SILK_SOURCES[1],
                                   variable=self.source, command=on_source)
        auto_btn.pack(side="left", padx=(4, 0))
        self.source_buttons = [drawn_btn, auto_btn]
        self.buttons = [all_btn, none_btn, *self.source_buttons]


    def refresh(self, found: dict[str, dict[str, int]], layers_off: set[str]) -> None:
        """Redraw for *found* ({side: {layer: polygon count}}), keeping the
        ticks already set; a layer in *layers_off* that is new here starts
        unticked, any other new layer ticked."""
        for child in self._inner.winfo_children():
            child.destroy()

        if not found:
            # grid, like the side columns below: pack and grid cannot both
            # manage children of one container, and this label shares
            # _layers_inner with them.
            ttk.Label(self._inner, foreground="#777",
                      text="No layer information in this JSON — the whole "
                           "legend is built. Re-export to choose layers.").grid(
                row=0, column=0, sticky="w", padx=4, pady=2)
            self.vars = {}
            self.rows = {"top": [], "bottom": []}
            return

        # Keep the ticks the user already set for layers that are still here,
        # so a refresh does not undo a selection.
        previous = {name: var.get() for name, var in self.vars.items()}
        self.vars = {}

        # Side by side, not stacked: a board's two sides rarely have many
        # layers each, so two short columns fit where one long list would
        # scroll, and the sides stay comparable at a glance. Columns are
        # allocated only to sides that have layers, so a top-only board does
        # not leave a gap where Bottom would have been.
        self.rows = {"top": [], "bottom": []}
        column = 0
        for side in ("top", "bottom"):
            if side not in found:
                continue
            side_frame = ttk.Frame(self._inner)
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
                state = previous.get(layer, layer not in layers_off)
                var = tk.BooleanVar(value=state)
                self.vars[layer] = var
                box = ttk.Checkbutton(
                    side_frame, variable=var,
                    text=f"{layer}   ({found[side][layer]})",
                )
                box.pack(anchor="w", padx=(16, 4))
                self.rows[side].append((layer, var, box))


    def current_layers_off(self) -> set[str]:
        """Layer names currently unticked."""
        return {name for name, var in self.vars.items() if not var.get()}

    def update_sides(self) -> None:
        """Grey the rows of a side that is off, and the rows the legend source
        leaves out on a side that is on - AUTOSILK under "drawn layers", the
        drawn layers under "AUTOSILK" where the side has one. State only - the
        variables are untouched, so the ticks come back exactly as they were."""
        for side, rows in self.rows.items():
            used = legend_layers((layer for layer, _var, _box in rows), self.source.get())
            on = self._side_wanted(side)
            for layer, _var, box in rows:
                box.configure(state="normal" if on and layer in used else "disabled")

    def set_all(self, state: bool) -> None:
        """All / None, but only for sides that are switched on.

        A greyed-out side keeps its ticks, and so does a row the legend source
        leaves out. Changing them from here would edit a selection whose effect
        is not visible, and it is that same selection which gets saved to the
        config.
        """
        for side, rows in self.rows.items():
            if not self._side_wanted(side):
                continue
            used = legend_layers((layer for layer, _var, _box in rows), self.source.get())
            for layer, var, _box in rows:
                if layer in used:
                    var.set(state)


    def grab_wheel(self, _event=None) -> None:
        """Route the wheel to this panel while the pointer is over it."""
        self.bind_all("<MouseWheel>", self._on_wheel)
        # X11 reports the wheel as buttons 4 and 5; harmless on Windows.
        self.bind_all("<Button-4>", self._on_wheel)
        self.bind_all("<Button-5>", self._on_wheel)

    def release_wheel(self, _event=None) -> None:
        self.unbind_all("<MouseWheel>")
        self.unbind_all("<Button-4>")
        self.unbind_all("<Button-5>")

    def _on_wheel(self, event) -> None:
        # Nothing to scroll when the list already fits: without this the canvas
        # rubber-bands the content out of view on a short list.
        region = self._canvas.bbox("all")
        if not region or region[3] - region[1] <= self._canvas.winfo_height():
            return
        if getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        else:
            step = -1 if event.delta > 0 else 1
        self._canvas.yview_scroll(step, "units")
