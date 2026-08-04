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
   │  1. finds the design's  rev/cad  folder (sibling of  rev/pcb )
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

Allegro's own progress form is on screen from the moment you press Export,
because all of the above happens before any window of ours appears. Nothing
temporary is written next to your board.

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

**3. The files.** Clone or unpack the repository; its root already is the layout
the tool expects — the two `.il` files, `simple3d_config.json` and the
`stepbuilder\` package in **one folder**, anywhere you like:

```
d:\Projects\OrCAD\Scripts\Simple3D\
├── makeVariant3dIntermediates.il     SKILL exporter (reads the board)
├── simple3d.il                       menu item + launcher
├── simple3d_config.json              all settings, both halves read it
└── stepbuilder\                      the Python package
```

Downloading as a ZIP from GitHub wraps everything in `Simple3D-main\`. Either
unpack its *contents*, or point `S3D_ScriptDir` at the wrapper — but do not
leave the two disagreeing.

Check it from a `cmd`:

```
cd /d d:\Projects\OrCAD\Scripts\Simple3D
python -m stepbuilder
```

The window should open and its log should say `Settings loaded from …`.

**4. Load the SKILL files** from `allegro.ilinit`, or by hand each session:

```
load("d:/Projects/OrCAD/Scripts/Simple3D/makeVariant3dIntermediates.il")
load("d:/Projects/OrCAD/Scripts/Simple3D/simple3d.il")
```

`File → Export → Simple 3D` appears. One setting stays in `simple3d.il` and has
to match where you put the files: **`S3D_ScriptDir`**. It cannot move into the
config, because it is what finds the config.

## The window

Most controls say what they do. These are the ones worth knowing about:

| Control | What to know |
|---|---|
| **STEP files** | The model folders, one per line, **searched in order** — the first folder holding a given file wins, so a project-local folder above the shared library overrides individual models. Each is searched recursively. A name found twice is reported with the path that won. |
| **JSON file** | One intermediate, or a folder of variants — then every one of them is built. Only files tagged `"format": "simple3d"` are touched; anything else in the folder is ignored and logged. |
| **Z = 0 at** | Which face is the datum. Parts sit on the **soldermask** of their side, because real pads carry solder that lifts the part to mask level. |
| **Board edge color** | Only *Solid* has one uniformly colored body for a rim to contrast with, so this greys out in the other two stitchings rather than being silently ignored. |
| **Body stitching** | Multi-stackup boards only. *Solid* — one body, smallest. *Solid colored layers* — one body whose layer interfaces survive, so the rim shows the stack (~4.7× larger). *Not stitched* — every layer of every zone its own part, for taking the board apart by eye. |
| **Do not include soldermask** | Leaves the mask out and closes the stack up toward the core by exactly what was removed, each side independently. The board really does get thinner — check the total. |
| **Silkscreen: Top / Bottom** | Both off skips the legend entirely and makes a noticeably smaller file. |
| **Make surface** | The legend as surfaces rather than thin solids: about a quarter of its file size. The ink then has no thickness and cannot be used in boolean work. |
| **Silkscreen layers** | A tick per layer *found in this JSON*, with its polygon count. Untick and press Generate again — no re-export needed. |
| **Fold flex bends** | Fold along the bend areas. Off exports the board flat. Does nothing on a board without them. |
| **Compact STEP** | Drops parametric surface curves — roughly half the file, identical geometry. |

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
takes `silkscreen` and `settings`. The window writes its own section back when
it closes, so what you last set is what the next run starts with.

**If that file cannot be read — missing, or edited into invalid JSON — nothing
is written back for the rest of the session**, even if you repair it while the
window is open. The fields on screen are defaults at that point, not your
settings, and saving them would overwrite the file you just fixed. The log says
which file was read and whether it parsed, on every start.

The keys worth setting by hand — the rest mirror controls in the window:

| Section | Key | What it does |
|---|---|---|
| `allegro` | `python` / `pythonw` | The interpreter. `pythonw` opens the window with **no console**; `""` falls back to `python`. |
| | `menuLabel` / `commandName` | Menu text and command name. Read at load time, so a change needs a SKILL reload. |
| | `defineAlwaysExportProp` | Create the **`ALWAYS_STEP_EXPORT`** property in the open design's property dictionary — at load and before every export — so it can be attached from Allegro's own Properties dialog. A part carrying it stays in every variant. Defining it is a change to the board, so `false` leaves every design untouched; the export still reads the property wherever it is already defined. See *What gets exported*. |
| `gui` | `stepDirs` | The model folders, in search order (see the table above). |
| | `boardMode` | `solid` / `layers` / `inspect` — the *Body stitching* control. |
| | `layerColors` | Color per layer kind (`copper`, `base`, `coverlay`, `adhesive`, `stiffener`, `soldermask`, `other`). The defaults are **Allegro's own material colors**, so the export looks like the same board does in Allegro's 3D canvas. |
| | `foldAnchor` | The point that stays in the XY plane, `[x, y]`. **`[0, 0]` by convention** — see *Folding*. `"auto"` holds the largest piece instead. |
| | `foldNeutral` | Where the neutral axis sits, as a fraction of thickness (default `0.5`). **Set it to `0` on a board whose bend areas touch** — see *Folding*. |
| | `foldSliceAngle` | Arc per slice for a bend that has to be faceted (default `7.5`). Bends built as true cylinders ignore it. |
| `settings` | `negativeLayers` | Stackup layers whose drawn shapes are **openings** rather than material, matched as a case-insensitive substring. Coverlay, soldermask and pastemask are drawn that way by convention; stiffener, adhesive and epoxy are the opposite. Add a layer here if its bodies come out inverted. |
| `silkscreen` | `top` / `bottom` | Which Allegro layers are **collected** — see *Silkscreen*. |

The rest of `gui` mirrors the window and is written back when it closes —
`zDatum`, `boardColor`, `boardEdge`, `boardEdgeCustom`, `silkscreenTop`,
`silkscreenBottom`, `silkColor`, `silkscreenFlat`, `ignoreSoldermask`,
`foldBends`, `minimizeFileSize` — plus five that are worth a word each:

* `silkscreenFlatHeight` — mm between the board face and a **flat** legend, so
  the two are not coplanar and do not flicker. Default `0.001`. Not the ink
  thickness; that is `settings.silkscreenThickness`, and it applies to solid
  mode only.
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
component: listed and unmarked, it is exported; listed and marked, it is not;
**absent from the list, it is not** — whatever `NO_STEP_EXPORT` says.

**A symbol with no reference designator is outside the variant system** and is
exported in every variant. Allegro leaves the refdes empty when there is no
associated component, so such a part can never be named in a list generated from
the schematic — nothing there can say anything about it, and `NO_STEP_EXPORT` is
the only thing that removes it.

**`ALWAYS_STEP_EXPORT` is the way out of that rule.** A part carrying it stays
in every variant whatever the list says; `NO_STEP_EXPORT` still outranks it,
because *never* beats *always*.

It exists because of a case the data cannot settle. A **wire-solder pad** and a
**connector housing** are identical in the database — refdes, a STEP model, no
BOM line, named in no variant — but the housing should vanish together with its
connector, while the pad is part of the *bare board* and belongs in every
variant: on a drawing, especially on a board with no silkscreen, those pads are
what the fitter needs to see. The difference is intent, so it is written on the
part.

Unlike `NO_STEP_EXPORT`, which is one of Allegro's own, **this property does not
exist until something creates it** — and until it is defined, nothing can attach
it. So `simple3d.il` defines it as a BOOLEAN user property and then stays out of
the way: what it goes on is yours to decide, through **Edit → Properties**.
Three consequences:

* A property dictionary belongs to a **design**, not to the installation, so the
  entry is created per board: on Allegro's `open` trigger and again at the top of
  every export. Loading the SKILL files does nothing at all — a version that
  wrote at load time coincided with Allegro crashing on startup.
* **A name is not a board.** Allegro sometimes starts on an empty placeholder
  rather than a design; nothing is written to one, and the export says so
  instead of building nothing.
* Defining it **changes the board**, so Allegro will want it saved. Set
  `allegro.defineAlwaysExportProp` to `false` to stop that; the export still
  reads the property wherever it is already defined.
* A BOOLEAN property has **no value** — it is there or it is not, which is the
  test the export makes. To un-mark a part, *delete* the property rather than
  setting it false. Allegro says the same if you try.

Attach it to a **component definition** to cover every instance of a library
part at once: mark the pad in the library, and no board needs touching again.

`Variants.lst` is read **from the folder holding the `.brd`**, which is where
Allegro keeps it, and nowhere else; the console names the path it tried when
there is nothing there. With one present, the export writes **one JSON per
variant**, named `<design>_<variant>`, and the window builds every one of them.
Two kinds of wrong file are refused rather than exported quietly: a **stub**
(one variant, usually `"dummy"`, with an empty list — it would install nothing)
and **another project's file** (plenty of refdes, none of them on this board).
The ordinary case prints its coverage: `variant list covers 47 of 51 placed
component(s)`.

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

## Multi-stackup and rigid-flex

A rigid-flex design is several **zones**, each with its own stackup and
thickness. The export reads them from the design and builds the board as those
zones fused into one solid; a single-stackup board takes the ordinary path.

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

**Which side moves — the anchor.** The piece containing the **origin** stays in
the XY plane and everything beyond each bend swings from it. Allegro has the
same idea (*Setup – Anchor 3D View*), but in 24.1 the point it asks for never
reaches the board file, so the design cannot tell us and `[0, 0]` is the
convention instead. **Put the part of the board that should lie flat over the
origin**, or name another point in `gui.foldAnchor`. It decides the shape of the
fold, not just where it sits: with the anchor in the middle, two tails swing off
a held centre; at one end, the same two bends make a chain.

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
**Set `foldNeutral` to `0` for such a board.**

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

## Command line (without Allegro)

```
python -m stepbuilder                                        # the window
python -m stepbuilder STEP_DIR JSON_FILE OUTPUT_DIR          # one JSON, headless
python -m stepbuilder STEP_DIR JSON_DIR  OUTPUT_DIR --batch  # every variant
```

Flags: `--batch`, `--z-datum {top,bottom}`, `--color NAME|r,g,b|#rrggbb`,
`--rim-color …`, `--dated-name`, `--brd-name NAME` (names the output file; with
several variants it is ignored and each JSON's own stem names its output, or
they would collide), `--no-silkscreen`, `--no-silk-top`, `--no-silk-bottom`,
`--flat-silkscreen`, `--silk-flat-height MM`,
`--silk-layer-off LAYER` (repeatable), `--silk-color White|Black`,
`--ignore-soldermask`, `--flat` (do not fold), `--fold-anchor X,Y|auto`,
`--fold-neutral K`, `--fold-slice-angle DEG`,
`--board-mode {solid,layers,inspect}`, `--no-minimize`, `--legacy-color`,
`--quiet`. Exit code 0 on success, 1 on error.

