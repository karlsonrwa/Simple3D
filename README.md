# Simple 3D — Allegro → STEP exporter

Exports an Allegro PCB — board solid, cutouts, holes, component models,
silkscreen, rigid-flex zones and folded bends — into one STEP assembly, from a
menu item and a small window.

[English](#english) · [Русский](#русский) · Quick start: `QUICKSTART.md` ·
Changes: `CHANGELOG.md`

<a name="english"></a>

# ⚠️ Disclaimer

Everything in this repository has been created through vibe coding with Claude.
I am not a professional software developer. My background is in hardware engineering, and this project exists solely because I wanted to solve problems I encountered in my own workflow.
I am not proficient in either Python or SKILL. Instead, I focus on clearly defining the behavior I expect from the tool and iteratively refining it until it does what I need.
If you find a bug, an issue, or have an idea for improvement, please feel free to open an Issue or submit a Pull Request. I will do my best to investigate and fix it, but I cannot promise a quick response.
Although this project was developed using an AI-assisted workflow, I make an effort to validate the generated code in real-world use and rely on this tool in my own projects.

## Why this exists

Allegro's own `File → Export → 3D` is heavyweight: it pulls the full MCAD
bridge, writes large files, and wants the models mapped through the whole 3D
workflow. For "does this board fit the enclosure" and "do these tall parts
clash", that is more than you want.

Simple 3D is the lightweight alternative: one board solid at the true finished
thickness, the placed component models reused so the file stays small, and a
flat assembly tree that imports cleanly into SolidWorks, Inventor or Creo.

It grew out of [`exportStep` by juulsA](https://github.com/juulsA/exportStep),
whose SKILL exporter and OpenCASCADE builder are the foundation here. The C++
builder was ported to Python — same kernel, no compiler or DLLs — a number of
bugs were fixed, and the features below were added.

## How it works

```
File → Export → Simple 3D          (simple3d.il, inside Allegro)
   │  1. finds  rev/cad  (sibling of  rev/pcb ), or writes beside the .brd
   │  2. writes one JSON per variant into it, tagged "format": "simple3d"
   │  3. checks that Python can start, and says so if it cannot
   └─ 4. opens the window with the paths filled in
            └─ <board>_simple_DD_MM_YYYY.step
```

The two halves talk through that JSON because neither can do the other's job:
SKILL reads the Allegro database but cannot build B-rep, OpenCASCADE builds
STEP but knows nothing about Allegro. Everything the export decides in Allegro
is in the file, so the model can be rebuilt — differently — without touching
the board again.

The exporter writes `format_version: 12` (10 added the optional `pads` object
the *Exposed copper* are drawn from; 11 adds each padstack's mask openings to it,
so a pad shows only what its opening exposes). Every earlier version still builds —
each version only ever *added* something optional — so an intermediate you kept
from an older release does not have to be re-exported to be used. The other
way round is new with 9: it keeps the components under one `"components"`
key instead of beside the metadata, so a file this release writes needs this
release's Python (an older `stepbuilder` would see one component named
`components`).

Allegro's own progress form is on screen from the moment you press Export,
because all of the above happens before any window of ours appears. The only
temporary file is the pre-flight check's log, `_simple3d_preflight.txt`, written
into the output folder and deleted as soon as it has been read.

## Installation

**1. Python 3.10+** from python.org, with *Add Python to PATH* ticked. `tkinter`
comes with the standard Windows installer.

**2. One dependency:**

```
pip install cadquery-ocp
```

That is the OpenCASCADE kernel with Python bindings, and it is the entire
`requirements.txt` — but it is not small: with VTK, which it declares as a hard
dependency, the three come to about **470 MB on disk**.

**If there is more than one Python on the machine**, know which one that `pip`
belonged to. `python` and `pythonw` are *names*, and PATH decides what they mean
today: an installer that brings its own Python — the node.js setup does, via
Chocolatey, and it installs into the machine PATH, which comes *before* your
per-user one — can put a fresh interpreter in front of yours. The packages are
then missing because it is a **different interpreter**, not because anything was
uninstalled. Pin the one you meant, by full path, in the `allegro` section of
`simple3d_config.local.json` (yours, gitignored, never touched by an update):

```json
"allegro": {
    "python":  "C:/Python312/python.exe",
    "pythonw": "C:/Python312/pythonw.exe"
}
```

The pre-flight check prints the interpreter that actually answered — path and
version — so the console says which one you got.

**3. The files.** Clone or unpack the repository; its root already is the layout
the tool expects — the two `.il` files, `simple3d_config.json` and the
`stepbuilder\` package in **one folder**, anywhere you like:

```
d:\Projects\OrCAD\Scripts\Simple3D\
├── makeVariant3dIntermediates.il     SKILL exporter (reads the board)
├── simple3d.il                       menu item + launcher; loads the exporter
├── skill\                            the exporter's ten parts (s3d_*.il)
├── simple3d_config.json              all settings, both halves read it
└── stepbuilder\                      the Python package
```

Downloading as a ZIP from GitHub wraps everything in `Simple3D-main\`. Either
unpack its *contents*, or point `SIMPLE3D_DIR` (below) at the wrapper — but do
not leave it and the `load()` lines disagreeing.

Check it from a `cmd`:

```
cd /d d:\Projects\OrCAD\Scripts\Simple3D
python -m stepbuilder
```

The window should open and its log should say `Settings loaded from …`.

**4. Load the SKILL files** from `allegro.ilinit`, or by hand each session:

```
load("d:/Projects/OrCAD/Scripts/Simple3D/simple3d.il")
```

`File → Export → Simple 3D` appears. One line: `simple3d.il` loads the exporter
itself (`makeVariant3dIntermediates.il`, which loads its ten parts from
`skill\`). The older pair of `load()` lines, the exporter first, keeps working.

**Nothing in the shipped files needs editing to match your machine** — and that
is deliberate: they are under version control, so a path written into one of
them is one installation's path shipped to everyone, and overwritten in
everyone's working copy by the next update.

Where the tool is installed is the one thing it cannot read from its own
config, since that is what *finds* the config. It comes from, in order:

1. **`SIMPLE3D_DIR`, in your own Allegro environment file** (`%HOME%\pcbenv\env`),
   which no update touches:

   ```
   set SIMPLE3D_DIR = d:/Tools/Simple3D
   ```

2. **the folder `simple3d.il` was loaded from**, when SKILL will say. Costs you
   nothing when it works; it is second because it rests on core-language names
   this project has not verified against Allegro, so it can be a fallback and
   never the only answer.

The console names which one answered. If neither does, the tool says so and
refuses to run rather than guessing — it would not find its own Python package
anyway.

**Your model folders go in the window** (*STEP files*), or in
`simple3d_config.local.json`. The tracked config ships with none for the same
reason.

## The window

Most controls say what they do. These are the ones worth knowing about:

| Control | What to know |
|---|---|
| **STEP files** | The model folders, one per line, **searched in order** — the first folder holding a given file wins, so a project-local folder above the shared library overrides individual models. Each is searched recursively. A name found twice is reported with the path that won. |
| **JSON file** | One intermediate, or a folder of variants — then every one of them is built. Only files tagged `"format": "simple3d"` are touched; anything else in the folder is ignored and logged. |
| **Z = 0 at** | Which face is the datum. Parts sit on the **soldermask** of their side, because real pads carry solder that lifts the part to mask level. |
| **Board edge color** | Only *Solid* has one uniformly colored body for a rim to contrast with, so this greys out in the other two stitchings rather than being silently ignored. |
| **Body stitching** | How the body is put together, **on any board** — an ordinary one has no zones, so its outline becomes one implicit zone on its single stackup. *Solid* — one body, smallest. *Solid colored layers* — one body whose layer interfaces survive, so the rim shows the stack (~4.7× larger). *Not stitched* — every layer of every zone its own part, for taking the board apart by eye. The last two need the stackup layers: an intermediate written by an older version says so in the log and falls back to one solid. |
| **Do not include soldermask** | Leaves the mask out and closes the stack up toward the core by exactly what was removed, each side independently. The board really does get thinner — check the total. |
| **Silkscreen: Top / Bottom** | Both off skips the legend entirely and makes a noticeably smaller file. |
| **Make surface** | The legend as surfaces rather than thin solids: about a quarter of its file size. The ink then has no thickness and cannot be used in boolean work. |
| **Silkscreen layers** | A tick per layer *found in this JSON*, with its polygon count. Untick and press Generate again — no re-export needed. |
| **Fold flex bends** | Fold along the bend areas. Off exports the board flat. Does nothing on a board without them. |
| **Exposed copper (as surfaces)** | The copper of every pin's pad on the two outer faces, as copper-coloured surfaces two microns above the mask — so the model reads as a board with its pads, not a plain slab. Nothing is cut into the board: no boolean, and the board stays one solid. One shared face per pad figure, instanced per pin, so a pad costs a placement in the file rather than a body. Only what the mask opening exposes is drawn: a solder-mask-defined pad shows its opening's shape, a pad with no opening shows nothing, an untented via its ring, a tented one nothing. Openings drawn on the `SOLDERMASK` layers add the copper under them, one flat part per side. Needs a JSON written with `format_version` 12 (11 has no vias and nothing under drawn openings, 10 draws the copper whole, an older one draws none; the log says which). See *Exposed copper*. |
| **Mask openings (as surfaces)** | The solder-mask openings as surfaces in the dielectric's colour (`base` in *layerColors*): every pin's and via's opening from its padstack, instanced like the pads, and every opening drawn on the `SOLDERMASK` layers — a line, a shape or rectangle, a text. With *Exposed copper* on, what the copper leaves of each opening: the ring around a copper-defined pad, the laminate a label cut into the mask shows; on its own, the openings whole. Needs a JSON written with `format_version` 11 for the padstacks' openings, 12 for the drawn ones. See *Exposed copper*. |
| **Compact STEP** | Drops parametric surface curves — roughly half the file, identical geometry. |
| **Build the full-board file too** | With a folder queued, whether the batch also builds `<board>.json` — the whole board, variants ignored (`settings.exportFullBoard` is what writes it). A file you point at directly is always built: choosing it is choice enough. |
| **Generate** / **Cancel** | While a build runs every other control is greyed out — a snapshot of the settings has already been taken, so changing them mid-build would only look as if it did something — and this button becomes **Cancel**. Cancelling kills the build outright, which is the only thing that works on a boolean that has been inside OCCT for a minute; the file being written at that moment may be left incomplete, and the log says so. |

The log is color-coded: orange warnings, dark red errors, green on success. The
progress bar covers the whole build and the line beside it says which stage.

**The build runs in a child process.** OpenCASCADE can die outright rather than
raise an exception, and a boolean over a difficult board occasionally does; in a
thread that would close the window with nothing written anywhere. Instead the
window survives, reports the exit code, and suggests what usually gets a board
through — *Not stitched*, which fuses nothing, or a coarser fold slice angle.

## Settings

Everything lives in **`simple3d_config.json`**, beside the two `.il` files.
Both halves read it: SKILL takes `allegro`, the window takes `gui`, the exporter
takes `silkscreen` and `settings`.

**Two files, and only one of them is yours.** The tracked
`simple3d_config.json` holds the shipped defaults; beside it,
**`simple3d_config.local.json`** holds whatever this installation does
differently — your model folders above all. The two are merged on read, key by
key, with the local one winning, and **the window writes only the local file**,
only where a value differs from the default.

That is what makes an update safe: it can neither conflict with your paths nor
overwrite them, improved defaults still reach you, and no absolute path or
window position lands in a commit. You do not have to create the file — the
window writes one the first time it closes; delete a key from it to go back to
the shipped default.

**If either file cannot be read — missing, or edited into invalid JSON —
nothing is written back for the rest of the session**, even if you repair it
while the window is open. The fields on screen are defaults at that point, not
your settings, and saving them would overwrite the file you just fixed. The log
names both files on every start.

The keys worth setting by hand — the rest mirror controls in the window:

| Section | Key | What it does |
|---|---|---|
| `allegro` | `python` / `pythonw` | The interpreter. `pythonw` opens the window with **no console**; `""` falls back to `python`. |
| | `menuLabel` / `commandName` | Menu text and command name. Read at load time, so a change needs a SKILL reload. |
| | `defineAlwaysExportProp` | Create the **`ALWAYS_STEP_EXPORT`** property in the open design's property dictionary — when a board is opened and before every export — so it can be attached from Allegro's own Properties dialog. A part carrying it stays in every variant. Defining it is a change to the board, so `false` leaves every design untouched; the export still reads the property wherever it is already defined. See *What gets exported*. |
| `gui` | `stepDirs` | The model folders, in search order (see the table above). |
| | `boardMode` | `solid` / `layers` / `inspect` — the *Body stitching* control. |
| | `layerColors` | Color per layer kind (`copper`, `base`, `coverlay`, `adhesive`, `stiffener`, `soldermask`, `other`). The defaults are **Allegro's own material colors**, so the export looks like the same board does in Allegro's 3D canvas. |
| | `foldAnchor` | The point that stays in the XY plane, `[x, y]`. **`[0, 0]` by convention** — see *Folding*. `"auto"` holds the largest piece instead. |
| | `foldNeutral` | Where the neutral axis sits, as a fraction of thickness (default `0.5`). **Set it to `0` on a board whose bend areas touch** — see *Folding*. |
| | `foldSliceAngle` | Arc per slice for a bend that has to be faceted (default `7.5`). Bends built as true cylinders ignore it. |
| | `exposedCopper` | The *Exposed copper* checkbox: the pads' copper on the outer faces, as surfaces. Off by default. See *Exposed copper*. |
| | `maskOpenings` | The *Mask openings* checkbox: the solder-mask openings as surfaces in the dielectric's colour — what the copper leaves of them when both are on. Off by default. See *Exposed copper*. |
| | `exportFullBoard` | With a `Variants.lst` present, also write `<design>.json` — the whole board with variants ignored (`NO_STEP_EXPORT` still applies). See *What gets exported*. |
| `settings` | `exportPads` | Whether the export **collects** the pads into the intermediate at all (on by default). Whether they are *drawn* is the checkbox, per build. Off saves the collection on a board where they are never wanted. |
| | `negativeLayers` | Stackup layers whose drawn shapes are **openings** rather than material, matched as a case-insensitive substring. Coverlay, soldermask and pastemask are drawn that way by convention; stiffener, adhesive and epoxy are the opposite. Add a layer here if its bodies come out inverted — and **take one out** if a board draws it as material: Allegro's 3D Canvas guide says a coverlay is read as negative and that *"coverlays specified as positive shapes are not rendered in 3D canvas"*, so such a board exists and Allegro's own 3D just omits the layer. The log names the layer when its openings leave nothing of it in a zone. Decided at export time, so changing this needs a re-export. |
| `silkscreen` | `top` / `bottom` | Which Allegro layers are **collected** — see *Silkscreen*. |
| `soldermask` | `top` / `bottom` | Which layers hold **drawn mask openings** — a line or a shape there exposes the copper under it, computed at export. `BOARD GEOMETRY` and `PACKAGE GEOMETRY / SOLDERMASK_*` by default; add `MANUFACTURING/SOLDERMASK_*` or a site layer if your footprints draw their openings there. See *Exposed copper*. |

The rest of `gui` mirrors the window and is written back when it closes —
`zDatum`, `boardColor`, `boardEdge`, `boardEdgeCustom`, `silkscreenTop`,
`silkscreenBottom`, `silkColor`, `silkscreenFlat`, `ignoreSoldermask`,
`foldBends`, `minimizeFileSize` — plus five that are worth a word each:

* `silkscreenFlatHeight` — mm between the board face and a **flat** legend, so
  the two are not coplanar and do not flicker. Default `0.001`. Not the ink
  thickness; that is `settings.silkscreenThickness`, and it applies to solid
  mode only.
* `buildFullBoard` — whether a queued **folder** also builds the whole-board
  file. The checkbox above.
* `silkscreenLayersOff` — **exclusions, not inclusions**, so a layer that turns
  up on a board for the first time is drawn rather than silently missing.
* `jsonFile`, `outputDir` — the last paths you picked **in the window**. An
  export launched from Allegro fills those fields but does not record them:
  they describe a board, not a preference.
* `windowGeometry`, `windowState` — where the window was and whether it was
  maximized, so on a multi-monitor desk it comes back on the same screen. A
  position that is no longer reachable is ignored and the window is centred.

Two keys are read but never written, so a config from an older build keeps
working: `stepDir` (one folder, superseded by `stepDirs`) and `debugLayers`
(superseded by `boardMode`). Each is migrated on load and dropped on save; do
not add them by hand.

## What gets exported

Every symbol that has a reference designator, plus any symbol carrying a STEP
model (`PKGDEF_STEP_FILE`) without one — a bracket or a housing placed straight
onto the board — minus two exclusions.

**`NO_STEP_EXPORT` wins over everything.** Attach it to a symbol, or to a
component or component definition to drop every instance of a part, and it stays
out of the model even if the variant installs it. Each one is named in the
console.

**The variant list governs everything that has a reference designator.** A
refdes is exactly what makes a part nameable in a `Variants.lst`, so mechanical
parts with one — a housing sitting on a connector — obey the list like any other
component: **absence from the list is the list saying "not installed"**, and the
part is left out unless it carries `ALWAYS_STEP_EXPORT`.

**A symbol with no reference designator is outside the variant system** and is
exported in every variant. Allegro leaves the refdes empty when there is no
associated component, so such a part can never be named in a list generated from
the schematic — nothing there can say anything about it, and `NO_STEP_EXPORT` is
the only thing that removes it.

**`ALWAYS_STEP_EXPORT` is the way out of that rule.** A part carrying it stays
in every variant whatever the list says; `NO_STEP_EXPORT` still outranks it,
because *never* beats *always*.

It exists because of a case the data cannot settle: a **wire-solder pad** and a
**connector housing** are identical in the database — refdes, a STEP model, no
BOM line, named in no variant — but the housing should vanish with its
connector, while the pad belongs to the *bare board* and so to every variant. On
a drawing of a board with no silkscreen, those pads are what the fitter needs to
see. The difference is intent, so it is written on the part.

Unlike `NO_STEP_EXPORT`, which is one of Allegro's own, **this property does not
exist until something creates it**, and until it is defined nothing can attach
it. So `simple3d.il` defines it as a BOOLEAN user property and stays out of the
way: what it goes on is yours to decide, through **Edit → Properties**. Four
consequences:

* A property dictionary belongs to a **design**, not to the installation, so the
  entry is created per board: on Allegro's `open` trigger and again at the top of
  every export. Loading the SKILL files does nothing at all — a version that
  wrote at load time coincided with Allegro crashing on startup.
* **A name is not a board.** Allegro sometimes starts on an empty placeholder
  rather than a design; nothing is written to one, and the export says so.
* Defining it **changes the board**, so Allegro will want it saved. Set
  `allegro.defineAlwaysExportProp` to `false` to stop that; the export still
  reads the property wherever it is already defined.
* A BOOLEAN property has **no value** — it is there or it is not, which is the
  test the export makes. To un-mark a part, *delete* the property rather than
  setting it false. Allegro says the same if you try.

Attach it to a **component definition** to cover every instance of a library
part at once: mark the pad in the library, and no board needs touching again.

**The whole board, variants ignored.** With a `Variants.lst` present the export
also writes **`<design>.json`** — every component except those marked
`NO_STEP_EXPORT`, with the variant list taking nothing away. A drawing sometimes
has to show what is on the bare board rather than what one assembly installs,
and that is a different question from `ALWAYS_STEP_EXPORT`: the property answers
it part by part, this file answers it for the whole board at once. It carries
`"full_board": true`, which is how the window names it in the queue — telling
`<design>.json` from `<design>_<variant>.json` by name alone is a guess, and a
variant may be called anything. Its STEP comes out as
`<design>_simple_DD_MM_YYYY.step`. `settings.exportFullBoard: false` stops it
being written; the **Build the full-board file too** checkbox decides whether a
queued folder builds it.

`Variants.lst` is read **from the folder holding the `.brd`**, which is where
Allegro keeps it, and nowhere else; the console names the path it tried when
there is nothing there. With one present, the export writes **one JSON per
variant**, named `<design>_<variant>`, and the window builds every one of them.
**Another project's file** (plenty of refdes, none of them on this board) is
refused rather than exported quietly. A variant that **installs nothing** —
every part set to *not installed* in the schematic, so Capture writes no base
list at all — is exported as the **bare board**: the outline, the silkscreen
and the symbols that have no refdes, with a warning in the console saying so
(a stub `"dummy"` file left from another project looks the same, and the
warning is for that case). The ordinary case prints its coverage: `variant
list covers 47 of 51 placed component(s)`. A refdes the list names that is
**not placed** on the board is reported per variant — `variant BOM lists 4
component(s) that are not on this board: VT1, VT2, VT3, VT4` — in the console
and again in the window's log: the list then describes a different revision
of the board than the one open.

A variant may also override properties on individual components, as a block
after its base list. Those components **are** installed in that variant — they
are simply built from a different part — so they are exported with it, and only
with it.

### When a model is not in the assembly

Allegro keeps its own copy of every mapped model **inside the .brd**, and Simple
3D does not use those copies — it builds from files on disk. So a board can look
complete in Allegro's 3D view while a component is missing here. The three cases
are told apart, because the fix differs:

* **Missing, and stored in the board.** Export the board from Allegro's 3DX
  canvas, take the model files out of that export, put them in any folder listed
  under *STEP files* (the board's own folder travels with the design), run again.
* **Missing, and not in the board.** There is no copy to recover; the file has
  to come from wherever the library keeps it.
* **On disk but unusable** — locked by another application, zero bytes from a
  transfer that failed, a dialect OpenCASCADE declines. Reported with the reason
  and the path; that component is left out and **the rest of the board is still
  built**.

The case of a filename does not matter. The name comes from Allegro's mapping
table, where it is typed by hand, and the file on disk is named by whoever
supplied the library, so `MODEL.STEP` and `model.step` are the same file here —
as they are to Windows itself. An exact match is always preferred.

## Assembly structure

```
<board_name>
├── PCB_<board>             one solid at the finished thickness
├── silkscreen_top_<board>  printed legend, top   (only if enabled and present)
├── silkscreen_bot_<board>  printed legend, bottom
├── pads_top_<board>        copper pads, top      (only with Exposed copper ticked)
│   ├── pad_S_RCT_1-00_X_0-95_TOP   one face per pad figure, named after the padstack and layer
│   └── pad_S_RCT_1-00_X_0-95_TOP   the same face instanced again, per pin
├── pads_bot_<board>        copper pads, bottom (a mirrored figure carries an m: pad_…_TOPm)
├── copper_top_<board>      copper under the drawn mask openings, top  (Exposed copper; one part per side, like a flat legend)
├── copper_bot_<board>      the same, bottom
├── openings_top_<board>    mask openings, top    (only with Mask openings ticked; the dielectric's colour)
│   └── opening_S_RCT_1-00_X_0-95_SOLDERMASK_TOP   one face per opening figure, instanced per pin - what the copper leaves of it when both are on
├── openings_bot_<board>    mask openings, bottom
├── bare_top_<board>        drawn openings as laminate, top   (Mask openings: what the copper leaves of them, or whole)
├── bare_bot_<board>        the same, bottom
├── symbols_top_<board>     top-side components
│   ├── cap_D8x10mm         part, named after its STEP file, placed in situ
│   └── cap_D8x10mm         the same part instanced again if the model repeats
└── symbols_bot_<board>     bottom-side components
```

* One **part** per distinct STEP model, named after the model file. Ten
  identical resistors cost one solid, not ten.
* The model parts sit **directly** under the two groups, with no per-refdes
  wrapper: each entry is an instance carrying its file's own name.
* **Every top-level node carries the board name**, never a bare `PCB` or
  `symbols_top`, so importing several boards into one CAD session cannot let one
  board's part or group silently substitute another's.
* Each **silkscreen side is its own part**, so it can be hidden or recolored
  without touching the board.
* The **copper pads are two groups**, top and bottom, of instances of shared
  faces — one face per (padstack, layer, mirrored), named after them — so they
  can be hidden as a whole and cost a placement per pin.

## Silkscreen

Both sides are built by default, as real geometry: filled regions, either
extruded into thin solids standing on the board face or drawn as flat surfaces
just clear of it.

**Widths, glyphs and curves are Allegro's own.** A silkscreen line is a
centreline plus a width, and turning that into a filled outline is
`axlPolyFromDB`'s job, with text vectorised through `axlText2Lines` first.
Nothing is stroked or offset by hand, so what lands in the STEP is the geometry
that goes to the Gerber. Every polygon is then checked against the area Allegro
reported for it, so a curve rebuilt the wrong way round cannot pass silently.

**The legend is the same for every assembly variant.** The bare board is
manufactured once and serves all of them, so the legend of a component that is
not installed is still physically printed. It is collected once per design.

Which Allegro layers are **collected** is set in the config, so edit that rather
than the source if your naming differs:

```json
"silkscreen": {
    "top":    [ "BOARD GEOMETRY/SILKSCREEN_TOP", "REF DES/SILKSCREEN_TOP", … ],
    "bottom": [ "…/SILKSCREEN_BOTTOM", … ]
},
"settings": {
    "exportSilkscreen": true,      // collect it at all
    "silkscreenThickness": 0.025,  // ink thickness, mm — solid mode only
    "clipToBoardOutline": true,    // trim to the outline minus every cutout
    "endCapType": "ROUND"          // line ends, as Allegro plots them
}
```

Which of the collected layers reach the model is decided **per build** in the
window, from a list built out of the JSON — so it only ever offers layers that
produced geometry on this board, with the polygon count each one costs. A layer
left out of the config lists is never collected and cannot be ticked back on
without re-exporting: keeping an expensive layer out (reference designators
vectorise every glyph) saves collection time, keeping it in buys the choice.

A line with no width, or text with a zero pen width, cannot be plotted — the
artwork has nothing to draw with either — so it is skipped and reported by layer
and position, in the Allegro console and in the window's log both, because the
console has usually scrolled past by the time you look at the model.

**Solid or flat.** Flat is about a quarter of the size, and its faces are
unioned — coplanar faces at one z flicker against each other where strokes
overlap. Solid mode deliberately does **not** union: a boolean over thousands of
thin overlapping prisms costs solver time and makes the file *larger* (measured
at 154%) while buying nothing visible. So a solid legend is a compound of
separate solids: correct to look at, export and render, but not one manifold
solid if you mean to do boolean work on the ink.

## Exposed copper

Off by default; tick **Exposed copper (as surfaces)** for a model that reads as a
board with its pads rather than as a green slab. The copper of every pin's pad
is drawn on the two outer faces as a surface in the copper colour of
`layerColors`, two `silkscreenFlatHeight`s above the mask — the way a flat
legend sits on it, one step higher (the *Mask openings* take the first step,
so where a window overlaps a neighbouring pad's copper the copper is on top).
That is the whole construction: **nothing is cut into the board.** A window per pad cut through the mask and a body per pad set into it
would be a boolean over thousands of prisms — minutes of solver time on a dense
board and a real chance of an empty result — for a picture that cannot tell a
flush pad from a face one micron above it.

**One face per figure, instanced per pin.** A padstack's pad is built once —
per layer, and once more mirrored for the pins on the underside — and every pin
that uses it is an instance of that face with its own position and rotation,
the way ten identical resistors share one model. So a pad costs a placement in
the file, not a face: measured on Cadence's demo board, 2982 pads on 85
figures for 2.1 MB — the same faces written one by one come to 5.9 MB — and
five seconds more on a three-minute build. Which
face a pin reaches is decided by its **own layer span** against the outer
copper of its zone — a surface pin on `INNER1` in a flex zone whose outer copper
*is* `INNER1` draws on that zone's top face, a through pin spanning the flex
core draws on both flex faces, and a pin that reaches no outer face of its zone
draws nothing and is counted in the log. A mirrored pin's figure is mirrored
before it is turned, and a mirrored through pin wears its padstack's stack
backwards, as Allegro places it.

**The outline is Allegro's own.** For every pad on an etch layer the exporter
walks the path the padstack holds for it — a circle, an oblong, a rounded or
chamfered rectangle, an octagon or a *Shape* pad all carry one — and writes it
in the same segment / arc / circle vocabulary as the board outline, so no
figure kind is interpreted anywhere. A corner arc is rebuilt **through its two
end points** rather than on its centre: Allegro keeps an arc's centre only to
the design's resolution, and an arc rebuilt on its radius can miss the next
line by a fraction of a micron — enough to leave a rounded rectangle open and
undrawn. A through pad keeps its drill hole, as an annular ring; a donut its
inside diameter; a mounting hole whose nominal pad is smaller than its drill
draws nothing, quietly. Every placed pad on five real boards — 54 000
placements, offset, mirrored and turned padstacks included — was checked
against the polygon Allegro itself reports for that pin (`axlPolyFromDB` with
`?layer`): same face, same bounding box.

**Only what the mask exposes.** The padstack carries the opening as a pad of
its own — `PIN/SOLDERMASK_TOP`, with the same kind of outline — and the
exporter writes it beside the copper. What is drawn is copper **and** opening,
settled once per figure: a *solder-mask-defined* pad, whose opening is smaller
than its copper, shows the opening's shape; a copper-defined one shows its
copper; a pad whose padstack has no opening on that side is under the mask and
draws nothing, counted in the log. Measured on the Dell board: 621 of 12 146
pins are mask-defined and 101 are covered.

**Vias, the same way.** Every via is a row like a pin's, with its padstack in
the library, so an untented via — one whose padstack has a mask opening —
shows its ring, and a tented one draws nothing and costs a row in the JSON.
Cadence's demo board tents none: 1242 vias, 2484 rings; the user's boards tent
all of theirs.

**Copper under openings drawn in the footprint or on the board.** A line, a
shape or a text on a `SOLDERMASK` layer (the `soldermask` section of the
config lists which layers — `BOARD GEOMETRY` and `PACKAGE GEOMETRY` by
default) exposes whatever copper lies under it: a thermal pad drawn as a
shape, a row of fingers, a test area, a pour, a part number cut into the mask.
The exporter computes that copper **in Allegro**: each opening becomes
polygons (a line opening is the line widened with round caps and a text its
strokes, as the legend does it), the copper on that side's outer layer
inside the opening's box is selected — pins and vias by their pads, a pour only
through the opening's window — and `axlPolyOperation` keeps what is under the
opening. The result travels in the legend's own polygon form, with Allegro's
area beside each polygon, and is built the way a flat legend is: one
copper-coloured part per side, `copper_top_<board>` / `copper_bot_<board>`,
faces unioned, a micron above the pads so a pad that lies under a drawn opening
as well is covered rather than fought. Measured on a small board: 53 drawn
openings, two of them over copper, 1.03 and 1.01 mm² of it, under a second.

**Copper drawn with no net is copper.** A label written in copper with *Add
Line* on `ETCH/TOP` belongs to no net, and to Allegro's find filter it is a
*line*, not a *cline*. The sweep asks for both: on the same board the 51
strokes of such a label under matching openings came back as 53 polygons of
copper, where a sweep for clines alone had found none of them.

## Mask openings

A second checkbox, **Mask openings (as surfaces)**, draws the windows in the
solder mask in the dielectric's colour (`base` in `layerColors`). Two kinds,
both the way the pads are drawn — surfaces above the mask, nothing cut into the
board. Three heights, a `silkscreenFlatHeight` apart: the windows lowest, the
copper above them, the drawn openings' parts above both — so where the windows
of two neighbouring through pins overlap each other's copper ring, the copper
is on top by construction rather than by whatever the viewer drew last (which
is how rings came out eaten on the demo board in step2html):

- **every pin's and via's opening from its padstack** — one shared face per
  opening figure, instanced per pin exactly like the pads, under
  `openings_top_<board>` / `openings_bot_<board>`; the drill stays a hole in it
  as it does in a pad;
- **every opening drawn on the mask layers** — a line, a shape or a rectangle
  (a rectangle on a mask layer is a filled shape to Allegro), a text — flat like
  the legend, one part per side, `bare_top_<board>` / `bare_bot_<board>`.

**With *Exposed copper* on, what the copper leaves of each opening**: the ring of
laminate around a copper-defined pad, and nothing for a solder-mask-defined
one, whose copper fills its window; for a drawn opening, the opening minus its
copper (`axlPolyOperation ANDNOT` in Allegro, the whole opening when nothing
lies under it). So a label cut into the mask over bare laminate is in the
model, and a label written in copper under a matching opening shows as copper
strokes with laminate rims. The copper and the laminate never overlap — one is
the other's complement inside the opening, at the same height. **On its own**
the checkbox draws the openings whole: the mask's windows on a board without
its copper.

**Only where there is a mask.** A window is drawn only on a zone whose stackup
carries a soldermask layer on that side. A flex or stiffener zone has coverlay
and adhesive there and no soldermask, so a pin on it gets no window (its copper
is still drawn), a drawn opening lying on it is left out, and one that runs
across a zone boundary — Cadence's demo draws its outline as strokes on the
mask layers, through every zone, and the part over the flex used to float two
millimetres above it — is clipped to the masked zones, each piece at its own
zone's face. The log counts what was left out and clipped. A plain board with
one stackup and no soldermask in it gets no windows at all, and says so.

Measured on the same small board: 61 padstack openings from 10 figures, and
the 53 drawn openings — the copper label's strokes and two shapes over the
pour — as 53 polygons of copper with 94 laminate rims when both are on, or 147
polygons of whole openings when the copper is off; 3.05–3.17 MB, under 2.5 s.

Needs an intermediate written with `format_version` 12 (`settings.exportPads`,
on by default, is what collects them); an 11 file has the pads and their
openings but no vias and nothing under drawn openings, a 10 file draws the
copper whole, an older one draws none, and a 12 file written before the bare
laminate was added has the copper under the openings but not the laminate —
the log says which, and a re-export cures each. **A tented via draws nothing** — and that is nearly every via
on nearly every board — and the pads are a picture: surfaces without thickness
that take part in no boolean.

## Multi-stackup and rigid-flex

A rigid-flex design is several **zones**, each with its own stackup and
thickness. The export reads them from the design and builds the board as those
zones fused into one solid. A single-stackup board has one zone — its own
outline — which is why *Body stitching* works there too.

**Zones line up on the copper, not on their outer faces.** A 2.44 mm stiffener
zone and a 0.365 mm flex zone share the same conductor core, and the stiffener
grows outwards from it — mostly upwards. Aligning their top faces instead would
tear the board apart at every zone boundary. **Components stand on their own
zone**, so a part on a stiffener and one on the flex are two millimetres apart
in Z.

Thickness comes from Allegro's own per-stackup figure rather than being summed
by layer name, because a flex stackup has no `SOLDERMASK` layer at all —
coverlay, adhesive and stiffener sit in its place — and a name-based sum would
silently report them as nothing.

## Folding flex bends

A bend is not geometry in Allegro: it is a line on `RIGID FLEX/BEND_LINE`, an
area on `RIGID FLEX/BEND_AREA`, and a property carrying the angle, the inner
side and the order. Simple 3D reads all three and folds the model.

**Everything moves together.** Board, legend and components are placed flat
first and then carried by the fold, so a part cannot drift off the surface it
was placed on. A component standing inside a bend area is placed on the curve
and reported — that is a design rule violation, not a modelling choice.

**The radius is measured from the local stack**, since the flex surface can sit
two millimetres below the top of a stiffener.

**Which side moves — the anchor.** The bend areas cut the flat board into
pieces. The one containing the **origin** stays in the XY plane, and every other
piece is folded by the bends on the path back to it — so what carries what is
read from how the pieces actually join, and a board with arms leaving in three
different directions folds each of them on its own. Allegro has the
same idea (*Setup – Anchor 3D View*), but in 24.1 the point it asks for never
reaches the board file, so the design cannot tell us and `[0, 0]` is the
convention instead. **Put the part of the board that should lie flat over the
origin**, or name another point in `gui.foldAnchor`. It decides the shape of the
fold, not just where it sits: with the anchor in the middle, two tails swing off
a held centre; at one end, the same two bends make a chain.

Each layer is cut down to its piece with a boundary that runs ten microns
outside the board outline and exactly along the bend seams. Allegro's zone
contours carry hairlines - an arc out along a stiffener's edge and back on a
circle a fraction of a micron off - and a cutter sharing that wall once cost
a flex layer a whole corner (2026-09-06); the margin keeps the two apart
without adding anything a layer does not already have.

**The bend surfaces are true cylinders.** Where the board is the same shape all
the way across a bend, the cross-section is revolved about the axis; otherwise
the outline itself is carried onto the cylinder, which keeps the surfaces
exactly cylindrical however complicated it is — relief notches, zone boundaries
and the occasional hole all live inside real bend areas. Only a shape neither
construction fits is faceted, in 7.5° slices, and the log names the bend and the
reason. The flat panels either side are never approximated.

A bend stretches the material outside the neutral surface and compresses what is
inside, and the model says so: each layer's volume comes out multiplied by its
own radius over the neutral one.

### The K factor, and why a ring may need it set to 0

How much flat material a bend consumes is its arc length along the neutral axis,
`angle × (radius + k × thickness)`, with `k = gui.foldNeutral`, `0.5` by
default — physically where the neutral axis of a symmetric flex is.

**Allegro draws its bend areas at the inner arc**, `angle × radius`, with no
thickness term at all — measured on three real boards, to a tenth of a micron
every time. That is the same as saying its flat pattern is laid out at `k = 0`,
and on a board with room to spare the difference does not show. It shows the
moment two bend areas touch: a flex rolled into a closed ring, two 180° bends
whose areas sit a ten-thousandth of a millimetre apart, closes to half a micron
at `k = 0` while at `k = 0.5` each bend wants 0.3 mm more material than exists.
**Set `foldNeutral` to `0` for such a board.** When the strips do reach each
other the log says so **in blue**, with the largest `foldNeutral` this particular
board takes cleanly — so the choice is a number rather than a guess.

Which of the two you want depends on whether you are reproducing the designer's
layout or modelling the material. When two bends do claim the same material, the
export names both, leaves the second one flat, folds everything else, and says
which `foldNeutral` would make them fit. Bends whose strips merely touch are
folded normally.

## Board thickness

The board solid is `dielectrics + planes + conductors + both soldermasks`.
Silkscreen and paste mask are excluded — they are printed on the board, not part
of it. A 2-layer example:

```
1.464 (dielectric) + 0.045 + 0.045 (copper) + 0.025 + 0.025 (mask) = 1.604 mm
```

## Known limitations

**Milling paths (`BOARD GEOMETRY/ncroute_path`) are not exported.** A route path
is an open centreline plus a tool width, not a boundary, so it cannot be
extruded — it would have to be offset by half the tool diameter on each side and
closed, with correct rounded ends and corner handling. **Draw anything you want
as a hole as a closed contour on `BOARD GEOMETRY/CUTOUT`**, which is a boundary
the export subtracts directly.

**A folded bend is a cylinder, not a bent stack-up model.** The surfaces are
exact and the material stretches and compresses as it should, but nothing here
models what a bend does to copper, adhesive or coverlay individually. Good for
fit, clearance and a picture; not a substitute for a flex stress calculation.

**Two bends that claim the same material are not both folded.** See *The K
factor*.

**Component B-rep comes from your library models.** File size beyond the board
is dominated by them, and *Compact STEP* cannot shrink geometry that lives
inside them.

**Silkscreen is not subtracted where holes are.** Clipping follows the outline
and its cutouts, not the drill holes. Legend is not printed over holes anyway,
so this shows only if the artwork deliberately runs a line across one.

**Exposed copper is a picture, not copper.** It is surfaces floating a micron
or two above the mask, in the mask's own plane rather than in a window cut through it;
they have no thickness and take part in no boolean. What is drawn is the pins'
and vias' pads through their padstack openings and the copper under openings
drawn on the `SOLDERMASK` layers; a pin whose span reaches no outer face of its
zone (a part mounted on an inner layer of a rigid zone) draws nothing and is
counted in the log, and a trace entering a pad's opening is not drawn inside
it — with *Mask openings* on, its place in the ring is laminate. A
legend printed over a pad — a design-rule violation in Allegro — lands in
the same plane as a flat legend and may flicker there.

## Command line (without Allegro)

```
python -m stepbuilder                                        # the window
python -m stepbuilder STEP_DIR JSON_FILE OUTPUT_DIR          # one JSON, headless
python -m stepbuilder STEP_DIR JSON_DIR  OUTPUT_DIR --batch  # every variant
```

`STEP_DIR` may be a `;`-separated list, and `--step-dir DIR` (repeatable) adds
more after it — same search order as the window.

Flags: `--batch` (with `--no-full-board` to leave the whole-board file out, as
the window's checkbox does), `--z-datum {top,bottom}`, `--color NAME|r,g,b|#rrggbb`,
`--rim-color …`, `--dated-name`, `--brd-name NAME` (names the output file; with
several variants it is ignored and each JSON's own stem names its output, or
they would collide), `--no-silkscreen`, `--no-silk-top`, `--no-silk-bottom`,
`--flat-silkscreen`, `--silk-flat-height MM`,
`--silk-layer-off LAYER` (repeatable), `--silk-color White|Black`,
`--ignore-soldermask`, `--flat` (do not fold), `--fold-anchor X,Y|auto`,
`--fold-neutral K`, `--fold-slice-angle DEG`, `--exposed-copper`, `--mask-openings`,
`--board-mode {solid,layers,inspect}`, `--no-minimize`, `--legacy-color`,
`--quiet`. Exit code 0 on success, 1 on error.

## What is where

```
makeVariant3dIntermediates.il   loads the exporter: its ten parts under skill/
skill/s3d_*.il                  the exporter itself - reads the Allegro database, writes the JSON
simple3d.il                     the menu item, the launcher, the pre-flight check
simple3d_config.json            every setting, read by both halves
stepbuilder/
  core.py        geometry + assembly. No UI, no printing: reports via callbacks
  contour.py     a JSON contour as an OpenCASCADE wire, or as a flat polygon
  errors.py      the one exception the package raises
  intermediate.py  one intermediate JSON, read once; which files to build; output naming
  settings.py    the settings pair: shipped defaults + the local file, merged key by key
  stackup.py     the stackup arithmetic: z from thickness, masks out, stackups on one datum, zone faces
  board.py       the board body: outline, zones, layers, cutouts, the rim faces
  legend.py      the silkscreen legend, and the arc convention settled by the board's own areas
  pads.py        the copper pads: which face a pin reaches, its figure as one shared face, placed per pin
  models.py      component models: the folder index, one read per model, the placement transform
  stepdoc.py     the assembly document and the STEP writer
  build.py       the options of one build, in one place, for the window and the CLI alike
  defaults.py    the three default numbers the window shows before a config is read
  winplace.py    where the window opens: remembered across runs, multi-monitor aware
  reporting.py   the log and progress callbacks every module reports through
  bend/          folding a flex board along its bend areas (a package since round 72)
  colors.py      the board themes and rim options
  widgets/       the panels the window is built from: layers_panel.py, the silkscreen layer list
  worker.py      the build, in a child process, so a crash cannot take the window
  worker_bridge.py  the window's half of that process: start, drain, notice a crash, cancel
  gui.py         the tkinter window, a thin wrapper around core
  __main__.py    entry point: window, headless, or prefilled from Allegro
tools/, tests/   SKILL checks, the docs audit, the Python name check, 26 test suites, two golden corpora (STEP and the SKILL export, the latter run headless), read-only probes and the runner that drives one against a board headless (run_probe.py)
```

`QUICKSTART.md` is the five-minute version. `CHANGELOG.md` is what changed and
when. `PROJECT_NOTES_simple3d.md` is the development memo — how each decision
was reached, round by round; useful for working *on* the tool, not for using it.
`ARCHITECTURE.md` is the map of the code — what each file holds, the pipeline
stage by stage, which pieces are monoliths and which could be reused elsewhere —
and `REFACTORING_PLANS.md` is the order in which to take those monoliths apart.

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

Штатный `File → Export → 3D` в Allegro тяжёлый: тянет полный MCAD-мост, делает
большие файлы и требует, чтобы модели были проведены через весь 3D-процесс. Для
вопросов «влезает ли плата в корпус» и «не сталкиваются ли высокие детали» это
избыточно.

Simple 3D — лёгкая альтернатива: одно тело платы истинной итоговой толщины,
переиспользуемые модели компонентов (поэтому файл небольшой) и плоское дерево
сборки, которое чисто открывается в SolidWorks, Inventor и Creo.

Проект вырос из [`exportStep` juulsA](https://github.com/juulsA/exportStep) —
его SKILL-экспортёр и построитель на OpenCASCADE лежат в основе. Построитель на
C++ переписан на Python (то же ядро, без компилятора и DLL), исправлен ряд
ошибок и добавлено всё описанное ниже.

## Как это работает

```
File → Export → Simple 3D          (simple3d.il, внутри Allegro)
   │  1. находит  rev/cad  (соседнюю с  rev/pcb ) или пишет рядом с .brd
   │  2. пишет туда по одному JSON на вариант с меткой "format": "simple3d"
   │  3. проверяет, что Python вообще запускается, и говорит, если нет
   └─ 4. открывает окно с уже заполненными путями
            └─ <плата>_simple_ДД_ММ_ГГГГ.step
```

Половины общаются через этот JSON, потому что ни одна не умеет работу другой:
SKILL читает базу Allegro, но не строит B-rep; OpenCASCADE строит STEP, но
ничего не знает про Allegro. Всё, что экспорт выяснил в Allegro, лежит в файле —
поэтому модель можно пересобрать иначе, не открывая плату заново.

Экспорт пишет `format_version: 12` (10 добавил необязательный объект `pads`,
из которого рисуется *медь площадок*; 11 добавил в него вскрытия маски каждого
падстека, так что площадка показывает только то, что открыто). Все предыдущие версии по-прежнему
собираются — каждая версия только *добавляла* необязательное, — так что
интермедиат, оставшийся от старого релиза, переэкспортировать не обязательно.
Обратное с версией 9 стало новостью: компоненты лежат под одним ключом
`"components"`, а не рядом с метаданными, поэтому файлу этого релиза нужен
Python этого релиза (старый `stepbuilder` увидел бы один компонент по имени
`components`).

Штатный индикатор Allegro на экране с момента нажатия Export: всё перечисленное
происходит до того, как появится наше окно. Единственный временный файл — лог
предполётной проверки `_simple3d_preflight.txt`: он пишется в выходную папку и
удаляется, как только прочитан.

## Установка

**1. Python 3.10+** с python.org, с галочкой *Add Python to PATH*. `tkinter`
входит в стандартный установщик под Windows.

**2. Одна зависимость:**

```
pip install cadquery-ocp
```

Это ядро OpenCASCADE с привязками к Python, и это весь `requirements.txt` — но
он немаленький: вместе с VTK, который объявлен жёсткой зависимостью, все трое
занимают на диске **около 470 МБ**.

**Если на машине больше одного Python**, помните, к какому из них относился этот
`pip`. `python` и `pythonw` — это *имена*, и что они значат сегодня, решает PATH:
установщик, приносящий с собой свой Python (так делает установка node.js — через
Chocolatey, причём в системный PATH, который идёт *раньше* пользовательского),
может поставить свежий интерпретатор впереди вашего. Пакетов после этого нет
потому, что интерпретатор **другой**, а не потому, что что-то удалили. Закрепите
нужный по полному пути — в секции `allegro` файла `simple3d_config.local.json`
(он ваш, в git не попадает, обновление его не трогает):

```json
"allegro": {
    "python":  "C:/Python312/python.exe",
    "pythonw": "C:/Python312/pythonw.exe"
}
```

Предполётная проверка печатает тот интерпретатор, который реально ответил, —
путь и версию, — так что в консоли видно, какой именно достался.

**3. Файлы.** Склонируйте или распакуйте репозиторий; его корень уже устроен
так, как надо — оба `.il`, `simple3d_config.json` и пакет `stepbuilder\` в
**одной папке**, где вам удобно:

```
d:\Projects\OrCAD\Scripts\Simple3D\
├── makeVariant3dIntermediates.il     SKILL-экспортёр (читает плату)
├── simple3d.il                       пункт меню + запуск; загружает экспортёр
├── skill\                            десять частей экспортёра (s3d_*.il)
├── simple3d_config.json              все настройки, читают обе половины
└── stepbuilder\                      пакет Python
```

Скачивание ZIP с GitHub заворачивает всё в лишнюю папку `Simple3D-main\`. Либо
распакуйте её *содержимое*, либо укажите на саму обёртку `SIMPLE3D_DIR` (ниже) —
но не оставляйте её и строки `load()` несогласованными.

Проверка из `cmd`:

```
cd /d d:\Projects\OrCAD\Scripts\Simple3D
python -m stepbuilder
```

Должно открыться окно, а в его логе — `Settings loaded from …`.

**4. Загрузка SKILL-файлов** из `allegro.ilinit` или вручную в каждой сессии:

```
load("d:/Projects/OrCAD/Scripts/Simple3D/simple3d.il")
```

Появится `File → Export → Simple 3D`. Одной строки достаточно: `simple3d.il`
сам загружает экспортёр (`makeVariant3dIntermediates.il`, который загружает
свои десять частей из `skill\`). Прежняя пара строк `load()`, сначала
экспортёр, тоже работает.

**Ничего в поставляемых файлах править под свою машину не нужно** — и это
намеренно: они под контролем версий, поэтому путь, вписанный в любой из них, —
это путь одной установки, разосланный всем и затираемый в каждой рабочей копии
следующим обновлением.

Где установлен сам инструмент — единственное, чего он не может прочитать из
своего конфига, потому что именно этим конфиг и находится. Источники, по
порядку:

1. **`SIMPLE3D_DIR` в вашем файле окружения Allegro** (`%HOME%\pcbenv\env`),
   которого обновления не касаются:

   ```
   set SIMPLE3D_DIR = d:/Tools/Simple3D
   ```

2. **папка, из которой загружен `simple3d.il`**, если SKILL её сообщит. Когда
   работает — не стоит пользователю ничего; вторым идёт потому, что опирается
   на имена ядра языка, не проверенные в этом Allegro, а значит может быть
   запасным вариантом, но не единственным.

Консоль называет, какой источник ответил. Если не ответил ни один, инструмент
говорит об этом и отказывается работать, а не гадает: свой Python-пакет он всё
равно не нашёл бы.

**Папки с моделями задаются в окне** (*STEP files*) или в
`simple3d_config.local.json`. В отслеживаемом конфиге их нет по той же причине.

## Окно программы

Большинство органов управления говорят сами за себя. Вот те, о которых стоит
знать:

| Элемент | Что важно |
|---|---|
| **STEP files** | Папки с моделями, по одной в строке, **просматриваются по порядку**: побеждает первая, где нашёлся файл. Поэтому папка проекта, стоящая выше общей библиотеки, перекрывает отдельные модели. Каждая обходится рекурсивно. Имя, найденное дважды, называется в логе вместе с победившим путём. |
| **JSON file** | Один интермедиат или папка вариантов — тогда собираются все. Берутся только файлы с меткой `"format": "simple3d"`, остальное игнорируется и пишется в лог. |
| **Z = 0 at** | Какая грань — база отсчёта. Детали стоят на **паяльной маске** своей стороны: реальные площадки несут припой, который поднимает деталь до уровня маски. |
| **Board edge color** | Своё тело одного цвета, с которым может контрастировать торец, есть только у *Solid*, поэтому в двух других сшивках элемент гаснет, а не молча игнорируется. |
| **Body stitching** | Как собрано тело, **на любой плате**: у обычной зон нет, поэтому её контур становится одной неявной зоной на единственном стекапе. *Solid* — одно тело, самое компактное. *Solid colored layers* — одно тело, но границы слоёв сохранены, и торец показывает стек (примерно в 4.7 раза больше). *Not stitched* — каждый слой каждой зоны отдельной деталью, чтобы разобрать плату глазами. Двум последним нужны слои стека: интермедиат от старой версии их не несёт — лог об этом скажет и соберёт одно тело. |
| **Do not include soldermask** | Убирает маску и смыкает стек к ядру ровно на снятую толщину, каждую сторону отдельно. Плата действительно становится тоньше — проверьте итог. |
| **Silkscreen: Top / Bottom** | Обе выключены — шелкография не строится вовсе, и файл заметно меньше. |
| **Make surface** | Легенда поверхностями, а не тонкими телами: примерно четверть её объёма в файле. Толщины у краски тогда нет, и в булевых операциях она не участвует. |
| **Silkscreen layers** | Галочка на каждый слой, *найденный в этом JSON*, с числом полигонов. Снимите и нажмите Generate снова — повторный экспорт не нужен. |
| **Fold flex bends** | Сгибать по областям сгиба. Выключено — плата экспортируется плоской. На плате без сгибов ничего не меняет. |
| **Exposed copper (as surfaces)** | Медь площадок всех выводов на двух наружных гранях — поверхности цвета меди на два микрона над маской, чтобы модель читалась как плата с площадками, а не как гладкая пластина. В плату ничего не вырезается: булевых операций нет, тело остаётся одним. Одна общая грань на фигуру площадки, вхождение на каждый вывод — площадка стоит в файле как размещение, а не как тело. Рисуется только то, что открыто маской: mask-defined площадка показывает форму своего вскрытия, площадка без вскрытия не показывает ничего, незакрытое переходное отверстие — своё кольцо, закрытое — ничего. Вскрытия, нарисованные на слоях `SOLDERMASK`, добавляют медь под собой — одна плоская деталь на сторону. Нужен JSON с `format_version` 12 (11 не несёт отверстий и меди под нарисованными вскрытиями, 10 рисует медь целиком, более старый — ничего; лог говорит, что именно). См. *Открытая медь*. |
| **Mask openings (as surfaces)** | Вскрытия паяльной маски поверхностями цвета диэлектрика (`base` из *layerColors*): вскрытие каждого вывода и переходного отверстия из его падстека, вхождениями как площадки, и каждое вскрытие, нарисованное на слоях `SOLDERMASK` — линия, фигура или прямоугольник, текст. Вместе с *Exposed copper* — то, что от вскрытия оставляет медь: кольцо вокруг copper-defined площадки, текстолит, который показывает прорезанная в маске надпись; сами по себе — вскрытия целиком. Нужен JSON с `format_version` 11 для вскрытий падстеков, 12 для нарисованных. См. *Открытая медь*. |
| **Compact STEP** | Убирает параметрические кривые на поверхностях — примерно вдвое меньший файл при той же геометрии. |
| **Build the full-board file too** | Когда в очереди папка — собирать ли вместе с вариантами `<плата>.json`, всю плату без учёта вариантов (пишет его `settings.exportFullBoard`). Файл, выбранный напрямую, собирается всегда: выбор и есть выбор. |
| **Generate** / **Cancel** | Пока идёт сборка, остальные элементы погашены — настройки уже сняты снимком, и правка на ходу лишь выглядела бы действием, — а кнопка становится **Cancel**. Отмена убивает сборку немедленно: с булевой операцией, которая уже минуту внутри OCCT, иначе не выйдет. Файл, который писался в этот момент, может остаться недописанным — лог об этом говорит. |

Лог раскрашен: оранжевый — предупреждения, тёмно-красный — ошибки, зелёный —
успех. Прогресс охватывает всю сборку, а строка рядом говорит, какой это этап.

**Сборка идёт в дочернем процессе.** OpenCASCADE умеет не выбросить исключение,
а умереть, и на сложной плате булева операция иногда именно это и делает; в
потоке это закрыло бы окно, не записав никуда ничего. Вместо этого окно
выживает, сообщает код возврата и подсказывает, что обычно помогает: *Not
stitched*, которая ничего не сшивает, или более грубый угол дольки при сгибе.

## Настройки

Всё лежит в **`simple3d_config.json`** рядом с двумя `.il`. Читают обе
половины: SKILL берёт секцию `allegro`, окно — `gui`, экспортёр — `silkscreen`
и `settings`.

**Файлов два, и ваш из них только один.** Отслеживаемый `simple3d_config.json`
содержит поставляемые умолчания; рядом с ним **`simple3d_config.local.json`**
содержит то, что отличается именно у этой установки, — прежде всего ваши папки
с моделями. При чтении они сливаются ключ за ключом, локальный побеждает, и
**окно пишет только локальный файл** и только то, что отличается от умолчания.

Это и делает обновление безопасным: оно не может ни конфликтовать с вашими
путями, ни затереть их, улучшенные умолчания до вас по-прежнему доходят, а
абсолютные пути и положение окна не попадают в коммиты. Создавать файл руками
не нужно — окно напишет его при первом закрытии; удаление ключа из него
возвращает поставляемое значение.

**Если не читается любой из двух — его нет или он отредактирован в невалидный
JSON — ничего не записывается до конца сессии**, даже если вы почините его при
открытом окне. Поля на экране в этот момент содержат значения по умолчанию, а не
ваши настройки, и их запись затёрла бы только что исправленный файл. Лог при
каждом старте называет оба файла.

Ключи, которые имеет смысл править руками, — остальные повторяют элементы окна:

| Секция | Ключ | Что делает |
|---|---|---|
| `allegro` | `python` / `pythonw` | Интерпретатор. `pythonw` открывает окно **без консоли**; `""` откатывается на `python`. |
| | `menuLabel` / `commandName` | Текст пункта меню и имя команды. Читаются при загрузке, поэтому изменение требует перезагрузки SKILL. |
| | `defineAlwaysExportProp` | Заводить свойство **`ALWAYS_STEP_EXPORT`** в словаре свойств открытого проекта — при открытии платы и перед каждым экспортом, — чтобы его можно было вешать из штатного диалога свойств Allegro. Деталь с этим свойством остаётся во всех вариантах. Заведение меняет плату, поэтому `false` не трогает ни один проект; экспорт при этом по-прежнему читает свойство там, где оно уже заведено. См. *Что попадает в экспорт*. |
| `gui` | `stepDirs` | Папки моделей в порядке поиска (см. таблицу выше). |
| | `boardMode` | `solid` / `layers` / `inspect` — то же, что *Body stitching*. |
| | `layerColors` | Цвет на каждый вид слоя (`copper`, `base`, `coverlay`, `adhesive`, `stiffener`, `soldermask`, `other`). По умолчанию — **собственные цвета материалов Allegro**, чтобы экспорт выглядел так же, как та же плата в 3D-канвасе Allegro. |
| | `foldAnchor` | Точка, остающаяся в плоскости XY, `[x, y]`. **По соглашению `[0, 0]`** — см. *Сгибание*. `"auto"` держит самый большой кусок. |
| | `foldNeutral` | Положение нейтральной оси как доля толщины (по умолчанию `0.5`). **Поставьте `0`, если области сгиба на плате соприкасаются** — см. *Сгибание*. |
| | `foldSliceAngle` | Угол дольки для сгиба, который пришлось гранить (по умолчанию `7.5`). Сгибы, построенные истинными цилиндрами, его игнорируют. |
| | `exposedCopper` | Галочка *Exposed copper*: медь площадок на наружных гранях, поверхностями. По умолчанию выключено. См. *Открытая медь*. |
| | `maskOpenings` | Галочка *Mask openings*: вскрытия маски поверхностями цвета диэлектрика — вместе с медью то, что она от них оставляет. По умолчанию выключено. См. *Открытая медь*. |
| | `exportFullBoard` | Когда есть `Variants.lst`, писать ещё и `<плата>.json` — всю плату без учёта вариантов (`NO_STEP_EXPORT` продолжает действовать). См. *Что попадает в экспорт*. |
| `settings` | `exportPads` | **Собирать** ли площадки в интермедиат вообще (по умолчанию да). *Рисовать* ли их — галочка, решается на каждой сборке. Выключение экономит сбор на плате, где они не нужны никогда. |
| | `negativeLayers` | Слои стека, чьи нарисованные фигуры — **окна**, а не материал; сравнение по подстроке без учёта регистра. Покрытие, маска и паста рисуются так по соглашению; стиффенер, клей и эпоксид — наоборот. Добавьте слой сюда, если его тела получаются инвертированными, — и **уберите**, если на плате он нарисован материалом: руководство по 3D Canvas говорит, что коверлей читается как негатив и что *«coverlays specified as positive shapes are not rendered in 3D canvas»*, то есть такие платы бывают и сам Allegro тогда слой просто не рисует. Лог называет слой, когда его окна не оставляют от него ничего в зоне. Решается при экспорте, поэтому смена требует переэкспорта. |
| `silkscreen` | `top` / `bottom` | Какие слои Allegro **собираются** — см. *Шелкография*. |
| `soldermask` | `top` / `bottom` | На каких слоях лежат **нарисованные вскрытия маски** — линия или фигура там открывает медь под собой, считается при экспорте. По умолчанию `BOARD GEOMETRY` и `PACKAGE GEOMETRY / SOLDERMASK_*`; добавьте `MANUFACTURING/SOLDERMASK_*` или свой слой, если посадочные места рисуют вскрытия там. См. *Открытая медь*. |

Остальное в `gui` повторяет окно и записывается при его закрытии — `zDatum`,
`boardColor`, `boardEdge`, `boardEdgeCustom`, `silkscreenTop`,
`silkscreenBottom`, `silkColor`, `silkscreenFlat`, `ignoreSoldermask`,
`foldBends`, `minimizeFileSize`, — плюс пять, о которых стоит сказать отдельно:

* `silkscreenFlatHeight` — мм между гранью платы и **плоской** легендой, чтобы
  они не были копланарны и не мерцали. По умолчанию `0.001`. Это не толщина
  краски: она в `settings.silkscreenThickness` и относится только к режиму тел.
* `buildFullBoard` — собирать ли вместе с вариантами файл всей платы, когда в
  очереди **папка**. Та самая галочка выше.
* `silkscreenLayersOff` — **исключения, а не включения**, поэтому слой, впервые
  появившийся на плате, рисуется, а не пропадает молча.
* `jsonFile`, `outputDir` — последние пути, выбранные **в окне**. Экспорт,
  запущенный из Allegro, эти поля заполняет, но сюда не пишет: они описывают
  плату, а не предпочтение.
* `windowGeometry`, `windowState` — где стояло окно и было ли развёрнуто, чтобы
  на многомониторном столе оно вернулось на тот же экран. Недостижимое
  положение игнорируется, окно центрируется.

Два ключа читаются, но не записываются, чтобы конфиг от старой сборки
продолжал работать: `stepDir` (одна папка, заменён на `stepDirs`) и
`debugLayers` (заменён на `boardMode`). Каждый переносится при чтении и
выбрасывается при записи; руками их добавлять не нужно.

## Что попадает в экспорт

Все символы с позиционным обозначением плюс любой символ, несущий STEP-модель
(`PKGDEF_STEP_FILE`) без обозначения — кронштейн или корпус разъёма,
поставленный прямо на плату, — за вычетом двух исключений.

**`NO_STEP_EXPORT` сильнее всего остального.** Повесьте свойство на символ —
либо на компонент или его определение, чтобы убрать все экземпляры детали, — и
он не попадёт в модель, даже если вариант его устанавливает. Каждый такой символ
называется в консоли.

**Список варианта решает за всё, у чего есть позиционное обозначение.**
Обозначение — это ровно то, чем деталь можно назвать в `Variants.lst`, поэтому
механика с обозначением (корпус разъёма, например) подчиняется списку наравне с
любым компонентом: **нет в списке — значит список говорит «не установлена»**, и
деталь не экспортируется, если на ней нет `ALWAYS_STEP_EXPORT`.

**Символ без позиционного обозначения находится вне системы вариантов** и
экспортируется во всех. Allegro оставляет обозначение пустым, когда связанного
компонента нет, поэтому такую деталь физически нечем назвать в списке,
сгенерированном из схемы — сказать о ней там нечего, и убрать её может только
`NO_STEP_EXPORT`.

**`ALWAYS_STEP_EXPORT` — выход из этого правила.** Деталь с этим свойством
остаётся во всех вариантах, что бы ни говорил список; `NO_STEP_EXPORT`
по-прежнему сильнее, потому что «никогда» побеждает «всегда».

Свойство появилось из-за случая, который по данным не разрешается: **площадка
под пайку провода** и **корпус разъёма** в базе одинаковы — обозначение,
STEP-модель, нет строки в BOM, не названы ни в одном варианте, — но корпус
должен исчезать вместе со своим разъёмом, а площадка часть **голой платы**, а
значит нужна в каждом варианте. На чертеже платы без шелкографии именно эти
площадки монтажнику и надо видеть. Разница в намерении, поэтому она
записывается на детали.

В отличие от `NO_STEP_EXPORT`, который штатный, **этого свойства не существует,
пока его кто-нибудь не заведёт**, а пока не заведено — прицепить его нельзя
ничем. Поэтому `simple3d.il` заводит его как пользовательское свойство типа
BOOLEAN и дальше не вмешивается: на что вешать — решаете вы, через
**Edit → Properties**. Четыре следствия:

* Словарь свойств принадлежит **проекту**, а не установке, поэтому запись
  создаётся на каждую плату: по триггеру `open` и ещё раз в начале экспорта. При
  загрузке SKILL-файлов не происходит ничего — версия, писавшая в базу при
  загрузке, совпала с падениями Allegro при старте.
* **Имя — ещё не плата.** Allegro иногда стартует на пустышке вместо проекта; в
  неё ничего не пишется, а экспорт об этом говорит.
* Заведение **меняет плату**, и Allegro попросит её сохранить. Чтобы этого не
  было, поставьте `allegro.defineAlwaysExportProp` в `false`: экспорт
  по-прежнему читает свойство там, где оно уже заведено.
* У BOOLEAN-свойства **нет значения** — оно есть или его нет, и это ровно та
  проверка, которую делает экспорт. Чтобы снять пометку, свойство надо
  **удалить**, а не выставлять в false. Allegro говорит об этом сам.

Повесьте свойство на **определение компонента** — и оно закроет все экземпляры
библиотечной детали сразу: пометьте площадку в библиотеке, и платы править не
придётся.

**Вся плата, без учёта вариантов.** Когда `Variants.lst` есть, экспорт
дополнительно пишет **`<плата>.json`** — все компоненты, кроме помеченных
`NO_STEP_EXPORT`, и список вариантов из них ничего не вычитает. Чертежу иногда
нужно показать то, что есть на голой плате, а не то, что ставится в конкретной
сборке; от `ALWAYS_STEP_EXPORT` это отличается масштабом: свойство решает вопрос
подетально, а этот файл — сразу для всей платы. В нём стоит
`"full_board": true` — по этому признаку окно и называет его в очереди:
отличать `<плата>.json` от `<плата>_<вариант>.json` по имени значит гадать, а
вариант может называться как угодно. STEP получается
`<плата>_simple_ДД_ММ_ГГГГ.step`. `settings.exportFullBoard: false` отключает
запись; галочка **Build the full-board file too** решает, собирать ли его, когда
в очереди папка.

`Variants.lst` читается **из папки, где лежит `.brd`** — там, где его держит
Allegro, — и больше нигде; если файла там нет, консоль называет проверенный
путь. Когда файл есть, пишется **по одному JSON на вариант** с именем
`<плата>_<вариант>`, и окно собирает каждый. **Файл от другого проекта**
(обозначений много, но ни одного с этой платы) отвергается, а не
экспортируется молча. Вариант, в котором **ничего не установлено** — в схеме
все детали помечены *not installed*, и Capture не пишет базовый список
вовсе, — экспортируется как **голая плата**: контур, шелкография и символы
без обозначения, с предупреждением в консоли (заглушка `"dummy"` от другого
проекта выглядит так же, предупреждение как раз про неё). В обычном случае
печатается покрытие: `variant list covers 47 of 51 placed component(s)`.
Обозначение из списка, которого **нет на плате**, называется по каждому
варианту — `variant BOM lists 4 component(s) that are not on this board:
VT1, VT2, VT3, VT4` — в консоли и ещё раз в логе окна: список тогда описывает
другую ревизию платы, не ту, что открыта.

Вариант может ещё и переопределять свойства отдельных компонентов блоком после
базового списка. Такие компоненты в этом варианте **установлены**, просто
собираются из другой детали, — и экспортируются вместе с ним, и только с ним.

### Когда модели нет в сборке

Allegro хранит собственную копию каждой привязанной модели **внутри .brd**, а
Simple 3D этими копиями не пользуется — он собирает из файлов на диске. Поэтому
плата может выглядеть полной в 3D-виде Allegro, а здесь компонента не окажется.
Три случая различаются, потому что чинятся по-разному:

* **Нет на диске, но лежит в плате.** Экспортируйте плату из 3DX-канваса
  Allegro, возьмите оттуда файлы моделей, положите в любую папку из списка
  *STEP files* (папка самой платы путешествует вместе с проектом), запустите
  ещё раз.
* **Нет ни на диске, ни в плате.** Восстанавливать нечего, файл нужно брать там,
  где лежит библиотека.
* **Есть на диске, но не читается** — занят другим приложением, нулевой после
  сорвавшегося копирования, диалект, который OpenCASCADE не принимает. Причина и
  путь называются, компонент пропускается, **остальная плата собирается**.

Регистр имени файла значения не имеет. Имя приходит из таблицы сопоставления
Allegro, где его набирают руками, а файл на диске назван поставщиком библиотеки,
поэтому `MODEL.STEP` и `model.step` здесь один и тот же файл — ровно как и для
самой Windows. Точное совпадение всегда в приоритете.

## Структура сборки

```
<имя_платы>
├── PCB_<плата>             одно тело итоговой толщины
├── silkscreen_top_<плата>  шелкография сверху (если включена и есть)
├── silkscreen_bot_<плата>  шелкография снизу
├── pads_top_<плата>        медь площадок сверху  (только с галочкой Exposed copper)
│   ├── pad_S_RCT_1-00_X_0-95_TOP   одна грань на фигуру площадки, по имени падстека и слоя
│   └── pad_S_RCT_1-00_X_0-95_TOP   та же грань ещё раз, на каждый вывод
├── pads_bot_<плата>        медь площадок снизу (зеркальная фигура несёт m: pad_…_TOPm)
├── copper_top_<плата>      медь под нарисованными вскрытиями маски сверху (Exposed copper; одна деталь на сторону, как плоская легенда)
├── copper_bot_<плата>      то же снизу
├── openings_top_<плата>    вскрытия маски сверху  (только с галочкой Mask openings; цвет диэлектрика)
│   └── opening_S_RCT_1-00_X_0-95_SOLDERMASK_TOP   одна грань на фигуру вскрытия, вхождение на каждый вывод — с медью то, что она оставляет
├── openings_bot_<плата>    вскрытия маски снизу
├── bare_top_<плата>        нарисованные вскрытия текстолитом сверху (Mask openings: что оставляет медь, или целиком)
├── bare_bot_<плата>        то же снизу
├── symbols_top_<плата>     компоненты верхней стороны
│   ├── cap_D8x10mm         деталь с именем своего STEP-файла, на месте
│   └── cap_D8x10mm         та же деталь ещё раз, если модель повторяется
└── symbols_bot_<плата>     компоненты нижней стороны
```

* Одна **деталь** на каждую уникальную STEP-модель, названа по имени файла.
  Десять одинаковых резисторов стоят одного тела, а не десяти.
* Детали моделей лежат **напрямую** в двух группах, без обёртки на каждый
  рефдес: каждый элемент — вхождение с именем своего файла.
* **Имя платы несёт каждый узел верхнего уровня**, а не просто `PCB` или
  `symbols_top`, поэтому импорт нескольких плат в одну сессию CAD не даёт детали
  или группе одной платы подменить другую.
* **Каждая сторона шелкографии — отдельная деталь**, её можно скрыть или
  перекрасить, не трогая плату.
* **Медь площадок — две группы**, верх и низ, из вхождений общих граней: одна
  грань на (падстек, слой, зеркало), названная по ним, — так их можно скрыть
  целиком, а каждый вывод стоит одного размещения.

## Шелкография

По умолчанию строятся обе стороны, настоящей геометрией: залитые области, либо
выдавленные в тонкие тела на грани платы, либо нарисованные плоскими
поверхностями чуть выше неё.

**Ширины, глифы и кривые — собственные у Allegro.** Линия шелкографии это
осевая плюс ширина, и превращение этого в залитый контур — работа
`axlPolyFromDB`, с предварительной векторизацией текста через `axlText2Lines`.
Ничего не обводится и не смещается вручную, поэтому в STEP попадает та же
геометрия, что уходит в Gerber. Каждый полигон затем сверяется с площадью,
которую сообщил Allegro, — кривая, восстановленная не в ту сторону, молча не
пройдёт.

**Легенда одинакова для всех вариантов сборки.** Текстолит изготавливается один
раз на все варианты, поэтому маркировка неустановленного компонента физически
на плате есть. Она собирается один раз на проект.

Какие слои Allegro **собираются**, задаётся в конфиге — правьте его, а не
исходник, если у вас другое именование:

```json
"silkscreen": {
    "top":    [ "BOARD GEOMETRY/SILKSCREEN_TOP", "REF DES/SILKSCREEN_TOP", … ],
    "bottom": [ "…/SILKSCREEN_BOTTOM", … ]
},
"settings": {
    "exportSilkscreen": true,      // собирать вообще
    "silkscreenThickness": 0.025,  // толщина краски, мм — только для тел
    "clipToBoardOutline": true,    // обрезать по контуру минус вырезы
    "endCapType": "ROUND"          // концы линий, как их рисует Allegro
}
```

Какие из собранных слоёв дойдут до модели, решается **на каждую сборку** в окне,
а список строится по JSON — поэтому предлагаются только слои, давшие геометрию
на этой плате, с числом полигонов, которое каждый стоит. Слой, не попавший в
списки конфига, не собирается и включить его галочкой без повторного экспорта
нельзя: держать дорогой слой вне конфига (позиционные обозначения векторизуют
каждый глиф) — экономия времени сбора, держать внутри — свобода выбора.

Линия без ширины или текст с нулевым пером не могут быть отпечатаны — рисовать
нечем и самой фотошаблонной программе, — поэтому объект пропускается и
называется вместе со слоем и координатами, и в консоли Allegro, и в логе окна:
консоль обычно уже прокручена к моменту, когда вы смотрите на модель.

**Тела или поверхности.** Поверхности примерно вчетверо компактнее, и они
объединяются: копланарные грани на одном z мерцают друг об друга там, где штрихи
перекрываются. Режим тел объединение намеренно **не** делает: булева операция
над тысячами тонких пересекающихся призм стоит времени решателя и делает файл
*больше* (измерено — 154%), не давая ничего видимого. Поэтому легенда телами —
это набор отдельных тел: смотреть, экспортировать и рендерить правильно, но это
не одно многообразное тело, если вы собираетесь делать булевы операции с самой
краской.

## Открытая медь

По умолчанию выключено; поставьте **Exposed copper (as surfaces)**, чтобы модель
читалась как плата с площадками, а не как зелёная пластина. Медь площадки
каждого вывода рисуется на двух наружных гранях поверхностью цвета меди из
`layerColors`, на два `silkscreenFlatHeight` над маской — как плоская
легенда, на ступеньку выше (первую ступеньку занимают *Mask openings*, и там,
где окно ложится на медь соседней площадки, медь сверху). В этом вся
конструкция: **в плату ничего не вырезается.** Окно на каждую площадку сквозь маску и тело в нём — это булева
операция над тысячами призм: минуты решателя на плотной плате и реальный шанс
пустого результата ради картинки, которая не отличит площадку заподлицо от
грани на микрон выше.

**Одна грань на фигуру, вхождение на каждый вывод.** Площадка падстека
строится один раз — на слой, и ещё раз зеркально для выводов на обратной
стороне, — а каждый вывод, который её использует, — вхождение этой грани со
своим положением и поворотом, как десять одинаковых резисторов делят одну
модель. Поэтому площадка стоит в файле как размещение, а не как грань: на
демо-плате Cadence 2982 площадки на 85 фигурах обошлись в 2.1 МБ — те же
грани, записанные по одной, дали бы 5.9 МБ — и в пять секунд сверх трёхминутной
сборки. Какой грани достигает вывод,
решает его **собственный диапазон слоёв** против наружной меди его зоны: SMD-
вывод на `INNER1` в гибкой зоне, где наружная медь и есть `INNER1`, рисуется на
верхней грани этой зоны, сквозной вывод через ядро флекса — на обеих его
гранях, а вывод, не достигающий наружной грани своей зоны, не рисуется и
считается в логе. Фигура зеркального вывода зеркалится до поворота, а
зеркальный сквозной вывод носит стек своего падстека задом наперёд — как его
ставит Allegro.

**Контур — собственный контур Allegro.** Для каждой площадки на слое меди
экспорт обходит путь, который хранит для неё падстек, — круг, овал,
скруглённый или фасочный прямоугольник, восьмиугольник и *Shape*-площадка
несут его все, — и пишет его тем же словарём отрезок / дуга / окружность, что
и контур платы, так что ни один вид фигуры нигде не интерпретируется. Сквозная
площадка сохраняет своё отверстие — кольцом; донат — внутренний диаметр;
крепёжное отверстие с номинальной площадкой меньше сверла не рисует ничего и
не жалуется. Дуга угла строится **через свои две концевые точки**, а не по
центру: центр дуги Allegro хранит лишь с разрешением проекта, и дуга,
восстановленная по радиусу, может не дойти до соседнего отрезка на доли
микрона — этого хватает, чтобы скруглённый прямоугольник остался незамкнутым
и не нарисовался. Каждая поставленная площадка на пяти реальных платах —
54 000 размещений, включая смещённые, зеркальные и повёрнутые падстеки —
сверена с полигоном, который сам Allegro сообщает для этого вывода
(`axlPolyFromDB` с `?layer`): та же грань, тот же габарит.

**Только то, что открыто маской.** Падстек хранит вскрытие как собственную
площадку — `PIN/SOLDERMASK_TOP`, с таким же контуром, — и экспорт пишет его
рядом с медью. Рисуется медь **и** вскрытие, один раз на фигуру:
*mask-defined* площадка, у которой вскрытие меньше меди, показывает форму
вскрытия; copper-defined — свою медь; площадка, у падстека которой нет
вскрытия с этой стороны, закрыта маской и не рисуется, это считается в логе.
Замер на плате Dell: 621 из 12146 выводов mask-defined и 101 закрыт.

**Переходные отверстия — так же.** Каждое переходное отверстие — строка, как
у вывода, с его падстеком в библиотеке, так что незакрытое отверстие — у
падстека которого есть вскрытие маски — показывает своё кольцо, а закрытое не
рисуется и стоит одной строки в JSON. Демо-плата Cadence не закрывает ни
одного: 1242 отверстия, 2484 кольца; на платах пользователя закрыты все.

**Медь под вскрытиями, нарисованными в посадочном месте или на плате.** Линия,
фигура или текст на слое `SOLDERMASK` (какие слои — секция `soldermask`
конфига; по умолчанию `BOARD GEOMETRY` и `PACKAGE GEOMETRY`) открывает медь,
лежащую под ней: термопад, нарисованный фигурой, ряд ламелей, тестовую
область, заливку, номер платы, прорезанный в маске. Экспорт считает эту медь
**в Allegro**: каждое вскрытие становится полигонами (вскрытие-линия — линия,
раздутая до ширины со скруглёнными концами, текст — его штрихи, как в
легенде), медь наружного слоя этой стороны в габарите вскрытия
выбирается — выводы и отверстия своими площадками, заливка только через окно
вскрытия — и `axlPolyOperation` оставляет то, что под вскрытием. Результат
едет в форме полигонов легенды, с площадью от Allegro у каждого, и строится
как плоская легенда: одна деталь цвета меди на сторону, `copper_top_<плата>` /
`copper_bot_<плата>`, грани слиты, на микрон выше площадок, чтобы площадка,
попавшая ещё и под нарисованное вскрытие, была накрыта, а не мерцала. Замер
на небольшой плате: 53 нарисованных вскрытия, два над медью, 1.03 и 1.01 мм²,
меньше секунды.

**Медь без цепи — тоже медь.** Надпись, нарисованная медью через *Add Line*
на `ETCH/TOP`, не принадлежит ни одной цепи, и для фильтра поиска Allegro это
*line*, а не *cline*. Развёртка спрашивает и то и другое: на той же плате
51 штрих такой надписи под совпадающими вскрытиями вернулся 53 полигонами меди,
тогда как поиск одних clines не находил ни одного.

## Вскрытия маски

Вторая галочка, **Mask openings (as surfaces)**, рисует окна в паяльной маске
цветом диэлектрика (`base` из `layerColors`). Два вида, оба так же, как
площадки: поверхности над маской, в плату ничего не вырезается. Три высоты
через `silkscreenFlatHeight`: окна ниже всех, медь над ними, детали
нарисованных вскрытий выше обоих — и там, где окна двух соседних выводов
ложатся на кольца меди друг друга, медь сверху по построению, а не потому, что
просмотрщик нарисовал её последней (именно так кольца на демо-плате
оказались «съедены» в step2html):

- **вскрытие каждого вывода и переходного отверстия из его падстека** — одна
  общая грань на фигуру вскрытия, вхождение на каждый вывод ровно как у
  площадок, под `openings_top_<плата>` / `openings_bot_<плата>`; сверло
  остаётся в нём отверстием, как и в площадке;
- **каждое вскрытие, нарисованное на слоях маски** — линия, фигура или
  прямоугольник (прямоугольник на слое маски для Allegro — заполненная
  фигура), текст — плоско, как легенда, одна деталь на сторону,
  `bare_top_<плата>` / `bare_bot_<плата>`.

**Вместе с *Exposed copper* — то, что от вскрытия оставляет медь**: кольцо
текстолита вокруг copper-defined площадки и ничего у solder-mask-defined, чью
рамку медь заполняет целиком; у нарисованного вскрытия — вскрытие минус его
медь (`axlPolyOperation ANDNOT` в Allegro, всё вскрытие целиком, если под ним
ничего нет). Так надпись, прорезанная в маске над голым текстолитом, есть в
модели, а надпись, нарисованная медью под совпадающим вскрытием, видна медными
штрихами с ободками текстолита. Медь и текстолит не пересекаются — одно
дополняет другое внутри вскрытия, на одной высоте. **Сама по себе** галочка
рисует вскрытия целиком: окна маски на плате без её меди.

**Только там, где маска есть.** Окно рисуется только в зоне, чей стек несёт
слой паяльной маски с этой стороны. У зоны флекса или стиффенера там
коверлей и клей, а маски нет, поэтому вывод на ней окна не получает (его
медь рисуется по-прежнему), нарисованное вскрытие, лежащее на ней,
пропускается, а пересекающее границу зон — демо-плата Cadence рисует свой
контур штрихами на слоях маски сквозь все зоны, и часть над флексом висела на
два миллиметра выше него — обрезается по зонам с маской, каждый кусок на
грани своей зоны. Лог считает пропущенное и обрезанное. Обычная плата с одним
стеком без паяльной маски окон не получает вовсе, и лог об этом говорит.

Замер на той же небольшой плате: 61 вскрытие падстеков из 10 фигур и 53
нарисованных — штрихи медной надписи и две фигуры над заливкой — дают 53
полигона меди с 94 ободками текстолита при обеих галочках или 147 полигонов
целых вскрытий без меди; 3.05–3.17 МБ, меньше 2.5 с.

Нужен интермедиат с `format_version` 12 (собирает их `settings.exportPads`,
по умолчанию включённый); файл 11 несёт площадки и их вскрытия, но не
переходные отверстия и не медь под нарисованными вскрытиями, файл 10 рисует
медь целиком, более старый не рисует ничего, а файл 12, записанный до
появления голого текстолита, несёт медь под вскрытиями, но не текстолит — лог
говорит, что именно, и повторный экспорт лечит каждый случай. **Закрытое маской переходное отверстие не рисуется** — а это
почти каждое отверстие почти на любой плате, — а площадки остаются картинкой:
поверхности без толщины, не участвующие в булевых операциях.

## Мультистэкап и rigid-flex

Rigid-flex — это несколько **зон**, у каждой свой стек и своя толщина. Экспорт
читает их из проекта и собирает плату как эти зоны, слитые в одно тело. У платы
с одним стекапом зона одна — её собственный контур, — поэтому *Body stitching*
работает и там.

**Зоны выравниваются по меди, а не по внешним граням.** Зона стиффенера 2.44 мм
и зона флекса 0.365 мм имеют общее проводящее ядро, и стиффенер растёт от него
наружу — в основном вверх. Выравнивание по верхним граням разорвало бы плату на
каждой границе зон. **Компоненты стоят на своей зоне**, поэтому деталь на
стиффенере и деталь на флексе разнесены по Z на два миллиметра.

Толщина берётся из собственной цифры Allegro на стекап, а не суммируется по
именам слоёв: у флекс-стекапа слоя `SOLDERMASK` нет вообще — на его месте
покрытие, клей и стиффенер — и сумма по именам молча посчитала бы их нулём.

## Сгибание гибких плат

Сгиб в Allegro — не геометрия: это линия на `RIGID FLEX/BEND_LINE`, область на
`RIGID FLEX/BEND_AREA` и свойство с углом, внутренней стороной и порядком.
Simple 3D читает все три и складывает модель.

**Всё двигается вместе.** Плата, легенда и компоненты сначала размещаются
плоско, а потом переносятся сгибом, поэтому деталь не может съехать с
поверхности, на которую её поставили. Компонент, стоящий в области сгиба,
размещается на дуге и отмечается в логе — это нарушение правил проектирования, а
не выбор модели.

**Радиус отсчитывается от местного стека**: поверхность флекса может лежать на
два миллиметра ниже верха стиффенера.

**Какая сторона двигается — якорь.** Области сгиба режут плоскую плату на куски.
Тот, что содержит **начало координат**, остаётся в плоскости XY, а каждый
остальной складывается теми сгибами, что лежат на пути обратно к нему — то есть
кто кого несёт, читается по тому, как куски реально соединены, и плата с
плечами, уходящими в три разные стороны, складывается по каждому отдельно. У
Allegro есть та же идея (*Setup – Anchor 3D View*), но в 24.1 запрошенная точка
до файла платы не доходит, поэтому проект нам её сообщить не может и соглашением
служит `[0, 0]`. **Положите ту часть платы, которая должна лежать плоско, на
начало координат** или назовите другую точку в `gui.foldAnchor`. Якорь решает
форму сгиба, а не только положение: если он в середине, два хвоста отгибаются от
удерживаемого центра; если с краю — те же два сгиба дают цепочку.

Каждый слой вырезается под свой кусок границей, которая идёт на десять микрон
снаружи контура платы и точно по швам сгибов. Контуры зон Allegro несут
«волоски» — дугу вдоль края стиффенера и обратно по окружности, смещённой на
долю микрона, — и резак, деливший с ними стенку, однажды стоил слою флекса
целого угла (2026-09-06); отступ разводит их, ничего не добавляя к тому, что у
слоя и так есть.

**Поверхности сгибов — истинные цилиндры.** Там, где плата поперёк области сгиба
одинакова, сечение вращается вокруг оси; иначе на цилиндр переносится сам
контур, и поверхности остаются точно цилиндрическими, каким бы сложным он ни
был — разгрузочные полукруги, границы зон и случайные отверстия попадают внутрь
реальных областей сгиба постоянно. Гранится дольками по 7.5° только форма, к
которой не подошло ни одно построение, и лог называет сгиб и причину. Плоские
панели по обе стороны не аппроксимируются никогда.

Сгиб растягивает материал снаружи нейтральной поверхности и сжимает изнутри, и
модель это показывает: объём каждого слоя выходит умноженным на отношение его
радиуса к нейтральному.

### K-фактор, и почему кольцу может понадобиться ноль

Сколько плоского материала съедает сгиб — это длина дуги по нейтральной оси,
`угол × (радиус + k × толщина)`, где `k = gui.foldNeutral`, по умолчанию `0.5`:
физически там нейтральная ось симметричного флекса и находится.

**Allegro рисует свои области сгиба по внутренней дуге**, `угол × радиус`, без
слагаемого с толщиной вовсе — измерено на трёх реальных платах, каждый раз с
точностью до десятой доли микрона. Это то же самое, что сказать: развёртка
Allegro построена при `k = 0`. На плате с запасом разница не видна. Она
проявляется, как только две области сгиба соприкасаются: флекс, свёрнутый в
замкнутое кольцо, — два сгиба по 180°, чьи области стоят в одной десятитысячной
миллиметра друг от друга, — при `k = 0` смыкается с точностью до полумикрона, а
при `k = 0.5` каждому сгибу не хватает 0.3 мм материала. **Для такой платы
поставьте `foldNeutral` в `0`.** Когда полосы всё же сходятся, лог говорит об
этом **синим** и называет наибольшее `foldNeutral`, которое эта плата держит
чисто, — то есть выбор становится числом, а не догадкой.

Что вам нужно из двух — зависит от того, воспроизводите вы разводку
конструктора или моделируете материал. Когда два сгиба действительно претендуют
на один материал, экспорт называет оба, оставляет второй плоским, складывает всё
остальное и говорит, какой `foldNeutral` их бы примирил. Сгибы, чьи полосы лишь
соприкасаются, складываются нормально.

## Толщина платы

Тело платы — это `диэлектрики + полигоны + проводники + обе паяльные маски`.
Шелкография и паста исключены: они нанесены на плату, а не являются ею. Пример
для двухслойки:

```
1.464 (диэлектрик) + 0.045 + 0.045 (медь) + 0.025 + 0.025 (маска) = 1.604 мм
```

## Известные ограничения

**Фрезеровочные пути (`BOARD GEOMETRY/ncroute_path`) не экспортируются.** Путь
фрезы — это открытая осевая линия плюс диаметр инструмента, а не граница, и
выдавить его нельзя: пришлось бы отступить на половину диаметра в обе стороны и
замкнуть, с правильными скруглениями концов и обработкой углов. **Всё, что
должно стать отверстием, рисуйте замкнутым контуром на
`BOARD GEOMETRY/CUTOUT`** — это граница, которую экспорт вычитает напрямую.

**Сложенный сгиб — цилиндр, а не модель изгиба стека.** Поверхности точные, и
материал растягивается и сжимается как положено, но того, что сгиб делает с
медью, клеем и покрытием по отдельности, здесь нет. Годится для примерки,
зазоров и картинки; расчёт напряжений во флексе это не заменяет.

**Два сгиба, претендующих на один материал, вместе не складываются.** См.
*K-фактор*.

**B-rep компонентов приходит из вашей библиотеки.** Размер файла сверх самой
платы определяют именно эти модели, и *Compact STEP* не уменьшит геометрию,
которая лежит внутри них.

**Шелкография не вычитается под отверстиями.** Обрезка идёт по контуру платы и
вырезам, но не по сверловке. Легенду поверх отверстий всё равно не печатают,
так что это заметно, только если линия проведена через отверстие намеренно.

**Открытая медь — картинка, а не медь.** Это поверхности на микрон-другой над маской,
в плоскости самой маски, а не в вырезанном в ней окне; толщины у них нет, и в
булевых операциях они не участвуют. Рисуются площадки выводов и переходных
отверстий сквозь вскрытия их падстеков и медь под вскрытиями, нарисованными на
слоях `SOLDERMASK`; вывод, чей диапазон слоёв не достигает наружной грани своей
зоны (деталь на внутреннем слое жёсткой зоны), не рисуется и считается в логе,
а дорожка, входящая во вскрытие площадки, внутри него не рисуется — с
*Mask openings* её место в кольце занимает текстолит. Легенда
поверх площадки — в Allegro это нарушение правил — попадает в одну плоскость с
плоской легендой и может там мерцать.

## Командная строка (без Allegro)

```
python -m stepbuilder                                        # окно
python -m stepbuilder STEP_DIR JSON_FILE OUTPUT_DIR          # один JSON, без окна
python -m stepbuilder STEP_DIR JSON_DIR  OUTPUT_DIR --batch  # все варианты
```

`STEP_DIR` может быть списком через `;`, а `--step-dir DIR` (можно повторять)
дописывает папки после него — порядок поиска тот же, что и в окне.

Флаги: `--batch` (с `--no-full-board`, чтобы не собирать файл всей платы, как
галочка в окне), `--z-datum {top,bottom}`, `--color NAME|r,g,b|#rrggbb`,
`--rim-color …`, `--dated-name`, `--brd-name NAME` (имя выходного файла; при
нескольких вариантах игнорируется — иначе они столкнулись бы в одно имя, — и
каждый файл называется по имени своего JSON), `--no-silkscreen`,
`--no-silk-top`, `--no-silk-bottom`, `--flat-silkscreen`, `--silk-flat-height MM`,
`--silk-layer-off LAYER` (можно повторять), `--silk-color White|Black`,
`--ignore-soldermask`, `--flat` (не сгибать), `--fold-anchor X,Y|auto`,
`--fold-neutral K`, `--fold-slice-angle DEG`, `--exposed-copper`, `--mask-openings`,
`--board-mode {solid,layers,inspect}`, `--no-minimize`, `--legacy-color`,
`--quiet`. Код возврата 0 при успехе, 1 при ошибке.

## Что где лежит

```
makeVariant3dIntermediates.il   загружает экспортёр: его десять частей из skill/
skill/s3d_*.il                  сам экспортёр — читает базу Allegro, пишет JSON
simple3d.il                     пункт меню, запуск, предполётная проверка
simple3d_config.json            все настройки, читают обе половины
stepbuilder/
  core.py        геометрия и сборка. Без UI и печати: отчёт через колбэки
  contour.py     контур из JSON как проволока OpenCASCADE или как плоский полигон
  errors.py      единственное исключение пакета
  intermediate.py  промежуточный JSON, прочитанный один раз; что собирать; имена выходных файлов
  settings.py    пара настроек: штатные значения + локальный файл, слитые по ключам
  stackup.py     арифметика стека: z из толщин, маски долой, стеки на одном уровне, грани зон
  board.py       тело платы: контур, зоны, слои, вырезы, грани торца
  legend.py      шелкография, и соглашение о дугах, установленное по площадям самой платы
  pads.py        медь площадок: какой грани достигает вывод, его фигура одной общей гранью, вхождение на каждый вывод
  models.py      модели компонентов: индекс папок, одно чтение на модель, преобразование установки
  stepdoc.py     документ сборки и запись STEP
  build.py       параметры одной сборки в одном месте, для окна и консоли одинаково
  defaults.py    три числа по умолчанию, которые окно показывает до чтения настроек
  winplace.py    где открывается окно: запоминается между запусками, знает о нескольких мониторах
  reporting.py   колбэки лога и прогресса, через которые отчитываются все модули
  bend/          сгибание гибкой платы по областям сгиба (с раунда 72 — пакет)
  colors.py      темы платы и варианты цвета торца
  widgets/       панели, из которых собрано окно: layers_panel.py — список слоёв шелкографии
  worker.py      сборка в дочернем процессе, чтобы падение не унесло окно
  worker_bridge.py  половина этого процесса со стороны окна: запуск, чтение очереди, замеченное падение, отмена
  gui.py         окно tkinter, тонкая обёртка вокруг core
  __main__.py    точка входа: окно, консоль или запуск из Allegro
tools/, tests/   проверки SKILL, аудит документации, проверка имён Python, 26 наборов тестов, два золотых корпуса (STEP и экспорт SKILL — второй гоняется без окна), зонды и запускалка зонда против платы без окна (run_probe.py)
```

`QUICKSTART.md` — версия на пять минут. `CHANGELOG.md` — что и когда менялось.
`PROJECT_NOTES_simple3d.md` — рабочая записка разработки: как принималось каждое
решение, раунд за раундом; нужна для работы **над** инструментом, а не с ним.
`ARCHITECTURE.md` — карта кода: что лежит в каждом файле, конвейер по стадиям,
какие куски являются монолитом, а какие можно переиспользовать; а
`REFACTORING_PLANS.md` — в каком порядке эти монолиты разбирать.
