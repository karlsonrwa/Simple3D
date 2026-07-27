# Simple 3D — Allegro → STEP exporter

*[English](#english) · [Русский](#русский)*

---

<a name="english"></a>
# English

# ⚠️ Disclaimer

Everything in this repository has been created through vibe coding with Claude.
I am not a professional software developer. My background is in hardware engineering, and this project exists solely because I wanted to solve problems I encountered in my own workflow.
I am not proficient in either Python or SKILL. Instead, I focus on clearly defining the behavior I expect from the tool and iteratively refining it until it does what I need.
If you find a bug, an issue, or have an idea for improvement, please feel free to open an Issue or submit a Pull Request. I will do my best to investigate and fix it, but I cannot promise a quick response.
Although this project was developed using an AI-assisted workflow, I make an effort to validate the generated code in real-world use and rely on this tool in my own projects.

## Why this exists

Allegro PCB Editor ships a native 3D STEP export (`File → Export → 3D`), but it
is heavyweight: it pulls the full MCAD bridge, produces large files, and needs
the component models mapped through the full 3D workflow. For quick mechanical
checks — "does this board fit the enclosure", "do these tall parts clash" — that
is more than you want.

**Simple 3D** is a lightweight alternative. It exports the board outline (with
cutouts and holes) plus the placed component STEP models into a single STEP
assembly, driven from a small menu item and a Python GUI. It is deliberately
minimal: one board solid at the true finished thickness, component models reused
so the file stays small, and a flat assembly tree that imports cleanly into
SolidWorks, Inventor, or Creo.

It grew out of the open-source `exportStep` project by juulsA
(https://github.com/juulsA/exportStep), whose SKILL exporter and OpenCASCADE
STEP builder are the foundation here. The C++ builder was ported to Python
(same OpenCASCADE kernel, no compiler or DLLs needed), a number of bugs were
fixed, and the mechanical-engineering features below were added.

## How it works

```
File → Export → Simple 3D   (simple3d.il, inside Allegro)
   │  1. finds the design's  rev/cad  folder (sibling of  rev/pcb )
   │  2. runs the fixed makeVariant3dIntermediates -> one JSON per variant
   │     into  cad , tagged  "format": "simple3d"
   │  3. checks that Python can actually start, and says so if it cannot
   └─ 4. launches the Python GUI with the paths prefilled
            │  reads the tagged JSON(s), builds the STEP
            └─ <board>_simple_DD_MM_YYYY.step
```

Allegro's own progress form is on screen from the moment you press Export and
names each of those stages, because all of it happens before any window of ours
appears. Nothing temporary is written next to your board.

The two halves communicate through an intermediate JSON file: SKILL can read the
Allegro database but not build B-rep/STEP; OpenCASCADE can build STEP but knows
nothing about Allegro. The JSON is that boundary.

## Installation

### 1. Python (3.10 or newer)

Install from https://www.python.org/downloads/ . During install tick **"Add
Python to PATH"**. `tkinter` (the GUI toolkit) is included in the standard
Windows installer — nothing extra to install there.

### 2. The one Python dependency

Open a normal `cmd` window and run:

```
pip install cadquery-ocp
```

`cadquery-ocp` is the OpenCASCADE geometry kernel with Python bindings. It is
the only thing you install, and it is the entire `requirements.txt` — but it is
not small: it declares VTK as a hard dependency, so the three of them together
come to **about 470 MB on disk** (measured: 91 MB of bindings, 63 MB of OCCT
libraries, ~315 MB of VTK).

### 3. The files

Clone the repository, or download and unpack it. **Its root already is the
layout below** — nothing has to be assembled by hand:

```
d:\Projects\OrCAD\Scripts\Simple3D\        ← ONE folder holds the whole tool
├── makeVariant3dIntermediates.il          ← SKILL exporter (fixes folded in)
├── simple3d.il                            ← the menu item + launcher
├── simple3d_config.json                   ← ALL settings: paths, GUI, silkscreen layers
├── stepbuilder\                           ← the Python package
│   ├── __main__.py
│   ├── core.py
│   ├── bend.py
│   ├── worker.py
│   ├── colors.py
│   └── gui.py
├── demo\                                  ← sample board + reference JSON/STEP (optional)
├── tests\, tools\                         ← the test suite and the SKILL checks (optional)
├── PROJECT_NOTES_simple3d.md              ← development memo, not needed to run
├── README.md
├── QUICKSTART.md
└── LICENSE
```

The folder may be called anything and live anywhere; what matters is that
`S3D_ScriptDir` and the two `load()` lines all name **the folder that holds the
two `.il` files**.

The one thing to watch for: downloading the repository as a ZIP from GitHub
wraps everything in an extra folder (`Simple3D-main\`). Either unpack its
*contents* into your Simple 3D folder, or point `S3D_ScriptDir` at the wrapper
itself — but do not leave the two disagreeing.

Verify from a `cmd`:

```
cd /d d:\Projects\OrCAD\Scripts\Simple3D
python -m stepbuilder
```

If the window opens and its log says `Settings loaded from …`, both the package
and the config are where they should be.

### 4. Load the SKILL files in Allegro

Add these to your `allegro.ilinit` (or load them manually each session):

```
load("d:/Projects/OrCAD/Scripts/Simple3D/makeVariant3dIntermediates.il")
load("d:/Projects/OrCAD/Scripts/Simple3D/simple3d.il")
```

`File → Export → Simple 3D` now appears.

## Settings — all in `simple3d_config.json`

Every setting lives in one file, `simple3d_config.json`, next to the two `.il`
files. Both halves of the tool read it: the SKILL side takes the `allegro`
section, the GUI takes `gui`, and the exporter takes `silkscreen` and
`settings`. The GUI writes the `gui` section back when you close the window, so
whatever you last typed into it is what the next run starts with — and the rest
of the file is left untouched.

If the file cannot be read — missing, or edited into invalid JSON — the GUI
loads nothing and **writes nothing for the rest of that session**, leaving your
file exactly as it is even if you repair it while the window is open. The
fields on screen are defaults at that point, not your settings, and writing
them back would overwrite the file you just fixed. It says so in its log. The line naming the settings file appears on every start:

```
Settings loaded from d:/Projects/OrCAD/Scripts/Simple3D/simple3d_config.json
```

so when a field comes up unexpectedly empty, the log says which file was read
and whether it parsed. A byte-order mark left by an editor is tolerated.

| Section | Key | What it does |
|---|---|---|
| `allegro` | `python` | Python executable. `"python"` if on PATH, else a full path like `"c:/Python312/python.exe"`. |
| | `pythonw` | Console-less launcher (`pythonw.exe`). When set, the GUI opens with **no console window**. `""` uses `python` instead. |
| | `menuLabel` / `commandName` | Menu item text and internal command name. Read at load time, so changing them needs a SKILL reload. |
| `gui` | `stepDirs` | Folders holding the footprint STEP models (referenced by `PKGDEF_STEP_FILE`) — the "STEP files" field. A **list, searched in order: the first folder holding a given model file wins**, so a project-local folder listed above the shared library overrides individual models. Each is searched recursively, so subfolders need no entry. |
| | `outputDir`, `jsonFile` | The last paths you picked **in the GUI**. An export launched from Allegro fills these fields for the board being built but does not record them here — they describe a board, not a preference. |
| | `boardMode` | How the board body is built on a **multi-stackup / rigid-flex** design; ignored on an ordinary board. `solid` — one solid in one color, coplanar faces merged, smallest file. `layers` — one solid whose layer interfaces are **kept**, so every face is colored by the kind of layer it belongs to and the rim shows the stack (about 4.7x `solid`). `inspect` — every layer of every zone as its own named part, for taking the board apart by eye. GUI: the **Body stitching** dropdown; CLI: `--board-mode`. |
| | `layerColors` | Color per kind of stackup layer (`copper`, `base`, `coverlay`, `adhesive`, `stiffener`, `soldermask`, `other`), used by `boardMode: layers` and `inspect`. Defaults are **Allegro's own material colors**, taken from a board's `3DX_APPEARANCE`, so the export looks like the same board does in Allegro's 3D canvas. Set them from the swatch row under **Body stitching**, or by hand as `#RRGGBB`. |
| | `ignoreSoldermask` | Leave the soldermask out of the board entirely, however the design defines it, and **close the stack up toward the core** by exactly the thickness removed — each side independently. Components then rest on the copper rather than on the mask. Applies to a multi-stackup board's layers and to a plain board's `soldermask_top`/`soldermask_bottom` alike. GUI: *Do not include soldermask layers*; CLI: `--ignore-soldermask`. Decided when the model is built, so it needs no re-export. |
| | `foldBends` | Fold the board along the **bend areas** defined in Allegro (*Setup – Bend*), so a flex tail is modelled where it ends up instead of flat. The board, the legend and the components all move together. `false` exports it flat, the way Allegro holds it. A design with no bend areas is unaffected either way. GUI: *Fold flex bends*; CLI: `--flat` turns it off. Decided when the model is built, so it needs no re-export. |
| | `foldAnchor` | The point of the board that **stays in the XY plane**, as `[x, y]`. **The origin, `[0, 0]`, by convention** — see *Folding flex bends*. It only decides which side of each bend line is held, so it need not be inside the outline. `"auto"` holds the largest piece the bend lines leave instead. CLI: `--fold-anchor X,Y|auto`. |
| | `foldNeutral` | Where the neutral axis sits in the stack, as a fraction of thickness from the inner surface (default `0.5`, the middle). This is what decides how much flat material a bend consumes: `angle × (radius + k × thickness)`. **Set it to `0` on a board whose bend areas touch** — Allegro lays the flat pattern out at `k = 0`; see *Folding flex bends*. CLI: `--fold-neutral K`. |
| | `foldSliceAngle` | Degrees of arc per slice for a bend that has to be **faceted** — which happens only when neither exact construction fits, and the log then names the bend and the reason. Default `7.5`. Bends built as true cylinders ignore it. CLI: `--fold-slice-angle DEG`. |
| | `windowGeometry`, `windowState` | Where the window was when it was last closed (`WIDTHxHEIGHT+X+Y`) and whether it was maximized. Restored on the next run, so on a multi-monitor desk it comes back **on the same screen** — `X` is negative for a monitor left of the primary. If that position is no longer reachable (usually the monitor was disconnected) it is ignored, the window is centred on the main screen and the log says so. Empty on a first run, which also centres it. |
| | `boardColor`, `boardEdge`, `boardEdgeCustom` | Board and rim color. |
| | `zDatum` | `"top"` or `"bottom"`. |
| | `silkscreenTop`, `silkscreenBottom` | Which sides of the legend to build. |
| | `silkColor`, `silkscreenFlat` | Ink color, and flat or solid. |
| | `silkscreenLayersOff` | Layers currently unticked in the GUI. Exclusions, not inclusions: a layer that turns up on a board for the first time is drawn, rather than silently missing. |
| | `silkscreenFlatHeight` | Distance in mm from the board surface to a **flat** legend, so the two are not coplanar and do not flicker. Default `0.001` (1 µm). Not the ink thickness — that is `settings.silkscreenThickness`, and it applies to solid mode only. |
| | `minimizeFileSize` | See *Silkscreen file size*. |
| `settings` | `negativeLayers` | Stackup layers whose drawn shapes are **openings** rather than material, matched as a case-insensitive substring of the layer name or its IPC function. Coverlay, soldermask and pastemask are drawn that way by convention; stiffener, adhesive and epoxy are the opposite. Add a layer here if its bodies come out inverted in the inspection build. |
| `silkscreen`, `settings` | | Silkscreen layers and ink settings — see *Silkscreen*. |

Two keys are **read but never written**, so that a config from an older build
keeps working: `stepDir` (one folder, superseded by the `stepDirs` list) and
`debugLayers` (a boolean meaning "inspect", superseded by `boardMode`). Each is
migrated on load and dropped on save. Do not add them by hand — `stepDirs` and
`boardMode` always win.

### The one setting still in `simple3d.il`

`S3D_ScriptDir` — the project folder. The config file is found relative to it,
so it has to be known before the config can be read; that bootstrap is the whole
reason it stays in source. Set it to wherever you unpacked the project (the same
folder the two `load()` lines use). `S3D_ConfigFile` sits beside it and only
needs changing if you deliberately keep the config somewhere else.

## The GUI

| Control | Purpose |
|---|---|
| **STEP files** | Folders with the footprint STEP models, **one per line** (`gui.stepDirs`). Searched in order — the first folder holding a model file wins, so a project-local folder above the shared library overrides individual models. Each is searched recursively. **Add...** appends a folder; reorder by editing the text. A name found in more than one folder is reported in the log with the path that won. |
| **JSON file** | The intermediate JSON, or a folder of variant JSONs. Only files tagged `"format": "simple3d"` are used; others are ignored and logged. |
| **Output** | Where the `.step` is written (the `cad` folder). |
| **Board color** | The eight Allegro 3D-canvas themes, with a color swatch. |
| **Board edge color** | Rim / side-wall color: same as board, cream dielectric, or a custom one from the picker. Only *Solid* has one uniformly colored body to contrast with, so the control greys out in the other two stitchings and the log says the color was ignored. |
| **Z = 0 at** | Which board face is the datum: top or bottom. Parts sit on the soldermask of their side (real pads carry solder that lifts the part to mask level). |
| **Body stitching** | How the board body is built — *Solid*, *Solid colored layers*, *Not stitched* (`gui.boardMode`). Multi-stackup and rigid-flex boards only; an ordinary board is one solid whatever this says. The swatch row under it sets the color of each layer kind and applies to the last two; **Reset colors** puts Allegro's own material colors back. Both are greyed out in *Solid*. |
| **Do not include soldermask layers** | Leave the mask out of the board and close the stack up toward the core by what was removed (`gui.ignoreSoldermask`). The board really does get thinner — the label says *check total thickness* for that reason. |
| **Silkscreen: Top / Bottom** | Which sides of the printed legend to build. Both off skips silkscreen entirely, makes a noticeably smaller file, and greys the rest of the group. |
| **Color** (same row) | Silkscreen ink: **White** or **Black**. Those are the two colors legend ink actually comes in, so it is a closed choice. |
| **Make surface (minimum file size)** | Draw the legend as surfaces instead of thin solids: about a quarter of the silkscreen's file size. Their height above the board is `gui.silkscreenFlatHeight`. See *Silkscreen file size* below. |
| **Silkscreen layers** | A tick per layer found in the loaded JSON, with its polygon count, the two sides side by side. Untick a layer to leave it out of this build — no re-export needed. **All** / **None** set them together, skipping a side that is switched off. |
| **Fold flex bends** | Fold the board along its bend areas (see *Folding flex bends*). On by default; unticking it exports the board flat. Does nothing on a board with no bend areas. |
| **Compact STEP (reuse component geometry)** | Drops parametric surface curves (`write.surfacecurve.mode = 0`), roughly halving the file with identical geometry. |
| **Generate** | Builds one file, or every queued variant. |

Log messages are color-coded: **orange** for warnings, **dark red** for errors,
green for success. The progress bar follows the whole build — reading, the
board, the legend, components, writing — and the line beside it says which.

**The build runs in a child process.** OpenCASCADE can die outright rather than
raise, and a boolean over a difficult board occasionally does; in a thread that
would close this window with nothing written anywhere. Instead the window
reports the exit code and what usually gets a board through: *Not stitched*,
which fuses nothing, or a coarser `gui.foldSliceAngle`.

The Allegro console is color-coded too. Messages go through `axlUIWPrint` with
a severity, so warnings appear in Allegro's warning color and errors in red,
carrying the same `*WARNING*` / `*Error*` prefixes as Allegro's own messages.
There is no green: the documented severities are `info0`, `info1`, `warn`,
`error` and `fatal`, and none of them means success, so a completed export
prints in the ordinary color. The GUI log is where a successful build shows
green.

## Assembly structure

```
<board_name>
├── PCB_<board>             one solid at the finished thickness
├── silkscreen_top_<board>  printed legend, top    (only if enabled and present)
├── silkscreen_bot_<board>  printed legend, bottom
├── symbols_top             top-side components
│   ├── cap_D8x10mm         part, named after its STEP file, placed in situ
│   └── cap_D8x10mm         the same part instanced again if the model repeats
└── symbols_bot             bottom-side components
```

* One **part** per distinct STEP model, named after the model file. Ten identical
  resistors cost one solid, not ten.
* Under `symbols_top` / `symbols_bot` the model parts are placed **directly** —
  each entry is an instance carrying its STEP file's own name, with no per-refdes
  wrapper sub-assembly. Identical footprints share the one part.
* The **board part** is named `PCB_<board>` (not a bare `PCB`), so importing
  several boards into one CAD session never lets one board's PCB silently
  substitute another's.
* Each **silkscreen side is its own part**, so it can be hidden or recolored in
  the viewer without touching the board.

## Silkscreen

Both sides are built by default. The legend is exported as real geometry —
filled regions, either extruded into thin solids standing on the board face, or
drawn as flat surfaces just clear of it. Which one is the **Flat** checkbox; see
*Silkscreen file size* for what it costs and what it buys.

**Which layers count** is set in `simple3d_config.json`, next to the two `.il`
files — edit that, not the source, if your layer naming differs. These are two
of the file's four sections; `allegro` and `gui` are described under *Settings*:

```json
{
    "silkscreen": {
        "top":    [ "BOARD GEOMETRY/SILKSCREEN_TOP", "PACKAGE GEOMETRY/SILKSCREEN_TOP",
                    "REF DES/SILKSCREEN_TOP", "COMPONENT VALUE/SILKSCREEN_TOP" ],
        "bottom": [ "…/SILKSCREEN_BOTTOM", … ]
    },
    "settings": {
        "exportSilkscreen": true,
        "silkscreenThickness": 0.025,
        "clipToBoardOutline": true,
        "endCapType": "ROUND"
    }
}
```

| Setting | Meaning |
|---|---|
| `exportSilkscreen` | Collect silkscreen at all. `false` skips it in Allegro, so the JSON stays small. |
| `silkscreenThickness` | Ink thickness in mm. `0.025` (25 µm) is a typical cured screen-printed legend. |
| `clipToBoardOutline` | Trim the legend to the board outline minus every cutout. |
| `endCapType` | Line ends: `ROUND` (what Allegro plots), `SQUARE` or `OCTAGON`. |

If the file is missing or unparsable, built-in defaults matching the block above
are used and the console says so — a broken config never costs you the export.

**Widths, glyphs and curves are Allegro's own.** A silkscreen line is a
centreline plus a width, and turning that into a filled outline is done by
`axlPolyFromDB`, with text vectorised through `axlText2Lines` first. Nothing is
stroked or offset by hand, so what lands in the STEP is the same geometry that
goes to the Gerber.

**Every polygon is checked against Allegro's own area.** The exporter carries
each polygon's area into the JSON, and the builder verifies its reconstruction
against it — so a curve rebuilt the wrong way round cannot pass silently. The
log says which reading of the vertex data won and how many polygons matched:

```
silkscreen_top: 214 polygon(s) match Allegro's areas (arc reading: ...)
```

If some polygons do not match, the log names the worst offender with both
areas. That is worth reporting — it means the legend geometry is distorted.

**Silkscreen is the same for every assembly variant.** The bare board is
manufactured once and serves all of them, so the legend of a component that is
not installed in a given variant is still physically printed on the board. It is
collected once per design, not per variant.

### Choosing layers without re-exporting

The config's `silkscreen.top` / `silkscreen.bottom` lists say which layers are
**collected** in Allegro. Every collected polygon is tagged with the layer it
came from, so which of them actually reach the model is decided in the GUI, per
build:

```
┌─ Silkscreen layers ─────────────────────────────────────────────────────┐
│ Top                                    Bottom                           │
│   ☑ BOARD GEOMETRY/SILKSCREEN_TOP (34)   ☑ BOARD GEOMETRY/SILK_BOT (9)  │
│   ☑ MANUFACTURING/AUTOSILK_TOP    (83)   ☐ REF DES/SILKSCREEN_BOT (61)  │
│   ☐ REF DES/SILKSCREEN_TOP       (412)                                  │
└─ [All] [None] ──────────────────────────────────────────────────────────┘
```

The two sides sit side by side, and the mouse wheel scrolls the panel wherever
the pointer is inside it. Switching **Top** or **Bottom** off greys that side's
layers out without changing them — the ticks are still there when you switch it
back on, and they are what gets saved.

Export once, then try combinations by ticking and pressing Generate — the
counts show what each layer costs before you decide. The list is built from the
JSON, not from the config, so it only ever offers layers that produced geometry
on this board; with several variant JSONs queued it is their union.

A layer left out of the config lists is never collected and cannot be ticked
back on without re-exporting. That is the trade: keeping an expensive layer out
of the config (reference designators vectorise every glyph) saves the collection
time, keeping it in buys the choice.

Older JSON files, from before layers were tagged, carry no layer information.
They build whole, and the panel says so.

### Zero-width objects

A line with no width, or text whose text block has zero pen width, cannot be
plotted — Allegro's own artwork has nothing to draw with either — so it is
skipped and reported by layer and position, both in the Allegro console and,
in orange, in the GUI log:

```
Simple 3D: WARNING - zero width: text on REF DES/SILKSCREEN_TOP at (12.500, 4.000) - skipped, it cannot be plotted.
```

The report is repeated in the GUI because the Allegro console has usually
scrolled past by the time you look at the model, and it appears even when
silkscreen is switched off — the object is wrong in the board either way.

### Silkscreen file size

A legend is thousands of small faces, so it costs real bytes. Measured on a
150-polygon legend, same geometry throughout:

| representation | size | note |
|---|---|---|
| solids, **Compact STEP (reuse component geometry)** on | 2191 kB | the default |
| solids, Minimise **off** | 5769 kB | 2.6x worse - leave the box ticked |
| **Flat** (surfaces) | 566 kB | **26%** of the default |
| boolean-fused into one solid | 3377 kB | *larger*, and slower - not offered |

Three levers, in order of effect:

1. **Flat.** A solid costs one face per polygon edge plus a top and a bottom; a
   surface costs one face. What you give up: the ink is a surface, not a solid -
   no thickness to measure, and nothing downstream can do boolean work with it.

   Overlapping polygons are boolean-unioned into one shape first. Silkscreen
   strokes really do overlap, and as coplanar faces at one z that renders as a
   flickering blend rather than as ink. The union also makes the file slightly
   smaller (measured: 117 faces → 112, 599 kB → 548 kB), which is the opposite
   of what fusing the *solid* legend does.

   The face is lifted off the board by `gui.silkscreenFlatHeight`, 1 µm by
   default. Exactly coplanar faces *do* flicker against each other in a viewer
   that resolves depth per pixel — this was confirmed on a real board — and a
   micron is enough to separate them while staying invisible at board scale. If
   a particular viewer still flickers, raise it: 0.005–0.01 mm is still far
   below anything you would notice.
2. **Drop layers you do not need** from `simple3d_config.json`. Reference
   designators are usually most of the legend by far; removing
   `REF DES/SILKSCREEN_*` from the layer lists keeps outlines and polarity marks
   while cutting the bulk. No code involved, and the JSON gets smaller too.
3. **Turn silkscreen off** for working exports and back on for the final one.

Fusing the legend into one solid was measured and is *counterproductive*: a
boolean union replaces analytic planes and cylinders with general surfaces, and
after clipping the strokes barely overlap, so there is nothing much for it to
remove. It makes the file half again as large and takes longer.

## What gets exported

Every symbol in the design that has a reference designator, plus any symbol that
carries a STEP model (`PKGDEF_STEP_FILE`) but no reference designator — a purely
mechanical part placed straight onto the board — minus two exclusions.

**`NO_STEP_EXPORT` wins over everything.** Attach that property to a symbol —
or to a component or component definition, to drop every instance of a part —
and it is left out of the STEP, even if `Variants.lst` lists it as installed.
Each one is named in the Allegro console:

```
Simple 3D: FID2 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: 3 symbol(s) excluded by NO_STEP_EXPORT.
```

Excluded symbols are also kept out of the "no 3D model" pre-flight list, which
is for parts that *would* be exported if they had a model.

**`Variants.lst` is read from the folder holding the `.brd`** — beside the
board, which is where Allegro keeps it. Nowhere else is looked at, and the
console names the path it tried when there is nothing there:

```
Simple 3D: no Variants.lst beside the board (looked for d:/Projects/board/Variants.lst)
```

With one present, the export writes **one JSON per variant**, named
`<design>_<variant>`, and the window builds every one of them into its own STEP.

**A `Variants.lst` that is not this board's is caught.** Two kinds parse
perfectly and then quietly export the whole board under variant names, which
looks exactly like variants working:

| what it is | what happens now |
|---|---|
| a **stub** — one variant, usually `"dummy"`, with an empty component list | the export stops: every variant would install nothing, leaving a board with only its mechanical parts |
| **another project's file** — plenty of refdes, none of them on this board | the export stops and says so, naming a few of the refdes it was given |

The ordinary case prints the coverage instead:
`variant list covers 47 of 51 placed component(s)`.

**The variant list decides what is installed.** A component that comes from the
schematic is exported only if the variant being built lists it. Absence from the
list is the list saying *not installed* — that is what it is for.

**A part the variant system cannot describe is exported in every variant.**
Three ways to be one, and they are told apart by what the part **is**, not by
whether the file happens to mention it:

- **it is not in the netlist at all** — a bracket, a mating connector, anything
  the designer dropped straight onto the board in Allegro. A part that is not in
  the schematic cannot appear in a variant list generated from that schematic,
  so its absence there says nothing;
- **its symbol type is `MECHANICAL`** — an `.osm` placed directly, usually with
  no refdes;
- **its component class is `MECHANICAL`** — a placed part that does have a
  refdes but no BOM line.

**A variant may also override properties on individual components**, as a block
per component after its base list:

```
(C43 VALUE="12pF" JEDEC_TYPE="CAPC100X50X55L25N" TOL="1" )
```

Those components **are** installed in that variant — they are simply built from
a different part — so their refdes joins that variant's list and they are
exported with it, and only with it. (The 3D model itself comes from the STEP
mapping, so the overridden properties do not change what is drawn.)

`NO_STEP_EXPORT` is still how any of them is kept out of the model altogether.
The console says how many were kept this way:

```
Simple 3D: 4 mechanical symbol(s) are outside the variant system; exported in every variant.
```

**A mechanical symbol needs no reference designator.** A part placed straight
onto the board — a battery holder, a bracket — often has a `PKGDEF_STEP_FILE` on
its symbol definition but no refdes at all (Allegro leaves the refdes nil when
there is no associated component). It is exported on the strength of its STEP
model, counted in the "not listed in any variant" line above, and its instance
is keyed internally as `<SymbolName>_MECH1`, `_MECH2`, … (unique per export). The
key is not shown in the tree — the placed instance carries its STEP file's name,
like every other component.

## Multi-stackup and rigid-flex

A rigid-flex design is several **zones**, each with its own stackup and its own
thickness. The export handles that: it reads the zones from the design, takes
each zone's outline and the thickness of the stackup assigned to it, and builds
the board as those zones fused into one solid. A board with a single stackup
takes the ordinary path and nothing changes.

The console says what it found:

```
Simple 3D: 4 stackup zone(s) exported.
```

and the build log lists them:

```
Multi-stackup board: 4 zone(s), 2.440 mm at its thickest
  STIFFENER2 (STIFFENER2): 2.440 mm
  FLEX2 (FLEX): 0.365 mm
```

**Zones line up on the copper, not on their outer faces.** This is what makes
the result correct rather than merely thick in the right places: a 2.44 mm
stiffener zone and a 0.365 mm flex zone share the same conductor core, and the
stiffener grows outwards from it — mostly upwards. Aligning their top faces
instead would tear the board apart at every zone boundary. Each zone is
therefore measured as three parts (outside the top conductor, core, outside the
bottom conductor) and placed on the shared core.

**Components stand on their own zone.** A part on a stiffener and a part on the
flex are two millimetres apart in Z, and each is placed on the surface of the
zone it actually sits in.

Thickness comes from Allegro's own per-stackup figure rather than being summed
by layer name here — a flex stackup has no `SOLDERMASK` layer at all (coverlay,
adhesive and stiffener sit in its place), so a name-based sum would silently
report those layers as nothing.

## Folding flex bends

A bend is not geometry in Allegro — it is a line on `RIGID FLEX/BEND_LINE`, an
area on `RIGID FLEX/BEND_AREA`, and a property carrying the angle, the inner
side and the bend order. Simple 3D reads all three and folds the model:

```
Folding 1 bend(s):
  BEND1: 90.00 deg over 2.431 mm, inner radius 1.000 mm on the top, order 0
```

**Everything moves together.** The board, the printed legend and the components
are placed flat first and then carried by the fold, so a part cannot drift off
the surface it was placed on. A component standing in a bend area is placed on
the curve and reported — it is a design rule violation, not a modelling choice.

**The radius is measured from the local stack.** A bend crosses the flex, and on
a rigid-flex board the flex surface can be two millimetres below the top of the
stiffener; the fold uses the stackup of the zone the bend line is in.

**Which side moves — the anchor.** The piece containing the **origin** stays in
the XY plane and everything beyond each bend swings from it. Allegro has the
same idea (*Setup – Anchor 3D View*), but in 24.1 the point it asks for never
reaches the board file — not the design property it declares for it
(`ANCHOR_POINT_3D_VIEWER`), not the design's attributes, not any attachment — so
the design cannot tell us and `[0, 0]` is the convention instead. **Put the part
of the board that should lie flat over the origin**, or name another point in
`gui.foldAnchor`. The anchor decides the shape of the fold, not just where it
sits: with it in the middle of a board, two tails swing off a held centre; at
one end, the same two bends make a chain.

Bends are folded outwards from the held piece, each one in the frame the ones
before it leave. A bend whose moving side wholly contains another carries it;
bends on different arms are independent.

What to know about the result:

**The bend surfaces are true cylinders.** There are three constructions, tried
in order, and the log says which one each bend got:

- **Revolved.** When the board is the same shape all the way across a bend area,
  the bent part is its cross-section revolved about the bend axis: six faces,
  two of them exact cylinders, and the volume unchanged to nine decimals.
- **Wrapped.** Otherwise the outline itself is carried onto the cylinder. In the
  cylinder's parameter space the bend is an affine map — the angle is the
  distance across the bend over the neutral radius — so a straight edge stays
  straight, an arc becomes an ellipse, and the surfaces stay exactly
  cylindrical however complicated the outline is. This is what real boards get:
  the **relief notches** at the ends of a bend line — the half circles cut so
  the flex does not tear — sit inside every bend area, and so do zone
  boundaries and the occasional hole.
- **Faceted**, in rigid slices of 7.5°, if neither applies — a piece that is not
  a flat-topped prism, which on a board means something unusual. The chords sit
  about 0.2% of the radius inside the true surface, and consecutive slices
  overlap by a hair so they interpenetrate rather than touching along a line,
  which is what lets the fuse produce one solid. Under 0.5% of the volume.

**A bend stretches and compresses the board, and the model says so.** Material
outside the neutral surface is longer than it was flat and material inside is
shorter — each layer's volume comes out multiplied by its own radius over the
neutral one. On the test board the top coverlay comes out at 0.937 of its flat
volume, the dielectric at the core at 1.000 and the bottom coverlay at 1.063.

**The flat panels either side are never approximated** — they get one exact
rigid transform each, whichever way the bend itself was built.

**Not stitched** folds each layer separately and never fuses them, so along a
bend the layer bodies overlap each other very slightly — 0.25% of the board's
volume on the test board. Flat, the three stitchings agree exactly.

Tick *Fold flex bends* off (or pass `--flat`) for the flat board. The decision
is made when the model is built, so both come out of one export.

### The K factor, and why a ring may need it set to 0

**How much flat material a bend consumes** is its arc length along the neutral
axis, `angle × (radius + k × thickness)`, with `k = gui.foldNeutral` — `0.5`,
the middle of a symmetric flex, by default.

**Allegro draws its bend areas at the inner arc**, `angle × radius`, with no
thickness term in them at all. Measured on three real boards, to a tenth of a
micron every time. That is the same as saying **Allegro's flat pattern is laid
out at `k = 0`**, and on a board with room to spare the difference does not
show. It shows the moment two bend areas touch:

```
warning: bends BEND_5 and BEND_4 both want to fold the same material - 2.805 mm
  and 2.805 mm of it with their lines only 2.500 mm apart - so which of them
  carries the other cannot be read; BEND_5 is left flat
    their drawn bend areas do not overlap - Allegro draws them at the inner arc,
    2.500 mm each on average - so this is the neutral factor, now 0.50: at 0.00
    the two strips meet exactly (foldNeutral in the config, --fold-neutral ...)
```

That board is a flex rolled into a **closed ring**: two 180° bends at R = 0.795
whose areas sit 0.0001 mm apart, and `2π × 0.795 = 4.998` against the 5.000 mm
the designer left for them. At `k = 0` the ring closes to half a micron; at
`k = 0.5` each bend wants 0.306 mm more material than exists and the second one
cannot be folded. **Set `foldNeutral` to `0` for such a board** and every bend
builds. The default stays at `0.5` because that is where the neutral axis of a
symmetric flex physically is; which of the two you want depends on whether you
are reproducing the designer's layout or modelling the material.

Strips that merely **meet** are fine — a ring is exactly that — and only
material claimed by two bends at once is refused. When that happens the export
names both bends and the numbers, leaves the second one flat, and folds
everything else it can.

## Models the board carries a copy of

Once a 3D model has been mapped to a component, Allegro keeps its own copy of
that model **inside the .brd**. Simple 3D does not use those copies: it builds
from model files on disk, taken from the folders listed under **STEP files**.

So a board can look complete in Allegro's own 3D view while a component is
missing here — the model is in the board, just not anywhere this tool can read
it. The export tells the two cases apart and names them:

```
warning: 2 model(s) are stored inside the board but were not found on disk:
         SWITRONIC_IT-1187.step, DIODFN2_100X60X60L27X50.step
```

followed by what to do about it. In short:

1. Export the board from Allegro's own 3DX canvas.
2. Take the missing model files out of that export.
3. Put them in any folder listed under **STEP files** — the board's own folder
   is a convenient choice, since it travels with the design.
4. Run Simple 3D again. Everything is then exported.

A model that is missing from disk and *not* in the board gets the ordinary
"could not find" warning: there is no copy to recover, and the file has to come
from wherever the library keeps it.

**The case of the filename does not matter.** The name comes from Allegro's STEP
mapping table, where it is typed by hand, and the file on disk is named by
whoever supplied the library — so `MODEL.STEP` and `model.step` are the same
file here, as they are to Windows itself. An exact match is preferred; when only
the case differs the log says which file was used.

## Board thickness

The board solid is `dielectrics + planes + conductors + both soldermasks`.
Silkscreen and paste mask are excluded. Example, a 2-layer stackup:

```
1.464 (dielectric) + 0.045 + 0.045 (copper) + 0.025 + 0.025 (mask) = 1.604 mm
```

## Checks and tests

```
python tests/run_all.py            all 20 suites, about 55 s
python tests/run_all.py --quick    skip the OCCT-heavy geometry suites
```

`tools/` holds four mechanical checks on the SKILL sources — parenthesis
balance, string literals broken across a real newline, calls to procedures
defined nowhere, and call arity — plus an audit of this README against the
code. **Run them after any edit to a `.il` file:** SKILL resolves names at call
time, so a file with a stale or wrong-arity call loads without complaint and
fails only when that line executes.

`tests/` holds the Python suites, including the geometry regression that pins
the demo board against the original C++ implementation (volume 12073.309477,
5054 entities). Everything they write goes to `build/test-output/`, which is
gitignored.

`tools/probes/` holds read-only SKILL diagnostics to load in Allegro when a
board does something unexpected — stackups and zones (`probe_flex.il`,
`probe_flex2.il`, `probe_order.il`), layer shapes and polarity
(`probe_layers.il`, `probe_neg.il`, `probe_func.il`), bend lines, bend areas
and their properties (`probe_bend.il`), database attachments
(`probe_attachments*.il`). They change nothing, and the parenthesis and arity
checks above cover them too — a probe that fails to load costs a round trip
with whoever is sitting at Allegro.

## Known limitations

**Milling paths (`BOARD GEOMETRY/ncroute_path`) are not exported.** Only closed
cutout contours are turned into 3D geometry. A route path is an open centerline
plus a tool width, not a boundary, so it cannot be extruded directly — it would
have to be offset by half the tool diameter on each side and closed into a
contour, with correct rounded ends and corner handling. That is a meaningful
amount of error-prone geometry work for a "simple" exporter.

**If you need non-plated slots or milled openings in the 3D model, draw them as
a closed contour on `BOARD GEOMETRY/CUTOUT`.** A cutout is a boundary Simple 3D
extrudes and subtracts directly, so it is reliable. The general rule: anything
you want as a hole in the board must exist as a closed contour on the CUTOUT
subclass.

**A folded bend is a cylinder, not a bent stack-up model.** The surfaces are
exact and the material stretches and compresses as it should (see *Folding flex
bends*), but nothing here models what a bend does to copper, adhesive or
coverlay individually — the whole stack is carried by one map about one neutral
surface, whose position is `gui.foldNeutral`. Good for fit, clearance and a
picture; not a substitute for a flex stress calculation.

**Two bends that claim the same material are not both folded.** Allegro will not
let bend areas overlap, but the material a bend really consumes is longer than
the area drawn for it (see *The K factor* above), and two bends can end up
wanting the same millimetre of flex. The export names both, leaves the second
one flat, and — when the drawn areas themselves do not overlap — says which
`foldNeutral` would make them fit. Bends whose strips only touch are folded
normally.

**Component B-rep comes from your library STEP models.** File size beyond the
board itself is dominated by those models; "Compact STEP (reuse component geometry)" cannot shrink
geometry that lives inside them.

**Silkscreen solids are not fused into one.** This is about **solid** mode: the
legend is thousands of overlapping strokes and glyphs, and a boolean union of
that many thin prisms costs solver time and makes the file *larger* (measured at
154%), while buying nothing visible. Each side is therefore a compound of
separate solids — correct to look at, export and render, but not a single
manifold solid if you intend to do boolean work on the ink itself.

**Flat** mode is the opposite case and *is* unioned: coplanar faces at one z
would flicker against each other where strokes overlap, and unioning them
removes that and shrinks the file at the same time.

**Silkscreen is not subtracted where holes are.** Clipping follows the board
outline and its cutouts, not the drill holes. In practice legend is not printed
over holes anyway, so this shows up only if your artwork deliberately runs a
line across one.

## Command line (without Allegro)

```
python -m stepbuilder                                  # GUI
python -m stepbuilder STEP_DIR JSON_FILE OUTPUT_DIR    # one JSON, headless
python -m stepbuilder STEP_DIR JSON_DIR  OUTPUT_DIR --batch   # every variant JSON
```

Flags: `--batch` (json arg is a folder; build every tagged variant),
`--z-datum {top,bottom}`, `--color NAME|r,g,b|#rrggbb`, `--rim-color ...`,
`--dated-name`, `--brd-name NAME` (names the output file, with or without a
date; single json only — with several variants each json's own stem names its
output), `--no-silkscreen`, `--no-silk-top`,
`--no-silk-bottom`, `--flat-silkscreen`, `--silk-flat-height MM`,
`--silk-layer-off LAYER` (repeatable), `--silk-color White|Black`,
`--ignore-soldermask`, `--flat` (do not fold the bends), `--fold-anchor X,Y|auto`,
`--fold-neutral K`, `--fold-slice-angle DEG`, `--board-mode {solid,layers,inspect}`, `--no-minimize`,
`--legacy-color`, `--quiet`. Exit code 0 on success, 1 on error.

## Package layout

```
stepbuilder/
  core.py       geometry + assembly. No UI, no printing: reports via callbacks.
  colors.py     the eight board themes + rim options.
  bend.py       folding a flex board along its bend areas.
  worker.py     the build, in a child process, so a crash cannot take the window.
  gui.py        tkinter window. Thin wrapper around core.
  __main__.py   entry point: GUI, headless, or --gui prefill for Allegro.
```

---

<a name="русский"></a>
# Русский

# ⚠️ Дисклеймер

Весь код в этом репозитории создан с использованием вайбкодинга совместно с Claude.
Я не являюсь профессиональным разработчиком программного обеспечения. По профессии я инженер-разработчик аппаратного обеспечения, и этот проект появился исключительно как попытка решить собственные практические задачи.
Я не владею в совершенстве ни Python, ни SKILL. Вместо этого я стараюсь максимально точно формулировать требования к инструменту и постепенно доводить его до нужного результата.
Если вы обнаружите ошибку, неточность или захотите предложить улучшение — пожалуйста, создайте Issue или Pull Request. Я постараюсь разобраться и исправить проблему, однако не могу гарантировать, что это произойдет быстро.
Несмотря на выбранный подход к разработке, я стараюсь проверять результаты работы инструмента на практике и использовать этот проект в реальных задачах.

## Зачем это нужно

В Allegro PCB Editor есть штатный экспорт в 3D STEP (`File → Export → 3D`), но он
тяжёлый: тянет полный MCAD-мост, делает большие файлы и требует, чтобы модели
компонентов были проведены через весь 3D-процесс. Для быстрой механической
проверки — «влезает ли плата в корпус», «не сталкиваются ли высокие компоненты»
— это избыточно.

**Simple 3D** — лёгкая альтернатива. Он экспортирует контур платы (с вырезами и
отверстиями) плюс размещённые STEP-модели компонентов в одну STEP-сборку, через
маленький пункт меню и Python-окно. Он намеренно минимален: одно тело платы
правильной итоговой толщины, переиспользование моделей ради малого размера файла
и плоское дерево сборки, которое чисто импортируется в SolidWorks, Inventor или
Creo.

Проект вырос из открытого `exportStep` за авторством juulsA
(https://github.com/juulsA/exportStep), чьи SKILL-экспортёр и построитель STEP на
OpenCASCADE лежат в основе. Построитель на C++ был портирован на Python (тот же
кернел OpenCASCADE, без компилятора и DLL), исправлен ряд багов и добавлены
механические функции, описанные ниже.

## Как это работает

```
File → Export → Simple 3D   (simple3d.il, внутри Allegro)
   │  1. находит папку  rev/cad  (рядом с  rev/pcb )
   │  2. запускает исправленный makeVariant3dIntermediates -> по одному JSON
   │     на вариант в  cad , с меткой  "format": "simple3d"
   │  3. проверяет, что Python вообще запускается, и говорит, если нет
   └─ 4. запускает Python-окно с уже подставленными путями
            │  читает помеченные JSON, собирает STEP
            └─ <плата>_simple_ДД_ММ_ГГГГ.step
```

Штатная форма прогресса Allegro висит на экране с момента нажатия Export и
называет каждый из этих этапов — всё это происходит до появления любого нашего
окна. Рядом с платой ничего временного не пишется.

Две половины общаются через промежуточный JSON: SKILL умеет читать БД Allegro, но
не умеет в B-rep/STEP; OpenCASCADE умеет в STEP, но ничего не знает про Allegro.
JSON — эта граница.

## Установка

### 1. Python (3.10 или новее)

Скачайте с https://www.python.org/downloads/ . При установке поставьте галочку
**«Add Python to PATH»**. `tkinter` (библиотека GUI) входит в стандартный
установщик под Windows — ставить отдельно ничего не нужно.

### 2. Единственная зависимость

Откройте обычное окно `cmd` и выполните:

```
pip install cadquery-ocp
```

`cadquery-ocp` — это геометрический кернел OpenCASCADE с Python-обвязкой.
Ставится только он, и весь `requirements.txt` состоит из него, — но лёгким его
не назовёшь: он жёстко тянет за собой VTK, и втроём они занимают **порядка
470 МБ на диске** (замерено: 91 МБ обвязки, 63 МБ библиотек OCCT и ~315 МБ VTK).

### 3. Файлы

Склонируйте репозиторий или скачайте и распакуйте его. **Его корень уже
представляет собой раскладку ниже** — собирать вручную ничего не нужно:

```
d:\Projects\OrCAD\Scripts\Simple3D\        ← ОДНА папка со всем инструментом
├── makeVariant3dIntermediates.il          ← SKILL-экспортёр (правки внутри)
├── simple3d.il                            ← пункт меню + запуск
├── simple3d_config.json                   ← ВСЕ настройки: пути, GUI, слои шелкографии
├── stepbuilder\                           ← Python-пакет
│   ├── __main__.py
│   ├── core.py
│   ├── bend.py
│   ├── worker.py
│   ├── colors.py
│   └── gui.py
├── demo\                                  ← пример платы + эталонные JSON/STEP (опц.)
├── tests\, tools\                         ← тесты и проверки SKILL (опц.)
├── PROJECT_NOTES_simple3d.md              ← рабочая записка по разработке, для работы не нужна
├── README.md
├── QUICKSTART.md
└── LICENSE
```

Папка может называться как угодно и лежать где угодно; важно лишь, чтобы
`S3D_ScriptDir` и обе строки `load()` указывали на **ту папку, где лежат два
`.il`-файла**.

За чем стоит следить: скачивание репозитория архивом с GitHub заворачивает всё
в дополнительную папку (`Simple3D-main\`). Либо распакуйте её *содержимое* в
свою папку Simple 3D, либо укажите `S3D_ScriptDir` на саму эту обёртку — но не
оставляйте их в противоречии.

Проверьте из `cmd`:

```
cd /d d:\Projects\OrCAD\Scripts\Simple3D
python -m stepbuilder
```

Если окно открылось и в его логе написано `Settings loaded from …`, значит и
пакет, и конфигурация лежат там, где нужно.

### 4. Загрузка SKILL-файлов в Allegro

Добавьте в `allegro.ilinit` (или загружайте вручную каждую сессию):

```
load("d:/Projects/OrCAD/Scripts/Simple3D/makeVariant3dIntermediates.il")
load("d:/Projects/OrCAD/Scripts/Simple3D/simple3d.il")
```

Пункт `File → Export → Simple 3D` появится в меню.

## Настройки — все в `simple3d_config.json`

Все настройки лежат в одном файле, `simple3d_config.json`, рядом с двумя
`.il`-файлами. Его читают обе половины инструмента: SKILL берёт секцию
`allegro`, GUI — `gui`, экспортёр — `silkscreen` и `settings`. При закрытии окна
GUI записывает секцию `gui` обратно, поэтому следующий запуск начинается с того,
что вы ввели в прошлый раз, — а остальная часть файла остаётся нетронутой.

Если файл не читается — отсутствует или отредактирован в невалидный JSON — GUI
ничего не загружает и **ничего не пишет до конца сеанса**, оставляя ваш файл как
есть, даже если вы почините его при открытом окне. Поля на экране в этот момент
содержат умолчания, а не ваши настройки, и запись их обратно затёрла бы только
что исправленный файл. Об этом сообщается в логе. Строка с именем файла настроек выводится при
каждом запуске:

```
Settings loaded from d:/Projects/OrCAD/Scripts/Simple3D/simple3d_config.json
```

так что если поле неожиданно пустое — в логе видно, какой файл прочитан и
разобрался ли он. Метка порядка байт (BOM), оставленная редактором, допускается.

| Секция | Ключ | Что делает |
|---|---|---|
| `allegro` | `python` | Исполняемый Python. `"python"`, если на PATH, иначе полный путь вроде `"c:/Python312/python.exe"`. |
| | `pythonw` | Запуск без консоли (`pythonw.exe`). Когда задан, окно GUI открывается **без окна консоли**. `""` — использовать `python`. |
| | `menuLabel` / `commandName` | Текст пункта меню и внутреннее имя команды. Читаются при загрузке, поэтому их изменение требует перезагрузки SKILL. |
| `gui` | `stepDirs` | Папки с STEP-моделями посадочных мест (по `PKGDEF_STEP_FILE`) — поле «STEP files». **Список, просматриваемый по порядку: побеждает первая папка, где есть нужный файл**, поэтому проектная папка выше общей библиотеки переопределяет отдельные модели. Каждая просматривается рекурсивно, подпапки перечислять не нужно. |
| | `outputDir`, `jsonFile` | Последние пути, выбранные **в самом окне**. Экспорт из Allegro заполняет эти поля под собираемую плату, но в файл их не записывает — они описывают плату, а не настройку. |
| | `boardMode` | Как строится тело платы на **мультистэкапе / rigid-flex**; на обычной плате игнорируется. `solid` — одно тело одного цвета, копланарные грани слиты, самый лёгкий файл. `layers` — одно тело, но границы слоёв **сохранены**, каждая грань красится по виду своего слоя, и торец показывает стек (примерно в 4.7 раза больше `solid`). `inspect` — каждый слой каждой зоны отдельной именованной деталью, чтобы разобрать плату глазами. GUI: список **Body stitching**; CLI: `--board-mode`. |
| | `layerColors` | Цвет на вид слоя (`copper`, `base`, `coverlay`, `adhesive`, `stiffener`, `soldermask`, `other`), используется при `boardMode: layers` и `inspect`. По умолчанию — **собственные цвета материалов Allegro**, взятые из `3DX_APPEARANCE` платы, так что экспорт выглядит как та же плата в 3D-канвасе Allegro. Задаются рядом квадратиков под списком **Body stitching** или вручную как `#RRGGBB`. |
| | `ignoreSoldermask` | Полностью исключить паяльную маску из платы, как бы она ни была задана в проекте, и **сомкнуть стек к ядру** ровно на убранную толщину — с каждой стороны независимо. Компоненты тогда стоят на меди, а не на маске. Действует и на слои платы с мультистэкапом, и на `soldermask_top`/`soldermask_bottom` обычной платы. GUI: *Do not include soldermask layers*; CLI: `--ignore-soldermask`. Решение принимается при сборке модели, переэкспорт не нужен. |
| | `foldBends` | Сгибать плату по **зонам сгиба**, заданным в Allegro (*Setup – Bend*), чтобы гибкий шлейф был там, где он окажется, а не в плоскости. Плата, легенда и компоненты едут вместе. `false` — экспорт плоской платы, как она лежит в Allegro. На плате без зон сгиба не меняет ничего. GUI: *Fold flex bends*; CLI: `--flat` выключает. Решение принимается при сборке модели, переэкспорт не нужен. |
| | `foldAnchor` | Точка платы, которая **остаётся в плоскости XY**, как `[x, y]`. **По соглашению — начало координат, `[0, 0]`**; см. «Сгибание гибких плат». Она отвечает только на вопрос, по какую сторону каждой линии сгиба держим, поэтому попадать внутрь контура не обязана. `"auto"` — держать самый большой кусок, который оставляют линии сгиба. CLI: `--fold-anchor X,Y|auto`. |
| | `foldNeutral` | Где в стеке лежит нейтральная ось, долей толщины от внутренней поверхности (по умолчанию `0.5` — середина). Именно это решает, сколько плоского материала съедает сгиб: `угол × (радиус + k × толщина)`. **На плате, где зоны сгиба соприкасаются, ставьте `0`** — Allegro раскладывает плоскую заготовку именно при `k = 0`, см. «Сгибание гибких плат». CLI: `--fold-neutral K`. |
| | `foldSliceAngle` | Градусов дуги на один ломтик для сгиба, который пришлось **гранить** — а это бывает, только когда не подошло ни одно точное построение, и лог тогда называет сгиб и причину. По умолчанию `7.5`. Сгибы, построенные настоящими цилиндрами, его игнорируют. CLI: `--fold-slice-angle DEG`. |
| | `windowGeometry`, `windowState` | Где было окно при последнем закрытии (`ШИРИНАxВЫСОТА+X+Y`) и было ли оно развёрнуто. Восстанавливается при следующем запуске, поэтому на нескольких мониторах окно возвращается **на тот же экран** — для монитора левее главного `X` отрицателен. Если позиция стала недостижимой (обычно монитор отключили), она игнорируется, окно центрируется на главном экране, и в лог пишется почему. При первом запуске пусто — окно тоже центрируется. |
| | `boardColor`, `boardEdge`, `boardEdgeCustom` | Цвет платы и торца. |
| | `zDatum` | `"top"` или `"bottom"`. |
| | `silkscreenTop`, `silkscreenBottom` | Какие стороны легенды строить. |
| | `silkColor`, `silkscreenFlat` | Цвет краски и плоская/объёмная. |
| | `silkscreenLayersOff` | Слои, снятые галочкой в окне. Хранятся именно исключения: слой, впервые появившийся на плате, будет нарисован, а не пропадёт молча. |
| | `silkscreenFlatHeight` | Расстояние в мм от поверхности платы до **плоской** шелкографии, чтобы они не совпадали и не рябили. По умолчанию `0.001` (1 мкм). Это не толщина краски — она в `settings.silkscreenThickness` и относится только к объёмному режиму. |
| | `minimizeFileSize` | См. «Размер файла и шелкография». |
| `settings` | `negativeLayers` | Слои стэкапа, чьи нарисованные шейпы — **окна**, а не материал; сопоставление без учёта регистра по подстроке имени слоя или его IPC-функции. Coverlay, soldermask и pastemask рисуются так по конвенции; stiffener, adhesive и epoxy — наоборот. Добавьте слой сюда, если в инспекционной сборке его тела вышли инверсными. |
| `silkscreen`, `settings` | | Слои шелкографии и параметры краски — см. «Шелкография». |

Два ключа **читаются, но никогда не записываются** — чтобы конфигурация от
более старой сборки продолжала работать: `stepDir` (одна папка, на смену
которой пришёл список `stepDirs`) и `debugLayers` (булево «inspect», на смену
которому пришёл `boardMode`). Каждый переносится при загрузке и удаляется при
сохранении. Вручную их добавлять не нужно — `stepDirs` и `boardMode` всё равно
побеждают.

### Единственная настройка, оставшаяся в `simple3d.il`

`S3D_ScriptDir` — папка проекта. Файл конфигурации ищется относительно неё,
поэтому папку нужно знать до того, как конфигурацию можно прочитать; эта
начальная загрузка и есть причина, по которой настройка осталась в исходнике.
Укажите ту папку, куда распаковали проект (ту же, что в двух строках `load()`).
Рядом стоит `S3D_ConfigFile` — его меняют, только если конфигурация намеренно
лежит в другом месте.

## Окно программы

| Элемент | Назначение |
|---|---|
| **STEP files** | Папки с STEP-моделями посадочных мест, **по одной на строку** (`gui.stepDirs`). Просматриваются по порядку — побеждает первая, где есть нужный файл, поэтому проектная папка выше общей библиотеки переопределяет отдельные модели. Каждая просматривается рекурсивно. **Add...** дописывает папку в конец; порядок правится прямо текстом. Имя, найденное в нескольких папках, отмечается в логе с указанием победившего пути. |
| **JSON file** | Промежуточный JSON или папка с JSON-вариантами. Берутся только файлы с меткой `"format": "simple3d"`, остальные игнорируются с записью в лог. |
| **Output** | Куда пишется `.step` (папка `cad`). |
| **Board color** | Восемь тем 3D-канвы Allegro, с образцом цвета. |
| **Board edge color** | Цвет торца / боковых стенок: как плата, кремовый диэлектрик или свой из палитры. Контрастировать есть с чем только у *Solid* — единственного режима, где плата целиком одного цвета, — поэтому в двух других элемент гаснет, а в лог пишется, что цвет проигнорирован. |
| **Z = 0 at** | Какая грань платы — ноль: верхняя или нижняя. Компоненты садятся на маску своей стороны (на площадках реально есть припой, поднимающий деталь до уровня маски). |
| **Body stitching** | Как собрано тело платы — *Solid*, *Solid colored layers*, *Not stitched* (`gui.boardMode`). Только для мультистэкапа и rigid-flex; обычная плата остаётся одним телом при любом значении. Ряд квадратиков под списком задаёт цвет каждого вида слоя и действует на два последних режима, кнопка **Reset colors** возвращает цвета материалов Allegro. В *Solid* и то и другое погашено. |
| **Do not include soldermask layers** | Убрать паяльную маску из платы и сомкнуть стек к ядру на убранную толщину (`gui.ignoreSoldermask`). Плата действительно становится тоньше — поэтому на самой галочке написано *check total thickness*. |
| **Silkscreen: Top / Bottom** | Какие стороны легенды строить. Обе выключены — шелкографии нет вовсе, файл заметно меньше, а остальная группа гаснет. |
| **Color** (в той же строке) | Цвет краски: **White** или **Black**. Это те два цвета, которыми шелкография реально печатается, поэтому выбор закрытый. |
| **Make surface (minimum file size)** | Рисовать легенду поверхностями вместо тонких тел: примерно вчетверо меньший вклад в размер файла. Высота над платой задаётся `gui.silkscreenFlatHeight`. См. «Размер файла и шелкография» ниже. |
| **Silkscreen layers** | Галочка на каждый слой, найденный в загруженном JSON, с числом полигонов; стороны расположены рядом. Снимите галочку — слой не попадёт в эту сборку, повторный экспорт не нужен. **All** / **None** переключают все сразу, пропуская выключенную сторону. |
| **Fold flex bends** | Согнуть плату по её зонам сгиба (см. «Сгибание гибких плат»). Включено по умолчанию; снятая галочка даёт плоскую плату. На плате без зон сгиба не делает ничего. |
| **Compact STEP (reuse component geometry)** | Убирает параметрические кривые поверхностей (`write.surfacecurve.mode = 0`), примерно вдвое уменьшая файл при идентичной геометрии. |
| **Generate** | Собирает один файл или все варианты из очереди. |

Сообщения в логе раскрашены: **оранжевый** — предупреждения, **тёмно-красный** —
ошибки, зелёный — успех. Полоса прогресса идёт по всей сборке — чтение, плата,
легенда, компоненты, запись, — а строка рядом говорит, что именно происходит.

**Сборка идёт в дочернем процессе.** OpenCASCADE умеет не выбрасывать
исключение, а падать целиком, и на трудной плате булева операция это иногда
делает; в потоке это закрыло бы окно, не написав никуда ни строчки. Вместо этого
окно сообщает код возврата и то, что обычно помогает: *Not stitched* (там ничего
не сплавляется) или более крупный `gui.foldSliceAngle`.

Консоль Allegro тоже раскрашена. Сообщения идут через `axlUIWPrint` с уровнем
важности, поэтому предупреждения выводятся цветом предупреждений Allegro, а
ошибки красным — с теми же префиксами `*WARNING*` / `*Error*`, что и у
собственных сообщений Allegro. Зелёного нет: документированные уровни — `info0`,
`info1`, `warn`, `error` и `fatal`, и ни один не означает успех, поэтому
завершённый экспорт печатается обычным цветом. Зелёным успешная сборка видна в
логе окна.

## Структура сборки

```
<имя_платы>
├── PCB_<плата>             одно тело итоговой толщины
├── silkscreen_top_<плата>  шелкография сверху (если включена и есть)
├── silkscreen_bot_<плата>  шелкография снизу
├── symbols_top             компоненты верхней стороны
│   ├── cap_D8x10mm         деталь с именем своего STEP-файла, на месте
│   └── cap_D8x10mm         та же деталь ещё раз, если модель повторяется
└── symbols_bot             компоненты нижней стороны
```

* Одна **деталь** на каждую уникальную STEP-модель, названа по имени файла
  модели. Десять одинаковых резисторов стоят одного тела, а не десяти.
* Под `symbols_top` / `symbols_bot` детали моделей размещаются **напрямую** —
  каждый элемент это вхождение с именем своего STEP-файла, без обёртки-подсборки
  на каждый рефдес. Одинаковые посадочные места делят одну деталь.
* **Деталь платы** называется `PCB_<плата>` (а не просто `PCB`), поэтому импорт
  нескольких плат в одну сессию CAD не даёт детали одной платы подменить деталь
  другой.
* **Каждая сторона шелкографии — отдельная деталь**, поэтому её можно скрыть или
  перекрасить в просмотрщике, не трогая плату.

## Шелкография

По умолчанию строятся обе стороны. Легенда экспортируется настоящей
геометрией — залитыми областями, которые либо выдавливаются в тонкие тела,
стоящие на грани платы, либо рисуются плоскими поверхностями чуть выше неё.
Выбор — галочка **Flat**; чем это оборачивается, см. «Размер файла и
шелкография».

**Какие слои считать шелкографией**, задаётся в `simple3d_config.json` рядом с
двумя `.il`-файлами — правьте его, а не исходник, если у вас другое именование
слоёв. Ниже — две из четырёх секций файла; `allegro` и `gui` описаны в разделе
«Настройки»:

```json
{
    "silkscreen": {
        "top":    [ "BOARD GEOMETRY/SILKSCREEN_TOP", "PACKAGE GEOMETRY/SILKSCREEN_TOP",
                    "REF DES/SILKSCREEN_TOP", "COMPONENT VALUE/SILKSCREEN_TOP" ],
        "bottom": [ "…/SILKSCREEN_BOTTOM", … ]
    },
    "settings": {
        "exportSilkscreen": true,
        "silkscreenThickness": 0.025,
        "clipToBoardOutline": true,
        "endCapType": "ROUND"
    }
}
```

| Настройка | Смысл |
|---|---|
| `exportSilkscreen` | Собирать шелкографию вообще. `false` — пропустить её в Allegro, JSON останется маленьким. |
| `silkscreenThickness` | Толщина краски в мм. `0.025` (25 мкм) — типичная высохшая трафаретная печать. |
| `clipToBoardOutline` | Обрезать легенду по контуру платы за вычетом всех вырезов. |
| `endCapType` | Концы линий: `ROUND` (как Allegro выводит в фотошаблон), `SQUARE` или `OCTAGON`. |

Если файла нет или он не разбирается, применяются встроенные значения,
совпадающие с блоком выше, и об этом пишется в консоль — сломанный конфиг
никогда не стоит вам экспорта.

**Ширины, глифы и дуги — родные аллегровские.** Линия шелкографии это осевая
плюс ширина, и превращение её в залитый контур делает `axlPolyFromDB`, а текст
сначала векторизуется через `axlText2Lines`. Ничего не обводится и не смещается
вручную, поэтому в STEP попадает та же геометрия, что уходит в Gerber.

**Каждый полигон сверяется с площадью, которую сообщил Allegro.** Экспортёр
кладёт площадь каждого полигона в JSON, а сборщик проверяет по ней свою
реконструкцию — так что дуга, восстановленная не в ту сторону, не пройдёт
молча. В логе видно, какое прочтение данных победило и сколько полигонов сошлось:

```
silkscreen_top: 214 polygon(s) match Allegro's areas (arc reading: ...)
```

Если часть полигонов не сошлась, лог называет худший случай с обеими площадями.
Об этом стоит сообщать — значит, геометрия легенды искажена.

**Шелкография одинакова для всех вариантов сборки.** Текстолит производится один
раз и обслуживает все варианты, поэтому маркировка неустановленного в данном
варианте компонента физически на плате всё равно есть. Она собирается один раз на
проект, а не на каждый вариант.

### Выбор слоёв без повторного экспорта

Списки `silkscreen.top` / `silkscreen.bottom` в конфиге задают, какие слои
**собираются** в Allegro. Каждый собранный полигон помечается слоем, из которого
он пришёл, поэтому какие из них реально попадут в модель, решается в окне — на
каждую сборку:

```
┌─ Silkscreen layers ─────────────────────────────────────────────────────┐
│ Top                                    Bottom                           │
│   ☑ BOARD GEOMETRY/SILKSCREEN_TOP (34)   ☑ BOARD GEOMETRY/SILK_BOT (9)  │
│   ☑ MANUFACTURING/AUTOSILK_TOP    (83)   ☐ REF DES/SILKSCREEN_BOT (61)  │
│   ☐ REF DES/SILKSCREEN_TOP       (412)                                  │
└─ [All] [None] ──────────────────────────────────────────────────────────┘
```

Стороны расположены рядом, а колесо мыши прокручивает панель в любом её месте,
не только на полосе прокрутки. Выключение **Top** или **Bottom** делает слои
этой стороны серыми, не меняя их: галочки останутся такими же, когда сторону
включите обратно, и именно они сохраняются в конфиг.

Экспортируете один раз, дальше пробуете комбинации галочками и кнопкой Generate
— число полигонов рядом показывает цену слоя до того, как вы решите. Список
строится из JSON, а не из конфига, поэтому в нём не может быть слоя, который на
этой плате ничего не дал; при нескольких вариантах в очереди берётся их
объединение.

Слой, которого нет в списках конфига, не собирается вовсе и включить его
галочкой не получится — нужен повторный экспорт. Это и есть компромисс: держать
дорогой слой вне конфига (позиционные обозначения векторизуют каждый глиф)
экономит время сбора, держать внутри — покупает свободу выбора.

Старые JSON, сделанные до появления меток, слоёв не несут. Они строятся целиком,
и панель об этом сообщает.

### Объекты нулевой ширины

Линия без ширины или текст, у которого в текстовом блоке нулевая толщина пера,
не может быть отпечатан — у самого Allegro в фотошаблоне тоже нечем рисовать, —
поэтому такой объект пропускается, а о нём сообщается с указанием слоя и
координат: и в консоли Allegro, и оранжевым в логе окна:

```
Simple 3D: WARNING - zero width: text on REF DES/SILKSCREEN_TOP at (12.500, 4.000) - skipped, it cannot be plotted.
```

Сообщение повторяется в окне, потому что консоль Allegro к моменту просмотра
модели обычно уже прокручена, и выводится даже при выключенной шелкографии —
объект в плате неверен в любом случае.

### Размер файла и шелкография

Легенда — это тысячи мелких граней, и она стоит реальных байт. Замерено на
легенде из 150 полигонов, геометрия во всех случаях одна и та же:

| представление | размер | примечание |
|---|---|---|
| тела, **Compact STEP (reuse component geometry)** включён | 2191 КБ | по умолчанию |
| тела, Minimise **выключен** | 5769 КБ | в 2.6 раза хуже — галочку не снимайте |
| **Flat** (поверхности) | 566 КБ | **26%** от значения по умолчанию |
| объединение булевой операцией в одно тело | 3377 КБ | *больше* и медленнее — не предлагается |

Три рычага, по убыванию эффекта:

1. **Flat.** Тело стоит по грани на каждое ребро полигона плюс верх и низ;
   поверхность — одну грань. Чем платите: краска становится поверхностью, а не
   телом — толщину не измерить и булевы операции с ней невозможны.

   Перекрывающиеся полигоны сначала объединяются булевой операцией. Штрихи
   шелкографии реально перекрываются, и как компланарные грани на одном z это
   рисуется мерцающим слипанием, а не краской. Объединение заодно немного
   уменьшает файл (замерено: 117 граней → 112, 599 КБ → 548 КБ) —
   противоположно тому, что даёт объединение *объёмной* легенды.

   Грань приподнята над платой на `gui.silkscreenFlatHeight`, по умолчанию
   1 мкм. Строго совпадающие плоскости действительно рябят друг о друга в
   просмотрщике, разрешающем глубину попиксельно — это подтвердилось на реальной
   плате, — а микрона достаточно, чтобы их развести, оставаясь невидимым в
   масштабе платы. Если конкретный просмотрщик всё равно рябит — увеличьте:
   0.005–0.01 мм по-прежнему далеко за порогом заметности.
2. **Уберите ненужные слои** из `simple3d_config.json`. Позиционные обозначения
   обычно составляют бо́льшую часть легенды; удаление `REF DES/SILKSCREEN_*` из
   списков оставит контуры и метки полярности, но срежет основной объём. Кода не
   требует, и JSON тоже становится меньше.
3. **Выключайте шелкографию** для рабочих выгрузок и включайте для финальной.

Объединение легенды в одно тело было измерено и оказалось **контрпродуктивным**:
булева операция заменяет аналитические плоскости и цилиндры общими
поверхностями, а после обрезки штрихи почти не перекрываются, так что удалять
ей особо нечего. Файл вырастает в полтора раза, и это дольше.

## Что попадает в экспорт

Все символы проекта, у которых есть позиционное обозначение, плюс любой символ,
несущий STEP-модель (`PKGDEF_STEP_FILE`), но без позиционного обозначения —
чисто механическая деталь, поставленная прямо на плату, — за вычетом двух
исключений.

**`NO_STEP_EXPORT` сильнее всего остального.** Повесьте это свойство на символ —
либо на компонент или его определение, чтобы убрать все экземпляры детали, — и
он не попадёт в STEP, даже если `Variants.lst` числит его установленным. Каждый
такой символ называется в консоли Allegro:

```
Simple 3D: FID2 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: 3 symbol(s) excluded by NO_STEP_EXPORT.
```

Исключённые символы не попадают и в предварительный список «нет 3D-модели» — он
про детали, которые экспортировались бы, будь у них модель.

**`Variants.lst` читается из папки, где лежит `.brd`** — рядом с платой, там,
где его держит Allegro. Больше нигде не ищется, а если там ничего нет, консоль
называет путь, по которому смотрели:

```
Simple 3D: no Variants.lst beside the board (looked for d:/Projects/board/Variants.lst)
```

Когда файл есть, экспорт пишет **по одному JSON на вариант** с именем
`<плата>_<вариант>`, и окно собирает каждый из них в собственный STEP.

**Чужой `Variants.lst` теперь ловится.** Два вида разбираются без единой
ошибки, а потом молча экспортируют всю плату под именами вариантов — со стороны
неотличимо от работающих вариантов:

| что это | что происходит теперь |
|---|---|
| **заглушка** — один вариант, обычно `"dummy"`, с пустым списком компонентов | экспорт останавливается: каждый вариант установил бы ничего, и на плате осталась бы одна механика |
| **файл от другого проекта** — обозначений много, но ни одного с этой платы | экспорт останавливается и говорит об этом, называя несколько полученных обозначений |

В обычном случае печатается покрытие:
`variant list covers 47 of 51 placed component(s)`.

**Что установлено — решает список варианта.** Компонент, пришедший из схемы,
экспортируется, только если собираемый вариант его перечисляет. Отсутствие в
списке — это и есть «не установлен», ради этого список и существует.

**Деталь, которую система вариантов описать не может, экспортируется во всех
вариантах.** Быть такой можно тремя способами, и различаются они по тому, чем
деталь **является**, а не по тому, упомянута ли она в файле:

- **её нет в списке соединений вообще** — кронштейн, ответная часть разъёма, всё
  что конструктор поставил на плату прямо в Allegro. Детали, которой нет в схеме,
  неоткуда взяться в списке вариантов, сгенерированном из этой схемы, поэтому её
  отсутствие там ничего не значит;
- **тип символа `MECHANICAL`** — напрямую поставленный `.osm`, обычно вообще без
  позиционного обозначения;
- **класс компонента `MECHANICAL`** — поставленная деталь с обозначением, но без
  строки в BOM.

**Вариант может ещё и переопределять свойства отдельных компонентов** — блоком
на компонент после базового списка:

```
(C43 VALUE="12pF" JEDEC_TYPE="CAPC100X50X55L25N" TOL="1" )
```

Такие компоненты в этом варианте **установлены**, просто собираются из другой
детали, — поэтому их обозначения попадают в список этого варианта и
экспортируются вместе с ним, и только с ним. (Сама 3D-модель берётся из
STEP-маппинга, так что переопределённые свойства на геометрию не влияют.)

`NO_STEP_EXPORT` по-прежнему убирает любую из них из модели совсем. Сколько
деталей осталось по этому правилу, видно в консоли:

```
Simple 3D: 4 mechanical symbol(s) are outside the variant system; exported in every variant.
```

**Механическому символу позиционное обозначение не нужно.** Деталь, поставленная
прямо на плату — держатель батарейки, кронштейн, — часто несёт `PKGDEF_STEP_FILE`
на определении символа, но позиционного обозначения не имеет вовсе (Allegro
оставляет refdes пустым, когда связанного компонента нет). Она экспортируется на
основании своей STEP-модели, попадает в строку «not listed in any variant» выше,
а её экземпляр внутри ключуется как `<ИмяСимвола>_MECH1`, `_MECH2`, … (уникально
на каждый экспорт). В дереве этот ключ не виден — размещённый экземпляр носит имя
своего STEP-файла, как и любой другой компонент.

## Мультистэкап и rigid-flex

Гибко-жёсткий дизайн — это несколько **зон**, у каждой свой стэкап и своя
толщина. Экспорт это учитывает: читает зоны из проекта, берёт контур каждой и
толщину назначенного ей стэкапа и строит плату как эти зоны, сплавленные в одно
тело. Плата с одним стэкапом идёт прежним путём, ничего не меняется.

В консоли видно, что найдено:

```
Simple 3D: 4 stackup zone(s) exported.
```

а в логе сборки — перечень:

```
Multi-stackup board: 4 zone(s), 2.440 mm at its thickest
  STIFFENER2 (STIFFENER2): 2.440 mm
  FLEX2 (FLEX): 0.365 mm
```

**Зоны выравниваются по меди, а не по внешним поверхностям.** Именно это делает
результат правильным, а не просто «толстым где надо»: зона жёсткости 2.44 мм и
гибкая зона 0.365 мм имеют общее проводниковое ядро, и жёсткая наращивается от
него наружу — в основном вверх. Выравнивание по верхним граням разорвало бы
плату на каждой границе зон. Поэтому каждая зона измеряется тремя частями (над
верхним проводником, ядро, под нижним) и ставится на общее ядро.

**Компоненты стоят на своей зоне.** Деталь на жёсткости и деталь на гибком
участке разнесены по Z на два миллиметра, и каждая ставится на поверхность той
зоны, в которой реально находится.

Толщина берётся из собственной оценки Allegro по каждому стэкапу, а не
суммируется здесь по именам слоёв: у гибкого стэкапа слоя `SOLDERMASK` нет
вовсе — на его месте coverlay, adhesive и stiffener, — и сумма по именам молча
посчитала бы их за ноль.

## Сгибание гибких плат

Сгиб в Allegro — это не геометрия, а линия на `RIGID FLEX/BEND_LINE`, область на
`RIGID FLEX/BEND_AREA` и свойство с углом, внутренней стороной и порядком сгиба.
Simple 3D читает всё это и складывает модель:

```
Folding 1 bend(s):
  BEND1: 90.00 deg over 2.431 mm, inner radius 1.000 mm on the top, order 0
```

**Едет всё вместе.** Плата, легенда и компоненты сначала размещаются в плоскости,
а затем переносятся сгибом, поэтому деталь не может «съехать» с той поверхности,
на которую её поставили. Компонент, попавший в зону сгиба, ставится на дугу и
отмечается в логе — это нарушение правил проектирования, а не выбор модели.

**Радиус отсчитывается от местного стэкапа.** Сгиб проходит по гибкому участку, а
на rigid-flex его поверхность может лежать на два миллиметра ниже верха жёсткой
зоны; берётся стэкап той зоны, в которой лежит линия сгиба.

**Что именно двигается — якорь.** В плоскости XY остаётся кусок, содержащий
**начало координат**, а всё за каждым сгибом качается от него. В Allegro есть та
же идея (*Setup – Anchor 3D View*), но в 24.1 выбранная точка до файла платы не
доходит — ни в объявленное под неё свойство `ANCHOR_POINT_3D_VIEWER`, ни в
атрибуты design, ни в одно вложение, — поэтому проект нам её сообщить не может и
соглашением служит `[0, 0]`. **Разместите ту часть платы, которая должна лежать
плоско, над началом координат**, либо укажите другую точку в `gui.foldAnchor`.
Якорь определяет саму форму сгиба, а не только положение: с якорем в середине
платы два шлейфа отгибаются от неподвижного центра, а с якорем на краю те же два
сгиба образуют цепочку.

Сгибы применяются от неподвижной части наружу, каждый — в системе координат,
оставленной предыдущими. Сгиб, чья подвижная сторона целиком содержит другой,
несёт его на себе; сгибы на разных рукавах независимы.

Что стоит знать о результате:

**Поверхности сгиба — настоящие цилиндры.** Построений три, они пробуются по
порядку, и лог говорит, какое досталось каждому сгибу:

- **Вращением.** Если поперёк зоны сгиба плата везде одной и той же формы,
  согнутая часть — это её сечение, провёрнутое вокруг оси сгиба: шесть граней,
  две из них точные цилиндры, объём совпадает до девятого знака.
- **Навёрткой.** Иначе на цилиндр переносится сам контур. В параметрическом
  пространстве цилиндра сгиб — аффинное отображение (угол есть расстояние
  поперёк сгиба, делённое на нейтральный радиус), поэтому прямая остаётся
  прямой, дуга становится эллипсом, а поверхности остаются точно
  цилиндрическими при любой сложности контура. Реальные платы получают именно
  это: **разгрузочные вырезы** на концах линии сгиба — полукруги, которые режут,
  чтобы гибкая часть не рвалась, — лежат внутри каждой зоны сгиба, как и границы
  зон, и случайное отверстие.
- **Гранями** по 7.5°, если не подошло ни то, ни другое, — например, кусок,
  который не является призмой с плоским верхом; на плате это что-то необычное.
  Хорды лежат примерно на 0.2% радиуса внутри истинной поверхности, а соседние
  ломтики перекрываются на волосок, чтобы входить друг в друга, а не касаться по
  линии — только так объединение даёт одно тело. Меньше 0.5% объёма.

**Сгиб растягивает и сжимает материал, и модель это показывает.** Материал
снаружи нейтральной поверхности длиннее, чем был плоским, внутри — короче: объём
каждого слоя умножается на его собственный радиус, делённый на нейтральный. На
тестовой плате верхний coverlay выходит 0.937 от плоского объёма, диэлектрик на
ядре — 1.000, нижний coverlay — 1.063.

**Плоские панели по обе стороны не аппроксимируются никогда** — каждая получает
одно точное жёсткое преобразование, как бы ни был построен сам сгиб.

**Not stitched** сгибает каждый слой отдельно и не сплавляет их, поэтому вдоль
сгиба тела слоёв чуть-чуть входят друг в друга — 0.25% объёма платы на тестовой
плате. В плоском виде все три режима совпадают точно.

Снимите галочку *Fold flex bends* (или передайте `--flat`), чтобы получить
плоскую плату. Решение принимается при сборке модели, так что оба варианта
получаются из одного экспорта.

### K-фактор, и почему кольцу может понадобиться ноль

**Сколько плоского материала съедает сгиб** — это длина дуги по нейтральной оси,
`угол × (радиус + k × толщина)`, где `k = gui.foldNeutral`; по умолчанию `0.5` —
середина симметричного флекса.

**Allegro рисует зоны сгиба по внутренней дуге**, `угол × радиус`, вообще без
слагаемого толщины. Замерено на трёх реальных платах, каждый раз с точностью до
десятой микрона. Это то же самое, что сказать: **плоская заготовка в Allegro
разложена при `k = 0`**. Пока на плате есть запас, разница незаметна. Она
вылезает ровно в тот момент, когда две зоны сгиба соприкасаются:

```
warning: bends BEND_5 and BEND_4 both want to fold the same material - 2.805 mm
  and 2.805 mm of it with their lines only 2.500 mm apart - so which of them
  carries the other cannot be read; BEND_5 is left flat
    their drawn bend areas do not overlap - Allegro draws them at the inner arc,
    2.500 mm each on average - so this is the neutral factor, now 0.50: at 0.00
    the two strips meet exactly (foldNeutral in the config, --fold-neutral ...)
```

Эта плата — флекс, свёрнутый в **замкнутое кольцо**: два разворота по 180° при
R = 0.795, зоны которых стоят в 0.0001 мм друг от друга, и `2π × 0.795 = 4.998`
против 5.000 мм, оставленных конструктором. При `k = 0` кольцо смыкается с
точностью до половины микрона; при `k = 0.5` каждому сгибу нужно на 0.306 мм
материала больше, чем есть, и второй согнуть невозможно. **Для такой платы
поставьте `foldNeutral` в `0`** — и построятся все сгибы. Умолчание остаётся
`0.5`, потому что физически нейтральная ось симметричного флекса лежит именно
там; что вам нужно, зависит от того, воспроизводите вы раскладку конструктора
или моделируете материал.

Полосы, которые просто **соприкасаются**, — это нормально (кольцо и есть такой
случай); отвергается только материал, на который претендуют сразу два сгиба.
Тогда экспорт называет оба сгиба и цифры, оставляет второй плоским и сгибает всё
остальное, что может.

## Модели, копия которых лежит внутри платы

После того как 3D-модель привязана к компоненту, Allegro хранит её собственную
копию **внутри .brd**. Simple 3D эти копии не использует: он собирает модель из
файлов на диске, из папок, перечисленных в поле **STEP files**.

Поэтому плата может выглядеть полной в штатном 3D-виде Allegro, а здесь
компонента не окажется — модель есть в плате, но нет там, откуда этот инструмент
умеет читать. Экспорт различает эти два случая и называет модели поимённо:

```
warning: 2 model(s) are stored inside the board but were not found on disk:
         SWITRONIC_IT-1187.step, DIODFN2_100X60X60L27X50.step
```

и следом поясняет, что делать. Кратко:

1. Экспортируйте плату из штатного 3DX-канваса Allegro.
2. Возьмите из этого экспорта недостающие файлы моделей.
3. Положите их в любую папку из списка **STEP files** — удобно в папку самой
   платы, тогда они путешествуют вместе с проектом.
4. Запустите Simple 3D ещё раз. После этого экспортируется всё.

Модель, которой нет ни на диске, ни в плате, получает обычное предупреждение
«could not find»: восстанавливать нечего, файл нужно брать там, где лежит
библиотека.

**Регистр имени файла значения не имеет.** Имя приходит из таблицы
сопоставления STEP в Allegro, где его набирают руками, а файл на диске назван
так, как его назвал поставщик библиотеки, — поэтому `MODEL.STEP` и `model.step`
здесь один и тот же файл, ровно как и для самой Windows. Точное совпадение
предпочитается; когда отличается только регистр, лог сообщает, какой файл взят.

## Толщина платы

Тело платы — это `диэлектрики + плейны + проводники + обе паяльные маски`.
Шелкография и паяльная паста не учитываются. Пример, двухслойный стек:

```
1.464 (диэлектрик) + 0.045 + 0.045 (медь) + 0.025 + 0.025 (маска) = 1.604 мм
```

## Проверки и тесты

```
python tests/run_all.py            все 20 наборов, около 55 с
python tests/run_all.py --quick    без тяжёлых геометрических наборов
```

В `tools/` — четыре механические проверки исходников SKILL: баланс скобок,
строковые литералы, разорванные настоящим переводом строки, вызовы процедур,
которых нигде нет, и арность вызовов. Плюс сверка этого README с кодом.
**Запускайте их после любой правки `.il`:** SKILL разрешает имена в момент
вызова, поэтому файл с устаревшим вызовом или неверным числом аргументов
грузится без единой жалобы и падает лишь тогда, когда до этой строки дойдёт
исполнение.

В `tests/` — наборы на Python, включая регрессию геометрии, которая держит
демонстрационную плату на значениях исходной реализации C++ (объём
12073.309477, 5054 сущности). Всё, что они пишут, идёт в `build/test-output/`,
а он в `.gitignore`.

В `tools/probes/` — диагностические скрипты SKILL только для чтения: загрузить
в Allegro, когда плата ведёт себя неожиданно. Стэкапы и зоны (`probe_flex.il`,
`probe_flex2.il`, `probe_order.il`), шейпы слоёв и полярность
(`probe_layers.il`, `probe_neg.il`, `probe_func.il`), линии и зоны сгиба с их
свойствами (`probe_bend.il`), вложения базы (`probe_attachments*.il`). Ничего
не меняют, и проверки скобок и арности выше распространяются и на них: зонд,
который не загрузился, стоит одного круга с тем, кто сидит за Allegro.

## Известные ограничения

**Фрезеровка (`BOARD GEOMETRY/ncroute_path`) не экспортируется.** В 3D-геометрию
превращаются только замкнутые контуры вырезов. Путь фрезеровки — это открытая
осевая линия плюс диаметр инструмента, а не граница, поэтому его нельзя
экструдировать напрямую: пришлось бы сместить осевую на половину диаметра в обе
стороны и замкнуть в контур, с правильными скруглёнными концами и обработкой
углов. Это заметный объём легко-ошибающейся геометрии для «простого» экспортёра.

**Если вам нужны неметаллизированные слоты или фрезерованные проёмы в 3D-модели,
рисуйте их замкнутым контуром на `BOARD GEOMETRY/CUTOUT`.** Вырез — это граница,
которую Simple 3D экструдирует и вычитает напрямую, поэтому он надёжен. Общее
правило: всё, что должно быть отверстием в плате, обязано существовать как
замкнутый контур в подклассе CUTOUT.

**Согнутый участок — это цилиндр, а не модель поведения стека.** Поверхности
точные, и материал растягивается и сжимается как положено (см. «Сгибание гибких
плат»), но никакого расчёта того, что сгиб делает с медью, адгезивом и покровом
по отдельности, здесь нет: весь стек несёт одно отображение вокруг одной
нейтральной поверхности, положение которой задаётся `gui.foldNeutral`. Годится
для сборки, зазоров и картинки; расчёт прочности гибкого участка этим не
заменяется.

**Два сгиба, претендующих на один и тот же материал, вместе не складываются.**
Сами зоны сгиба Allegro пересекать не даёт, но материала сгиб съедает больше,
чем нарисовано в его зоне (см. «K-фактор» выше), и два сгиба могут потребовать
один и тот же миллиметр флекса. Экспорт называет оба, оставляет второй плоским
и — если сами нарисованные зоны не пересекаются — говорит, при каком
`foldNeutral` они сойдутся. Сгибы, полосы которых только соприкасаются,
складываются как обычно.

**B-rep компонентов берётся из ваших STEP-моделей библиотеки.** Размер файла
сверх самой платы определяется этими моделями; «Compact STEP (reuse component geometry)» не может
уменьшить геометрию, которая лежит внутри них.

**Тела шелкографии не объединяются в одно.** Речь про **объёмный** режим:
легенда — это тысячи пересекающихся штрихов и глифов, и булево объединение
такого количества тонких призм стоит времени солвера и делает файл *больше*
(замерено: 154%), не давая при этом ничего видимого. Поэтому каждая сторона —
компаунд отдельных тел: корректный для просмотра, экспорта и рендера, но не
единое манифолдное тело, если вы собираетесь делать булевы операции с самой
краской.

Режим **Flat** — противоположный случай, и там объединение **выполняется**:
компланарные грани на одном z рябили бы друг о друга там, где штрихи
перекрываются; объединение это убирает и заодно уменьшает файл.

**Шелкография не вычитается по отверстиям.** Обрезка идёт по контуру платы и её
вырезам, но не по сверловке. На практике легенду поверх отверстий и не печатают,
так что это заметно, только если в вашем фотошаблоне линия намеренно проходит
через отверстие.

## Командная строка (без Allegro)

```
python -m stepbuilder                                  # GUI
python -m stepbuilder STEP_DIR JSON_FILE OUTPUT_DIR    # один JSON, без окна
python -m stepbuilder STEP_DIR JSON_DIR  OUTPUT_DIR --batch   # все варианты
```

Флаги: `--batch` (json-аргумент — папка; собрать все помеченные варианты),
`--z-datum {top,bottom}`, `--color ИМЯ|r,g,b|#rrggbb`, `--rim-color ...`,
`--dated-name`, `--brd-name ИМЯ` (задаёт имя выходного файла, с датой и без;
только для одиночного json — при нескольких вариантах имя каждому даёт стем его
json), `--no-silkscreen`, `--no-silk-top`,
`--no-silk-bottom`, `--flat-silkscreen`, `--silk-flat-height ММ`,
`--silk-layer-off СЛОЙ` (можно несколько раз), `--silk-color White|Black`,
`--ignore-soldermask`, `--flat` (не сгибать плату), `--fold-anchor X,Y|auto`,
`--fold-neutral K`, `--fold-slice-angle DEG`, `--board-mode {solid,layers,inspect}`, `--no-minimize`,
`--legacy-color`, `--quiet`. Код возврата 0 при успехе, 1 при ошибке.

## Структура пакета

```
stepbuilder/
  core.py       геометрия + сборка. Без UI и print: отчёты через колбэки.
  colors.py     восемь тем платы + опции торца.
  bend.py       сгибание гибкой платы по её зонам сгиба.
  worker.py     сборка в дочернем процессе, чтобы падение не унесло окно.
  gui.py        окно tkinter. Тонкая обёртка над core.
  __main__.py   точка входа: GUI, без окна, или --gui prefill для Allegro.
```

---

## Changelog / История изменений

- **2026-07-27** — **A model file is found whatever case its name is in.** The
  name comes from Allegro's STEP mapping table, where it is typed by hand; the
  file on disk is whatever the library vendor called it. `MODEL.STEP` against
  `model.step` was an ordinary miss, reported as "could not find model.step",
  and the component was simply absent from the assembly — even though Windows
  itself cannot tell the two names apart. The search now falls back to ignoring
  case, for the whole name and not only the extension, and says in the log which
  file it used. An exact match is still tried first and always wins, so nothing
  that resolved before resolves differently.
  / **Файл модели находится в любом регистре.** Имя берётся из таблицы
  сопоставления STEP в Allegro, где его набирают руками, а файл на диске назван
  так, как его назвал поставщик библиотеки. `MODEL.STEP` против `model.step`
  было обычным промахом с сообщением «could not find model.step», и компонент
  просто отсутствовал в сборке — при том что сама Windows эти два имени не
  различает. Теперь поиск в последнюю очередь пробует без учёта регистра, причём
  для всего имени, а не только расширения, и пишет в лог, какой файл взял.
  Точное совпадение по-прежнему проверяется первым и всегда выигрывает, так что
  ничто из находившегося раньше не начнёт находиться иначе.

- **2026-07-27** — **A bend no longer flattens what curves inside it.** Where a
  board's outline runs straight into a bend area and then curves *within* it,
  the bend was built by revolving a single cross-section — exact and cheap, but
  only correct when the strip is the same shape all the way across. That was
  checked by volume, and on a real board the whole curve amounted to 0.04% of
  the strip, so it passed the check and was dropped: the model came out with a
  25 µm ledge along the edge of the flex exactly where the bend ended. The check
  now also requires the cross-section to *span* what the strip spans, to within
  a micron, and a strip that fails it is built by the general construction —
  still true cylinders, not facets. Two bends on the test board were affected;
  the reported 0.025158 mm ledge is gone.
  / **Сгиб больше не спрямляет то, что изгибается внутри него.** Там, где контур
  платы входит в зону сгиба прямым и начинает закругляться уже *внутри* неё,
  сгиб строился вращением одного поперечного сечения — точно и дёшево, но
  правильно лишь тогда, когда полоса одинакова по всей ширине. Проверялось это
  по объёму, а на реальной плате всё закругление составляло 0.04% полосы,
  поэтому проверку проходило и терялось: в модели по краю шлейфа ровно там, где
  кончался сгиб, появлялась ступенька в 25 мкм. Теперь проверка требует ещё и
  чтобы сечение **перекрывало** ту же протяжённость, что и сама полоса, с
  точностью до микрона, а полоса, которая этого не проходит, строится общим
  способом — по-прежнему истинными цилиндрами, а не гранями. На тестовой плате
  задело два сгиба; названная ступенька 0.025158 мм исчезла.

- **2026-07-27** — **Export now shows a progress meter.** Pressing *File →
  Export → Simple 3D* used to look like nothing happening: the board is read,
  the JSON written and Python started before any window appears, and Allegro's
  own Ready light stays green throughout. Allegro's progress form now comes up
  at once and names each stage — *Checking components*, *Reading the board*,
  *Checking the Python side*, *Starting the 3D window* — and closes when the 3D
  window is on its way. There is deliberately no Stop button: nothing in that
  sequence can be interrupted once it is running.
  / **Экспорт показывает индикатор выполнения.** Нажатие *File → Export →
  Simple 3D* выглядело так, будто ничего не происходит: плата читается, JSON
  пишется и Python запускается ещё до появления любого окна, а собственный
  индикатор Ready в Allegro всё это время горит зелёным. Теперь сразу
  появляется штатная форма прогресса Allegro и называет этапы — *Checking
  components*, *Reading the board*, *Checking the Python side*, *Starting the 3D
  window* — и закрывается, когда окно 3D уже в пути. Кнопки Stop намеренно нет:
  прервать эту последовательность на ходу всё равно нечем.

- **2026-07-27** — **The export no longer writes a batch file.** Launching the
  GUI and the Python pre-flight check each wrote a throwaway `.bat` — one into
  the design folder, right next to the board data, one into the install folder —
  because a design path with a space did not survive the trip through `cmd`. The
  real cause turned out to be cmd's own rule, which strips the first and the last
  quote of a `/c` command line; `start` had been blamed for it. A line that
  *begins* with `start ""` and takes its working directory from start's `/D`
  switch keeps every quoted path intact, so both files are gone: nothing
  temporary is written beside your board any more, and the tool now launches
  from a **read-only install folder** as well, which the batch file made
  impossible. The "Python did not start" diagnosis no longer reads cmd's
  localised exit code either, so it can no longer arrive as mojibake.
  / **Экспорт больше не пишет batch-файл.** Запуск GUI и предварительная
  проверка Python писали по одноразовому `.bat` — один в папку дизайна, прямо
  рядом с данными платы, другой в папку установки, — потому что путь с пробелом
  не переживал дорогу через `cmd`. Настоящей причиной оказалось правило самого
  cmd: он срезает первую и последнюю кавычку командной строки `/c`, а винили в
  этом `start`. Строка, которая *начинается* со `start ""` и берёт рабочую папку
  из ключа `/D`, доносит все кавычки в целости, поэтому оба файла исчезли: рядом
  с платой больше не появляется ничего временного, а сам инструмент запускается
  и из папки, **доступной только для чтения**, — с batch-файлом это было
  невозможно. Диагностика «Python не запустился» тоже больше не опирается на
  локализованный код возврата cmd и не может прийти кракозябрами.

- **2026-07-27** — **Two fixes found on a board rolled into a closed ring.**
  A bend whose outline had a fillet or a hair-thin sliver in it fell back to
  facets with nothing in the log but *not valid*: rebuilding the outline on the
  cylinder left corners meeting only as well as the flat solid's own vertices
  did (a couple of tenths of a micron, perfectly legal there), and
  `BRepBuilderAPI_MakeWire` joins at a fixed 1e-7 and **drops the edges it
  cannot join without reporting a failure**. Every corner is now an explicit
  shared vertex, so the wire is connected by topology and no tolerance decides
  anything. On the test board that turned two faceted bends into exact ones and
  the file from 52797 STEP entities into 35581. Second: **Allegro lays its flat
  pattern out at `k = 0`** — a bend area is `angle × radius` exactly — so on a
  board whose bend areas touch, the default `foldNeutral` of 0.5 makes two bends
  claim the same material. The log now names both bends, the numbers, and the
  `foldNeutral` that would fit; strips that merely touch are folded normally.
  Also: `--brd-name` names the output file without `--dated-name` as documented
  (it was read on the dated path only), and the exporter's per-design caches are
  cleared at the start of every export instead of surviving into the next board.
  / **Два исправления, найденные на плате, свёрнутой в кольцо.** Сгиб, в контур
  которого попадало скругление или тонкий язычок, скатывался в гранёный с
  единственной строкой *not valid* в логе: при перестроении контура на цилиндре
  углы сходились ровно настолько, насколько сходились вершины плоского тела
  (пара десятых микрона — там это законно), а `BRepBuilderAPI_MakeWire`
  сшивает по жёстким 1e-7 и **молча выбрасывает рёбра, которые не смог
  соединить**. Теперь каждый угол — явная общая вершина, проволока связана
  топологией, и никакой допуск ничего не решает. На тестовой плате два гранёных
  сгиба стали точными, а файл — 35581 сущность вместо 52797. Второе: **Allegro
  раскладывает плоскую заготовку при `k = 0`** — зона сгиба это ровно
  `угол × радиус`, — поэтому на плате, где зоны сгиба соприкасаются, умолчание
  `foldNeutral` 0.5 заставляет два сгиба претендовать на один и тот же материал.
  Лог теперь называет оба сгиба, цифры и то значение `foldNeutral`, при котором
  они сойдутся; просто соприкасающиеся полосы сгибаются как обычно. Кроме того:
  `--brd-name` задаёт имя файла и без `--dated-name`, как и написано в справке
  (раньше читался только на «датированном» пути), а кэши экспортёра сбрасываются
  в начале каждого экспорта, а не доживают до следующей платы.

- **2026-07-26** — **Flex boards are folded along their bend areas.** The bend
  line, the bend area and the undocumented `IDX_BEND_TYPE_INFO` property are
  read from the design, and the board, the printed legend and the components
  are all carried by the fold together, so nothing drifts off the surface it
  was placed on. The radius is measured from the stackup of the zone the bend
  crosses, not from the top of the board. The bend surfaces are true cylinders
  — revolved where the strip is a prism, otherwise the outline is wrapped onto
  the cylinder — with 7.5° facets left as a fallback for shapes neither
  construction fits, and the flat panels exact. *Fold flex bends* in the window,
  `--flat` on the command line, `gui.foldBends` in the config; on by default,
  and a board with no bend areas is unaffected. Intermediate format
  `format_version: 7` (the new `bends` array is optional).
  / **Гибкие платы сгибаются по своим зонам сгиба.** Линия сгиба, область сгиба
  и недокументированное свойство `IDX_BEND_TYPE_INFO` читаются из проекта, а
  плата, легенда и компоненты переносятся сгибом вместе, поэтому ничто не
  съезжает с поверхности, на которую было поставлено. Радиус отсчитывается от
  стэкапа той зоны, которую пересекает сгиб, а не от верха платы. Поверхности
  сгиба — настоящие цилиндры: вращение, если полоса призматична, иначе контур
  навёртывается на цилиндр; гранение по 7.5° осталось запасным путём для форм,
  к которым не подошло ни одно из двух. Плоские панели точные. *Fold flex bends* в окне,
  `--flat` в командной строке, `gui.foldBends` в конфигурации; включено по
  умолчанию, на плате без зон сгиба ничего не меняет. Промежуточный формат
  `format_version: 7` (новый массив `bends` необязателен).

- **2026-07-25** — **Multi-stackup and rigid-flex boards are now exported
  correctly.** Each stackup zone is read from the design with its own outline
  and thickness, and the board is built as those zones fused into one solid;
  components stand on the surface of the zone they are in. Zones are aligned on
  the conductor core, which is what they physically share — a stiffener grows
  outwards from it. Per-stackup thickness comes from Allegro rather than being
  summed by layer name, which reported zero for a flex stackup (it has no
  `SOLDERMASK` layer — coverlay and adhesive sit there). Previously such a board
  was exported as one slab of a single zone's thickness. Bends are still not
  folded: the board is exported flat. Intermediate format `format_version: 5`.
  / **Платы с мультистэкапом и rigid-flex теперь экспортируются правильно.**
  Каждая зона стэкапа читается из проекта со своим контуром и толщиной, а плата
  строится как эти зоны, сплавленные в одно тело; компоненты стоят на
  поверхности своей зоны. Зоны выравниваются по проводниковому ядру — именно оно
  у них общее, а жёсткость наращивается от него наружу. Толщина каждого стэкапа
  берётся у Allegro, а не суммируется по именам слоёв: для гибкого стэкапа такая
  сумма давала ноль (слоя `SOLDERMASK` там нет — на его месте coverlay и
  adhesive). Раньше такая плата экспортировалась одной плитой толщиной одной из
  зон. Гибы по-прежнему не сгибаются, плата экспортируется плоской. Промежуточный
  формат `format_version: 5`.

- **2026-07-25** — A model that is **stored inside the board but missing from
  disk** is now named in the log, together with what to do about it: Allegro
  keeps its own copy of every mapped 3D model inside the .brd, and Simple 3D
  builds from files on disk, so the two can disagree. Previously such a
  component produced only a bare "could not find" line, which did not
  distinguish a model that exists nowhere from one that is right there in the
  board. Intermediate format `format_version: 4` (the new `embedded_models`
  list is optional — an older file simply says nothing on the subject).
  / Модель, которая **лежит внутри платы, но отсутствует на диске**, теперь
  называется в логе вместе с указанием, что делать: Allegro хранит собственную
  копию каждой привязанной 3D-модели внутри .brd, а Simple 3D собирает из
  файлов на диске, поэтому эти два источника могут расходиться. Раньше такой
  компонент давал только сухое «could not find», по которому не отличить
  модель, которой нет нигде, от той, что лежит прямо в плате. Промежуточный
  формат `format_version: 4` (новый список `embedded_models` необязателен —
  файл постарше просто ничего об этом не сообщает).

- **2026-07-24** — The window now **reopens where you left it**, on the same
  monitor: its position and size are saved on close (`gui.windowGeometry`,
  `gui.windowState`) and restored next time, maximized included. A position
  that is no longer reachable — typically the monitor it was on has been
  unplugged — is ignored and the window is centred on the main screen, with a
  line in the log saying so. On a first run it is centred. Closing the window
  no longer leaves a pending timer that printed a Tk error to the console.
  / Окно теперь **открывается там, где вы его закрыли**, на том же мониторе:
  положение и размер сохраняются при закрытии (`gui.windowGeometry`,
  `gui.windowState`) и восстанавливаются при следующем запуске, вместе с
  развёрнутым состоянием. Недостижимая позиция — обычно монитор отключили —
  игнорируется, окно центрируется на главном экране, и в лог пишется почему.
  При первом запуске окно центрируется. Закрытие окна больше не оставляет
  висящий таймер, печатавший ошибку Tk в консоль.

- **2026-07-24** — The **STEP files** field takes several folders, one per line,
  and is now an ordered search path: the first folder holding a given model file
  wins, so a project-local folder listed above the shared library overrides
  individual models. Each folder is still searched recursively. **Add...** appends
  rather than replacing, a name found in more than one folder is reported in the
  log with the path that won, and a folder that does not exist is warned about
  and skipped instead of failing the build. Config key `gui.stepDirs` (a list).
  A settings file still holding the older single-folder `gui.stepDir` is migrated
  on first load and that key is then dropped, so the two never coexist. CLI:
  the positional folder accepts a `;`-separated list and `--step-dir` adds more.
  / Поле **STEP files** принимает несколько папок, по одной на строку, и стало
  упорядоченным путём поиска: побеждает первая папка, где есть нужный файл, —
  так проектная папка выше общей библиотеки переопределяет отдельные модели.
  Каждая по-прежнему просматривается рекурсивно. **Add...** дописывает, а не
  замещает; имя, найденное в нескольких папках, отмечается в логе с победившим
  путём; несуществующая папка вызывает предупреждение и пропускается, а не
  роняет сборку. Ключ конфигурации `gui.stepDirs` (список). Файл настроек, где
  ещё лежит старый ключ на одну папку `gui.stepDir`, переносится при первой
  загрузке, после чего этот ключ удаляется — вдвоём они не сосуществуют. CLI:
  позиционный аргумент принимает список через `;`, а `--step-dir` добавляет ещё.

- **2026-07-24** — Mechanical symbols that carry a STEP model
  (`PKGDEF_STEP_FILE`) but no reference designator are now exported; before, the
  export list was gated on the reference designator and such parts were dropped
  silently. Their instances are keyed internally as `<SymbolName>_MECH1`,
  `_MECH2`, … `NO_STEP_EXPORT` and the variant rules apply to them unchanged.
  SKILL-only change; the STEP output for boards without such parts is identical.
  / Механические символы, несущие STEP-модель (`PKGDEF_STEP_FILE`), но без
  позиционного обозначения, теперь экспортируются; раньше список на экспорт
  фильтровался по позиционному обозначению, и такие детали молча терялись. Их
  вхождения ключуются внутри как `<ИмяСимвола>_MECH1`, `_MECH2`, … Правила
  `NO_STEP_EXPORT` и вариантов действуют для них без изменений. Изменение только
  в SKILL; для плат без таких деталей STEP-файл идентичен прежнему.

- **2026-07-23** — Silkscreen layers are now chosen in the GUI instead of by
  editing the config (intermediate format `format_version: 3`): the exporter
  collects every layer the config lists and tags each polygon with the layer it
  came from, so a **Silkscreen layers** panel offers them as ticks — with
  polygon counts, the two sides side by side — and the choice applies on the
  next Generate with no re-export. Silkscreen gained separate **Top** and
  **Bottom** checkboxes, which grey out their side's layers without changing
  them, and a **Flat** mode that draws the legend as surfaces for about a
  quarter of the file size (`gui.silkscreenFlatHeight` lifts them clear of the
  board so the two planes do not flicker). Mechanical components are exported
  even though `Variants.lst` may not list them, and any symbol carrying
  `NO_STEP_EXPORT` is left out and named in the log. Zero-width lines and text
  are reported by layer and position instead of vanishing. Every user setting
  moved into `simple3d_config.json`, read by both halves of the tool, and the
  GUI now refuses to rewrite a settings file it could not read. Allegro console
  messages carry a severity, so warnings print in Allegro's warning color and
  errors in red. / Слои шелкографии теперь выбираются в окне, а не правкой
  конфига (формат `format_version: 3`): экспортёр собирает все слои из конфига
  и помечает каждый полигон его слоем, поэтому панель **Silkscreen layers**
  предлагает их галочками — с числом полигонов, стороны рядом, — и выбор
  применяется по кнопке Generate без повторного экспорта. У шелкографии
  появились отдельные галочки **Top** и **Bottom**, которые делают слои своей
  стороны серыми, не меняя их, и режим **Flat**: легенда рисуется
  поверхностями и занимает вчетверо меньше (`gui.silkscreenFlatHeight`
  приподнимает их над платой, чтобы плоскости не рябили). Механические
  компоненты экспортируются, даже если их нет в `Variants.lst`, а любой символ
  со свойством `NO_STEP_EXPORT` исключается и называется в логе. Объекты
  нулевой ширины сообщаются с указанием слоя и координат вместо тихого
  исчезновения. Все пользовательские настройки переехали в
  `simple3d_config.json`, который читают обе половины инструмента, а GUI больше
  не перезаписывает файл настроек, который не смог прочитать. Сообщения в
  консоли Allegro несут уровень важности: предупреждения выводятся цветом
  предупреждений Allegro, ошибки — красным.

- **2026-07-22** — Silkscreen export (intermediate format bumped to
  `format_version: 2`). The legend is collected in Allegro as filled polygons
  (`axlPolyFromDB`, text through `axlText2Lines`), clipped to the board outline
  minus its cutouts, and extruded into thin solids — 25 µm by default — as two
  separate parts, `silkscreen_top` / `silkscreen_bot`. Which layers count, the
  ink thickness, the clip and the end-cap style live in the new
  `simple3d_config.json`; a missing or broken config falls back to built-in
  defaults. GUI gained an **Export silkscreen** checkbox and a White/Black ink
  dropdown with a swatch; CLI gained `--no-silkscreen` and `--silk-color`.
  Silkscreen is deliberately identical across assembly variants, because the
  bare board is manufactured once for all of them. Also fixed: a board where no
  component has a STEP mapping used to fault while writing the JSON. /
  Экспорт шелкографии (промежуточный формат поднят до `format_version: 2`).
  Легенда собирается в Allegro как залитые полигоны (`axlPolyFromDB`, текст
  через `axlText2Lines`), обрезается по контуру платы за вычетом вырезов и
  выдавливается в тонкие тела — по умолчанию 25 мкм — двумя отдельными деталями,
  `silkscreen_top` / `silkscreen_bot`. Какие слои считать шелкографией, толщина
  краски, обрезка и тип торца линии вынесены в новый `simple3d_config.json`;
  отсутствующий или сломанный конфиг откатывается на встроенные значения. В GUI
  добавлены галочка **Export silkscreen** и список цвета White/Black с образцом,
  в CLI — `--no-silkscreen` и `--silk-color`. Шелкография намеренно одинакова во
  всех вариантах сборки, потому что текстолит производится один раз под все.
  Попутно исправлено: плата, у которой ни у одного компонента нет STEP-модели,
  падала при записи JSON.

- **2026-07-19** — MFRPN commented out everywhere (SKILL read + JSON field,
  Python option, GUI checkbox, CLI flag) — the property read was unreliable;
  the code is kept, disabled, for a future re-enable. The board part is now
  named `PCB_<board>` instead of a bare `PCB`, so several boards no longer
  collide in one CAD session. Under `symbols_top`/`symbols_bot` the model parts
  are placed directly (instance named after its STEP file), dropping the
  per-refdes wrapper sub-assemblies. GUI: the board-color swatch now sits next
  to its dropdown. / MFRPN закомментирован везде (чтение в SKILL и поле JSON,
  опция Python, галочка GUI, флаг CLI) — чтение свойства работало ненадёжно;
  код оставлен отключённым на будущее. Деталь платы теперь называется
  `PCB_<плата>`, а не просто `PCB`, чтобы несколько плат не конфликтовали в
  одной сессии CAD. Под `symbols_top`/`symbols_bot` детали моделей размещаются
  напрямую (вхождение с именем своего STEP-файла), без обёрток-подсборок на
  каждый рефдес. GUI: квадрат цвета платы теперь стоит рядом со своим списком.

- **2026-07-19** — Consolidated into a single self-contained folder (`…\Scripts\Simple3D\`): `S3D_ScriptDir`, both `load()` lines and every install path now point at that one folder; package tree corrected (no `__init__.py` — it runs as a namespace package); the two README files merged into this one, keeping the disclaimer. / Всё сведено в одну самодостаточную папку (`…\Scripts\Simple3D\`): `S3D_ScriptDir`, обе строки `load()` и все пути установки теперь указывают на неё; дерево пакета исправлено (без `__init__.py` — работает как namespace-пакет); два README объединены в один, дисклеймер сохранён.

- **2026-07-19** — Review pass: browsing to a different JSON after an Allegro
  prefill now builds exactly what the field shows (jobs are resolved at
  Generate time, no cached queue); with several variants each output keeps its
  variant name even when `--brd-name` is given; dated-name logic unified into
  one shared helper; JSON marker keys uniformly indented; stale
  `S3D_DefaultModelDir` row removed from this README; `--batch`/`--quiet` added
  to the flags list. / Ревью: выбор другого JSON через Browse после запуска из
  Allegro теперь собирает ровно то, что в поле (задания разрешаются в момент
  Generate, без кэшированной очереди); при нескольких вариантах каждый файл
  сохраняет имя варианта даже с `--brd-name`; логика датированного имени
  сведена в один общий хелпер; ключи маркера JSON выровнены; из README убрана
  устаревшая настройка `S3D_DefaultModelDir`; в список флагов добавлены
  `--batch`/`--quiet`.

- **2026-07-18** — Colored log (orange warnings, dark-red errors); JSON format
  marker so foreign `.json` files are ignored; rim-color fix (was landing on a
  flat face); documented `ncroute_path` and multi-stackup limitations; settings
  switched from `defvar` to `=`; self-deleting launch batch; console-less
  `pythonw` launch. Bilingual README created.