## What is where

```
makeVariant3dIntermediates.il   reads the Allegro database, writes the JSON
simple3d.il                     the menu item, the launcher, the pre-flight check
simple3d_config.json            every setting, read by both halves
stepbuilder/
  core.py        geometry + assembly. No UI, no printing: reports via callbacks
  bend.py        folding a flex board along its bend areas
  colors.py      the board themes and rim options
  worker.py      the build, in a child process, so a crash cannot take the window
  gui.py         the tkinter window, a thin wrapper around core
  __main__.py    entry point: window, headless, or prefilled from Allegro
tools/, tests/   SKILL checks, the docs audit, 20 test suites, read-only probes
```

`QUICKSTART.md` is the five-minute version. `CHANGELOG.md` is what changed and
when. `PROJECT_NOTES_simple3d.md` is the development memo — how each decision
was reached, round by round; useful for working *on* the tool, not for using it.

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
   │  1. находит папку  rev/cad  (соседнюю с  rev/pcb )
   │  2. пишет туда по одному JSON на вариант с меткой "format": "simple3d"
   │  3. проверяет, что Python вообще запускается, и говорит, если нет
   └─ 4. открывает окно с уже заполненными путями
            └─ <плата>_simple_ДД_ММ_ГГГГ.step
```

Половины общаются через этот JSON, потому что ни одна не умеет работу другой:
SKILL читает базу Allegro, но не строит B-rep; OpenCASCADE строит STEP, но
ничего не знает про Allegro. Всё, что экспорт выяснил в Allegro, лежит в файле —
поэтому модель можно пересобрать иначе, не открывая плату заново.

Штатный индикатор Allegro на экране с момента нажатия Export: всё перечисленное
происходит до того, как появится наше окно. Рядом с платой ничего временного не
пишется.

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

**3. Файлы.** Склонируйте или распакуйте репозиторий; его корень уже устроен
так, как надо — оба `.il`, `simple3d_config.json` и пакет `stepbuilder\` в
**одной папке**, где вам удобно:

```
d:\Projects\OrCAD\Scripts\Simple3D\
├── makeVariant3dIntermediates.il     SKILL-экспортёр (читает плату)
├── simple3d.il                       пункт меню + запуск
├── simple3d_config.json              все настройки, читают обе половины
└── stepbuilder\                      пакет Python
```

Скачивание ZIP с GitHub заворачивает всё в лишнюю папку `Simple3D-main\`. Либо
распакуйте её *содержимое*, либо укажите `S3D_ScriptDir` на саму обёртку — но не
оставляйте эти два несогласованными.

Проверка из `cmd`:

```
cd /d d:\Projects\OrCAD\Scripts\Simple3D
python -m stepbuilder
```

Должно открыться окно, а в его логе — `Settings loaded from …`.

**4. Загрузка SKILL-файлов** из `allegro.ilinit` или вручную в каждой сессии:

```
load("d:/Projects/OrCAD/Scripts/Simple3D/makeVariant3dIntermediates.il")
load("d:/Projects/OrCAD/Scripts/Simple3D/simple3d.il")
```

Появится `File → Export → Simple 3D`. Одна настройка остаётся в `simple3d.il` и
должна совпадать с тем, куда вы положили файлы: **`S3D_ScriptDir`**. В конфиг её
перенести нельзя — именно она находит конфиг.

## Окно программы

Большинство органов управления говорят сами за себя. Вот те, о которых стоит
знать:

| Элемент | Что важно |
|---|---|
| **STEP files** | Папки с моделями, по одной в строке, **просматриваются по порядку**: побеждает первая, где нашёлся файл. Поэтому папка проекта, стоящая выше общей библиотеки, перекрывает отдельные модели. Каждая обходится рекурсивно. Имя, найденное дважды, называется в логе вместе с победившим путём. |
| **JSON file** | Один интермедиат или папка вариантов — тогда собираются все. Берутся только файлы с меткой `"format": "simple3d"`, остальное игнорируется и пишется в лог. |
| **Z = 0 at** | Какая грань — база отсчёта. Детали стоят на **паяльной маске** своей стороны: реальные площадки несут припой, который поднимает деталь до уровня маски. |
| **Board edge color** | Своё тело одного цвета, с которым может контрастировать торец, есть только у *Solid*, поэтому в двух других сшивках элемент гаснет, а не молча игнорируется. |
| **Body stitching** | Только для мультистэкапа. *Solid* — одно тело, самое компактное. *Solid colored layers* — одно тело, но границы слоёв сохранены, и торец показывает стек (примерно в 4.7 раза больше). *Not stitched* — каждый слой каждой зоны отдельной деталью, чтобы разобрать плату глазами. |
| **Do not include soldermask** | Убирает маску и смыкает стек к ядру ровно на снятую толщину, каждую сторону отдельно. Плата действительно становится тоньше — проверьте итог. |
| **Silkscreen: Top / Bottom** | Обе выключены — шелкография не строится вовсе, и файл заметно меньше. |
| **Make surface** | Легенда поверхностями, а не тонкими телами: примерно четверть её объёма в файле. Толщины у краски тогда нет, и в булевых операциях она не участвует. |
| **Silkscreen layers** | Галочка на каждый слой, *найденный в этом JSON*, с числом полигонов. Снимите и нажмите Generate снова — повторный экспорт не нужен. |
| **Fold flex bends** | Сгибать по областям сгиба. Выключено — плата экспортируется плоской. На плате без сгибов ничего не меняет. |
| **Compact STEP** | Убирает параметрические кривые на поверхностях — примерно вдвое меньший файл при той же геометрии. |

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
и `settings`. Окно записывает свою секцию при закрытии, поэтому следующий
запуск начинается с того, на чём вы остановились.

**Если файл не читается — его нет или он отредактирован в невалидный JSON —
ничего не записывается до конца сессии**, даже если вы почините его при
открытом окне. Поля на экране в этот момент содержат значения по умолчанию, а не
ваши настройки, и их запись затёрла бы только что исправленный файл. Лог при
каждом старте говорит, какой файл прочитан и разобрался ли он.

Ключи, которые имеет смысл править руками, — остальные повторяют элементы окна:

| Секция | Ключ | Что делает |
|---|---|---|
| `allegro` | `python` / `pythonw` | Интерпретатор. `pythonw` открывает окно **без консоли**; `""` откатывается на `python`. |
| | `menuLabel` / `commandName` | Текст пункта меню и имя команды. Читаются при загрузке, поэтому изменение требует перезагрузки SKILL. |
| | `defineAlwaysExportProp` | Заводить свойство **`ALWAYS_STEP_EXPORT`** в словаре свойств открытого проекта — при загрузке и перед каждым экспортом, — чтобы его можно было вешать из штатного диалога свойств Allegro. Деталь с этим свойством остаётся во всех вариантах. Заведение меняет плату, поэтому `false` не трогает ни один проект; экспорт при этом по-прежнему читает свойство там, где оно уже заведено. См. *Что попадает в экспорт*. |
| `gui` | `stepDirs` | Папки моделей в порядке поиска (см. таблицу выше). |
| | `boardMode` | `solid` / `layers` / `inspect` — то же, что *Body stitching*. |
| | `layerColors` | Цвет на каждый вид слоя (`copper`, `base`, `coverlay`, `adhesive`, `stiffener`, `soldermask`, `other`). По умолчанию — **собственные цвета материалов Allegro**, чтобы экспорт выглядел так же, как та же плата в 3D-канвасе Allegro. |
| | `foldAnchor` | Точка, остающаяся в плоскости XY, `[x, y]`. **По соглашению `[0, 0]`** — см. *Сгибание*. `"auto"` держит самый большой кусок. |
| | `foldNeutral` | Положение нейтральной оси как доля толщины (по умолчанию `0.5`). **Поставьте `0`, если области сгиба на плате соприкасаются** — см. *Сгибание*. |
| | `foldSliceAngle` | Угол дольки для сгиба, который пришлось гранить (по умолчанию `7.5`). Сгибы, построенные истинными цилиндрами, его игнорируют. |
| `settings` | `negativeLayers` | Слои стека, чьи нарисованные фигуры — **окна**, а не материал; сравнение по подстроке без учёта регистра. Покрытие, маска и паста рисуются так по соглашению; стиффенер, клей и эпоксид — наоборот. Добавьте слой сюда, если его тела получаются инвертированными. |
| `silkscreen` | `top` / `bottom` | Какие слои Allegro **собираются** — см. *Шелкография*. |

Остальное в `gui` повторяет окно и записывается при его закрытии — `zDatum`,
`boardColor`, `boardEdge`, `boardEdgeCustom`, `silkscreenTop`,
`silkscreenBottom`, `silkColor`, `silkscreenFlat`, `ignoreSoldermask`,
`foldBends`, `minimizeFileSize`, — плюс пять, о которых стоит сказать отдельно:

* `silkscreenFlatHeight` — мм между гранью платы и **плоской** легендой, чтобы
  они не были копланарны и не мерцали. По умолчанию `0.001`. Это не толщина
  краски: она в `settings.silkscreenThickness` и относится только к режиму тел.
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
любым компонентом: перечислена и не помечена — экспортируется; перечислена и
помечена — нет; **в списке её нет — нет**, что бы ни говорило `NO_STEP_EXPORT`.

**Символ без позиционного обозначения находится вне системы вариантов** и
экспортируется во всех. Allegro оставляет обозначение пустым, когда связанного
компонента нет, поэтому такую деталь физически нечем назвать в списке,
сгенерированном из схемы — сказать о ней там нечего, и убрать её может только
`NO_STEP_EXPORT`.

**`ALWAYS_STEP_EXPORT` — выход из этого правила.** Деталь с этим свойством
остаётся во всех вариантах, что бы ни говорил список; `NO_STEP_EXPORT`
по-прежнему сильнее, потому что «никогда» побеждает «всегда».

Свойство появилось из-за случая, который по данным не разрешается. **Площадка
под пайку провода** и **корпус разъёма** в базе одинаковы — обозначение,
STEP-модель, нет строки в BOM, не названы ни в одном варианте, — но корпус
должен исчезать вместе со своим разъёмом, а площадка часть **голой платы** и
нужна в каждом варианте: на чертеже, особенно на плате без шелкографии, именно
эти площадки монтажнику и надо видеть. Разница в намерении, поэтому она
записывается на детали.

В отличие от `NO_STEP_EXPORT`, который штатный, **этого свойства не существует,
пока его кто-нибудь не заведёт**, а пока не заведено — прицепить его нельзя
ничем. Поэтому `simple3d.il` заводит его как пользовательское свойство типа
BOOLEAN и дальше не вмешивается: на что вешать — решаете вы, через
**Edit → Properties**. Три следствия:

* Словарь свойств принадлежит **проекту**, а не установке, поэтому запись
  создаётся на каждую плату: по триггеру `open` и ещё раз в начале экспорта. При
  загрузке SKILL-файлов не происходит ничего — версия, писавшая в базу при
  загрузке, совпала с падениями Allegro при старте.
* **Имя — ещё не плата.** Allegro иногда стартует на пустышке вместо проекта; в
  неё ничего не пишется, а экспорт об этом говорит, вместо того чтобы собрать
  пустоту.
* Заведение **меняет плату**, и Allegro попросит её сохранить. Чтобы этого не
  было, поставьте `allegro.defineAlwaysExportProp` в `false`: экспорт
  по-прежнему читает свойство там, где оно уже заведено.
* У BOOLEAN-свойства **нет значения** — оно есть или его нет, и это ровно та
  проверка, которую делает экспорт. Чтобы снять пометку, свойство надо
  **удалить**, а не выставлять в false. Allegro говорит об этом сам.

Повесьте свойство на **определение компонента** — и оно закроет все экземпляры
библиотечной детали сразу: пометьте площадку в библиотеке, и платы править не
придётся.

`Variants.lst` читается **из папки, где лежит `.brd`** — там, где его держит
Allegro, — и больше нигде; если файла там нет, консоль называет проверенный
путь. Когда файл есть, пишется **по одному JSON на вариант** с именем
`<плата>_<вариант>`, и окно собирает каждый. Два вида неподходящего файла
отвергаются, а не экспортируются молча: **заглушка** (один вариант, обычно
`"dummy"`, с пустым списком — он не установил бы ничего) и **файл от другого
проекта** (обозначений много, но ни одного с этой платы). В обычном случае
печатается покрытие: `variant list covers 47 of 51 placed component(s)`.

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

## Мультистэкап и rigid-flex

Rigid-flex — это несколько **зон**, у каждой свой стек и своя толщина. Экспорт
читает их из проекта и собирает плату как эти зоны, слитые в одно тело; плата с
одним стекапом идёт обычным путём.

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

**Какая сторона двигается — якорь.** Кусок, содержащий **начало координат**,
остаётся в плоскости XY, а всё за каждым сгибом поворачивается от него. У
Allegro есть та же идея (*Setup – Anchor 3D View*), но в 24.1 запрошенная точка
до файла платы не доходит, поэтому проект нам её сообщить не может и соглашением
служит `[0, 0]`. **Положите ту часть платы, которая должна лежать плоско, на
начало координат** или назовите другую точку в `gui.foldAnchor`. Якорь решает
форму сгиба, а не только положение: если он в середине, два хвоста отгибаются от
удерживаемого центра; если с краю — те же два сгиба дают цепочку.

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
поставьте `foldNeutral` в `0`.**

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

## Командная строка (без Allegro)

```
python -m stepbuilder                                        # окно
python -m stepbuilder STEP_DIR JSON_FILE OUTPUT_DIR          # один JSON, без окна
python -m stepbuilder STEP_DIR JSON_DIR  OUTPUT_DIR --batch  # все варианты
```

Флаги: `--batch`, `--z-datum {top,bottom}`, `--color NAME|r,g,b|#rrggbb`,
`--rim-color …`, `--dated-name`, `--brd-name NAME` (имя выходного файла; при
нескольких вариантах игнорируется — иначе они столкнулись бы в одно имя, — и
каждый файл называется по имени своего JSON), `--no-silkscreen`,
`--no-silk-top`, `--no-silk-bottom`, `--flat-silkscreen`, `--silk-flat-height MM`,
`--silk-layer-off LAYER` (можно повторять), `--silk-color White|Black`,
`--ignore-soldermask`, `--flat` (не сгибать), `--fold-anchor X,Y|auto`,
`--fold-neutral K`, `--fold-slice-angle DEG`,
`--board-mode {solid,layers,inspect}`, `--no-minimize`, `--legacy-color`,
`--quiet`. Код возврата 0 при успехе, 1 при ошибке.

## Что где лежит

```
makeVariant3dIntermediates.il   читает базу Allegro, пишет JSON
simple3d.il                     пункт меню, запуск, предполётная проверка
simple3d_config.json            все настройки, читают обе половины
stepbuilder/
  core.py        геометрия и сборка. Без UI и печати: отчёт через колбэки
  bend.py        сгибание гибкой платы по областям сгиба
  colors.py      темы платы и варианты цвета торца
  worker.py      сборка в дочернем процессе, чтобы падение не унесло окно
  gui.py         окно tkinter, тонкая обёртка вокруг core
  __main__.py    точка входа: окно, консоль или запуск из Allegro
tools/, tests/   проверки SKILL, аудит документации, 20 наборов тестов, зонды
```

`QUICKSTART.md` — версия на пять минут. `CHANGELOG.md` — что и когда менялось.
`PROJECT_NOTES_simple3d.md` — рабочая записка разработки: как принималось каждое
решение, раунд за раундом; нужна для работы **над** инструментом, а не с ним.
