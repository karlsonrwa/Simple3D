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
   └─ 3. launches the Python GUI with the paths prefilled
            │  reads the tagged JSON(s), builds the STEP
            └─ <board>_simple_DD_MM_YYYY.step
```

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

`cadquery-ocp` is the OpenCASCADE geometry kernel with Python bindings (~165 MB).
It is the only dependency. That is the entire `requirements.txt`.

### 3. The files

Put the Python package and the two SKILL files where the settings expect them:

```
d:\Projects\OrCAD\Scripts\Simple3D\        ← ONE folder holds the whole tool
├── makeVariant3dIntermediates.il          ← SKILL exporter (fixes folded in)
├── simple3d.il                            ← the menu item + launcher
├── simple3d_config.json                   ← which layers are silkscreen, ink thickness
├── stepbuilder\                           ← the Python package (the FOLDER, not its contents)
│   ├── __main__.py
│   ├── core.py
│   ├── colors.py
│   └── gui.py
├── demo\                                 ← sample board + reference JSON/STEP (optional)
├── README.md
└── LICENSE
```

The most common install mistake is nesting `stepbuilder\` one level too deep
(`…\Simple3D\stepbuilder\stepbuilder\`). It must be exactly
`…\Simple3D\stepbuilder\__main__.py`. Verify from a `cmd`:

```
cd /d d:\Projects\OrCAD\Scripts\Simple3D
python -m stepbuilder
```

If the GUI opens, the layout is correct.

### 4. Load the SKILL files in Allegro

Add these to your `allegro.ilinit` (or load them manually each session):

```
load("d:/Projects/OrCAD/Scripts/Simple3D/makeVariant3dIntermediates.il")
load("d:/Projects/OrCAD/Scripts/Simple3D/simple3d.il")
```

`File → Export → Simple 3D` now appears.

## Settings (top of `simple3d.il`)

All settings use plain assignment (`=`), so editing the file and reloading it
always takes effect. Edit these values to match your machine:

| Setting | What it does |
|---|---|
| `S3D_ScriptDir` | The project folder — the one folder holding both `.il` files and the `stepbuilder` package. Used to launch Python without depending on the current directory. Set it to wherever you unpacked the project. |
| `S3D_Python` | Python executable. `"python"` if on PATH, else a full path like `"c:/Python312/python.exe"`. |
| `S3D_PythonW` | Console-less launcher (`pythonw.exe`). When set, the GUI opens with **no console window** and the launching cmd window closes at once. Set `""` to use `S3D_Python` instead. |
| `S3D_ModelLibDir` | Folder holding the footprint STEP models (referenced by `PKGDEF_STEP_FILE`). This becomes the GUI's "STEP files" path. If empty, the `cad` folder is used. |
| `S3D_DefaultColor` | Board colour pre-selected in the GUI. One of: `Black Blue Dark_green Green Purple Red White Yellow`. |
| `S3D_ConfigFile` | Path to `simple3d_config.json` — the silkscreen layer list and ink settings. Set `""` to use the built-in defaults instead. |
| `S3D_DefaultSilkColor` | Silkscreen colour pre-selected in the GUI: `"White"` or `"Black"`. |
| `S3D_CommandVisible` / `S3D_CommandName` | Menu label and internal command name. |

## The GUI

| Control | Purpose |
|---|---|
| **STEP files** | Folder with the footprint STEP models (from `S3D_ModelLibDir`). |
| **JSON file** | The intermediate JSON, or a folder of variant JSONs. Only files tagged `"format": "simple3d"` are used; others are ignored and logged. |
| **Output** | Where the `.step` is written (the `cad` folder). |
| **Board colour** | The eight Allegro 3D-canvas themes, with a colour swatch. |
| **Board edge** | Rim / side-wall colour: same as board, cream dielectric, or a custom `r,g,b` / `#rrggbb`. |
| **Z = 0 at** | Which board face is the datum: top or bottom. Parts sit on the soldermask of their side (real pads carry solder that lifts the part to mask level). |
| **Export silkscreen** | Build the printed legend as thin solids on both board faces. Off makes a noticeably smaller file. |
| **Colour** (next to it) | Silkscreen ink: **White** or **Black**. Those are the two colours legend ink actually comes in, so it is a closed choice. |
| **Flat** | Draw the legend as surfaces instead of thin solids: about a quarter of the silkscreen's file size. See *Silkscreen file size* below. |
| **Minimise file size** | Drops parametric surface curves (`write.surfacecurve.mode = 0`), roughly halving the file with identical geometry. |
| **Generate** | Builds one file, or every queued variant. |

Log messages are colour-coded: **orange** for warnings, **dark red** for errors,
green for success.

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
* Each **silkscreen side is its own part**, so it can be hidden or recoloured in
  the viewer without touching the board.

## Silkscreen

Enabled by default. The legend is exported as real geometry: filled regions
extruded into thin solids that sit on the outer face of each side and grow away
from the board, so they never intersect it.

**Which layers count** is set in `simple3d_config.json`, next to the two `.il`
files — edit that, not the source, if your layer naming differs:

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

### Silkscreen file size

A legend is thousands of small faces, so it costs real bytes. Measured on a
150-polygon legend, same geometry throughout:

| representation | size | note |
|---|---|---|
| solids, **Minimise file size** on | 2191 kB | the default |
| solids, Minimise **off** | 5769 kB | 2.6x worse - leave the box ticked |
| **Flat** (surfaces) | 566 kB | **26%** of the default |
| boolean-fused into one solid | 3377 kB | *larger*, and slower - not offered |

Three levers, in order of effect:

1. **Flat.** A solid costs one face per polygon edge plus a top and a bottom; a
   surface costs one face. The face sits at the ink's outer surface, so it does
   not z-fight with the board. What you give up: the ink is a surface, not a
   solid - no thickness to measure, and nothing downstream can do boolean work
   with it. For looking at, rendering and sharing a board, that costs nothing.
2. **Drop layers you do not need** from `simple3d_config.json`. Reference
   designators are usually most of the legend by far; removing
   `REF DES/SILKSCREEN_*` from the layer lists keeps outlines and polarity marks
   while cutting the bulk. No code involved, and the JSON gets smaller too.
3. **Turn silkscreen off** for working exports and back on for the final one.

Fusing the legend into one solid was measured and is *counterproductive*: a
boolean union replaces analytic planes and cylinders with general surfaces, and
after clipping the strokes barely overlap, so there is nothing much for it to
remove. It makes the file half again as large and takes longer.

## Board thickness

The board solid is `dielectrics + planes + conductors + both soldermasks`.
Silkscreen and paste mask are excluded. Example, a 2-layer stackup:

```
1.464 (dielectric) + 0.045 + 0.045 (copper) + 0.025 + 0.025 (mask) = 1.604 mm
```

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

**Multi-stackup / rigid-flex boards are not supported.** The exporter sums a
single stackup into one thickness and extrudes one flat board. A design with
more than one stackup zone will be exported as a single averaged-thickness slab,
which is wrong for those boards. Support may be added later.

**Component B-rep comes from your library STEP models.** File size beyond the
board itself is dominated by those models; "Minimise file size" cannot shrink
geometry that lives inside them.

**Silkscreen solids are not fused into one.** The legend is thousands of
overlapping strokes and glyphs; a boolean union of that many thin prisms costs
minutes of solver time and can fail outright, while buying nothing visible. Each
side is therefore a compound of separate solids — correct to look at, export and
render, but not a single manifold solid if you intend to do boolean work on the
ink itself.

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
`--dated-name`, `--brd-name NAME` (single json only; with several variants each
json's own stem names its output), `--no-silkscreen`, `--flat-silkscreen`,
`--silk-color White|Black`, `--no-minimize`, `--legacy-color`, `--quiet`.
Exit code 0 on success, 1 on error.

## Package layout

```
stepbuilder/
  core.py       geometry + assembly. No UI, no printing: reports via callbacks.
  colors.py     the eight board themes + rim options.
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
   └─ 3. запускает Python-окно с уже подставленными путями
            │  читает помеченные JSON, собирает STEP
            └─ <плата>_simple_ДД_ММ_ГГГГ.step
```

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

`cadquery-ocp` — это геометрический кернел OpenCASCADE с Python-обвязкой (~165 МБ).
Это единственная зависимость. Весь `requirements.txt` состоит из неё.

### 3. Файлы

Разложите Python-пакет и два SKILL-файла туда, где их ждут настройки:

```
d:\Projects\OrCAD\Scripts\Simple3D\        ← ОДНА папка со всем инструментом
├── makeVariant3dIntermediates.il          ← SKILL-экспортёр (правки внутри)
├── simple3d.il                            ← пункт меню + запуск
├── simple3d_config.json                   ← слои шелкографии и толщина краски
├── stepbuilder\                           ← Python-пакет (сама ПАПКА, не её содержимое)
│   ├── __main__.py
│   ├── core.py
│   ├── colors.py
│   └── gui.py
├── demo\                                 ← пример платы + эталонные JSON/STEP (опц.)
├── README.md
└── LICENSE
```

Самая частая ошибка установки — вложить `stepbuilder\` на уровень глубже
(`…\Simple3D\stepbuilder\stepbuilder\`). Должно быть ровно
`…\Simple3D\stepbuilder\__main__.py`. Проверьте из `cmd`:

```
cd /d d:\Projects\OrCAD\Scripts\Simple3D
python -m stepbuilder
```

Если окно открылось — раскладка верная.

### 4. Загрузка SKILL-файлов в Allegro

Добавьте в `allegro.ilinit` (или загружайте вручную каждую сессию):

```
load("d:/Projects/OrCAD/Scripts/Simple3D/makeVariant3dIntermediates.il")
load("d:/Projects/OrCAD/Scripts/Simple3D/simple3d.il")
```

Пункт `File → Export → Simple 3D` появится в меню.

## Настройки (вверху `simple3d.il`)

Все настройки используют обычное присваивание (`=`), поэтому редактирование файла
и его перезагрузка всегда применяются. Отредактируйте значения под свою машину:

| Настройка | Что делает |
|---|---|
| `S3D_ScriptDir` | Папка проекта — одна папка, где лежат оба `.il`-файла и пакет `stepbuilder`. Нужна, чтобы запускать Python независимо от текущего каталога. Укажите ту, куда распаковали проект. |
| `S3D_Python` | Исполняемый Python. `"python"`, если на PATH, иначе полный путь вроде `"c:/Python312/python.exe"`. |
| `S3D_PythonW` | Запуск без консоли (`pythonw.exe`). Когда задан, окно GUI открывается **без окна консоли**, и окно cmd закрывается сразу. Поставьте `""`, чтобы использовать `S3D_Python`. |
| `S3D_ModelLibDir` | Папка с STEP-моделями посадочных мест (по `PKGDEF_STEP_FILE`). Становится путём «STEP files» в GUI. Если пусто — берётся папка `cad`. |
| `S3D_DefaultColor` | Цвет платы, выбранный в GUI по умолчанию. Один из: `Black Blue Dark_green Green Purple Red White Yellow`. |
| `S3D_ConfigFile` | Путь к `simple3d_config.json` — список слоёв шелкографии и настройки краски. `""` — использовать встроенные значения по умолчанию. |
| `S3D_DefaultSilkColor` | Цвет шелкографии, выбранный в GUI по умолчанию: `"White"` или `"Black"`. |
| `S3D_CommandVisible` / `S3D_CommandName` | Название пункта меню и внутреннее имя команды. |

## Окно программы

| Элемент | Назначение |
|---|---|
| **STEP files** | Папка с STEP-моделями посадочных мест (из `S3D_ModelLibDir`). |
| **JSON file** | Промежуточный JSON или папка с JSON-вариантами. Берутся только файлы с меткой `"format": "simple3d"`, остальные игнорируются с записью в лог. |
| **Output** | Куда пишется `.step` (папка `cad`). |
| **Board colour** | Восемь тем 3D-канвы Allegro, с образцом цвета. |
| **Board edge** | Цвет торца / боковых стенок: как плата, кремовый диэлектрик или свой `r,g,b` / `#rrggbb`. |
| **Z = 0 at** | Какая грань платы — ноль: верхняя или нижняя. Компоненты садятся на маску своей стороны (на площадках реально есть припой, поднимающий деталь до уровня маски). |
| **Export silkscreen** | Строить шелкографию тонкими телами на обеих сторонах платы. Выключение заметно уменьшает файл. |
| **Colour** (рядом) | Цвет краски: **White** или **Black**. Это те два цвета, которыми шелкография реально печатается, поэтому выбор закрытый. |
| **Flat** | Рисовать легенду поверхностями вместо тонких тел: примерно вчетверо меньший вклад в размер файла. См. «Размер файла и шелкография» ниже. |
| **Minimise file size** | Убирает параметрические кривые поверхностей (`write.surfacecurve.mode = 0`), примерно вдвое уменьшая файл при идентичной геометрии. |
| **Generate** | Собирает один файл или все варианты из очереди. |

Сообщения в логе раскрашены: **оранжевый** — предупреждения, **тёмно-красный** —
ошибки, зелёный — успех.

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

Включена по умолчанию. Легенда экспортируется настоящей геометрией: залитые
области выдавливаются в тонкие тела, лежащие на внешней грани каждой стороны и
растущие наружу от платы, так что они с ней не пересекаются.

**Какие слои считать шелкографией**, задаётся в `simple3d_config.json` рядом с
двумя `.il`-файлами — правьте его, а не исходник, если у вас другое именование
слоёв:

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

### Размер файла и шелкография

Легенда — это тысячи мелких граней, и она стоит реальных байт. Замерено на
легенде из 150 полигонов, геометрия во всех случаях одна и та же:

| представление | размер | примечание |
|---|---|---|
| тела, **Minimise file size** включён | 2191 КБ | по умолчанию |
| тела, Minimise **выключен** | 5769 КБ | в 2.6 раза хуже — галочку не снимайте |
| **Flat** (поверхности) | 566 КБ | **26%** от значения по умолчанию |
| объединение булевой операцией в одно тело | 3377 КБ | *больше* и медленнее — не предлагается |

Три рычага, по убыванию эффекта:

1. **Flat.** Тело стоит по грани на каждое ребро полигона плюс верх и низ;
   поверхность — одну грань. Грань кладётся на внешнюю поверхность краски,
   поэтому не конфликтует с гранью платы по глубине. Чем платите: краска
   становится поверхностью, а не телом — толщину не измерить и булевы операции
   с ней невозможны. Для просмотра, рендера и передачи платы это ничего не стоит.
2. **Уберите ненужные слои** из `simple3d_config.json`. Позиционные обозначения
   обычно составляют бо́льшую часть легенды; удаление `REF DES/SILKSCREEN_*` из
   списков оставит контуры и метки полярности, но срежет основной объём. Кода не
   требует, и JSON тоже становится меньше.
3. **Выключайте шелкографию** для рабочих выгрузок и включайте для финальной.

Объединение легенды в одно тело было измерено и оказалось **контрпродуктивным**:
булева операция заменяет аналитические плоскости и цилиндры общими
поверхностями, а после обрезки штрихи почти не перекрываются, так что удалять
ей особо нечего. Файл вырастает в полтора раза, и это дольше.

## Толщина платы

Тело платы — это `диэлектрики + плейны + проводники + обе паяльные маски`.
Шелкография и паяльная паста не учитываются. Пример, двухслойный стек:

```
1.464 (диэлектрик) + 0.045 + 0.045 (медь) + 0.025 + 0.025 (маска) = 1.604 мм
```

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

**Платы с мультистэкапом / rigid-flex не поддерживаются.** Экспортёр суммирует
один стек в одну толщину и экструдирует одну плоскую плату. Дизайн с более чем
одной зоной стека будет экспортирован как плита усреднённой толщины, что для
таких плат неверно. Поддержка может быть добавлена позже.

**B-rep компонентов берётся из ваших STEP-моделей библиотеки.** Размер файла
сверх самой платы определяется этими моделями; «Minimise file size» не может
уменьшить геометрию, которая лежит внутри них.

**Тела шелкографии не объединяются в одно.** Легенда — это тысячи
пересекающихся штрихов и глифов; булево объединение такого количества тонких
призм стоит минут работы солвера и может вовсе не сойтись, не давая при этом
ничего видимого. Поэтому каждая сторона — компаунд отдельных тел: корректный для
просмотра, экспорта и рендера, но не единое манифолдное тело, если вы
собираетесь делать булевы операции с самой краской.

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
`--dated-name`, `--brd-name ИМЯ` (только для одиночного json; при нескольких
вариантах имя каждому даёт стем его json), `--no-silkscreen`,
`--flat-silkscreen`, `--silk-color White|Black`,
`--no-minimize`, `--legacy-color`, `--quiet`. Код возврата 0 при успехе, 1 при ошибке.

## Структура пакета

```
stepbuilder/
  core.py       геометрия + сборка. Без UI и print: отчёты через колбэки.
  colors.py     восемь тем платы + опции торца.
  gui.py        окно tkinter. Тонкая обёртка над core.
  __main__.py   точка входа: GUI, без окна, или --gui prefill для Allegro.
```

---

## Changelog / История изменений

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
  per-refdes wrapper sub-assemblies. GUI: the board-colour swatch now sits next
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

- **2026-07-18** — Coloured log (orange warnings, dark-red errors); JSON format
  marker so foreign `.json` files are ignored; rim-colour fix (was landing on a
  flat face); documented `ncroute_path` and multi-stackup limitations; settings
  switched from `defvar` to `=`; self-deleting launch batch; console-less
  `pythonw` launch. Bilingual README created.
