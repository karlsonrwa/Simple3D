# Simple 3D — quick reference / краткая справка

[English](#english) · [Русский](#русский)

<a name="english"></a>

# English

Exports an Allegro board to a STEP assembly: the board solid at its true
thickness with cutouts and holes, the component models from Allegro's STEP
mapping, and optionally the silkscreen. Full description, with the reasons:
[README.md](README.md).

## Running it

1. In Allegro PCB Editor: **File → Export → Simple 3D**. The design units must
   be **mm**.
2. The board is read and `<board>.json` written into the `cad` folder beside
   `pcb` (or beside the `.brd` when there is none); then the window opens with
   the paths filled in. Allegro's own progress form covers all of that — our
   window appears at the very end.
3. Press **Generate**. The rest of the window greys out and the button becomes
   **Cancel**.

## The window

**Input**
- **STEP files** — the model folders, **one per line**, searched top to bottom:
  the first one holding the file wins, so a project folder above the shared
  library overrides individual models. Subfolders are searched too. **Add...**
  appends; reorder in the text itself. Right-click any path field for Cut /
  Copy / Paste / Select all. A folder with characters outside ASCII (Cyrillic)
  is named at the top of the log: the build reads it, Allegro's own half may
  not - if a model comes out missing, start there.
- **JSON file** — the intermediate (filled in for you); a folder builds every
  variant in it.
- **Output** — where the STEP goes.

**Board options**
- **Board color** — 8 themes from Allegro's own palette (Dark_green and so on).
- **Board edge color** — the rim: `Same as board`, `Cream` or `Custom…`, which
  makes the swatch beside it live. Only `Solid` has one uniformly colored body
  for a rim to contrast with, so this greys out in the other two stitchings.
- **Z = 0 at** — which board face the origin sits on, top or bottom.
- **Body stitching** — how the board body is put together, on any board: an
  ordinary one has no zones, so its outline becomes one implicit zone on its
  single stackup.
  - `Solid` — one body in one color, the smallest file;
  - `Solid colored layers` — one body, but the layer interfaces are kept and
    every face is colored by the kind of layer, so the rim shows the stack;
  - `Not stitched` — every layer its own part, to take the board apart by eye.

  The last two need the stackup layers: an intermediate from an older version
  says so in the log and falls back to one solid. Both use the swatch row below
  — copper, base, coverlay, adhesive, stiffener, soldermask; **Reset colors**
  puts Allegro's material colors back.
- **Do not include soldermask layers** — the stack closes up toward the core by
  what was removed, so the board really does get thinner.
- **Fold flex bends** — fold along Allegro's bend areas (*Setup – Bend*); the
  board, the legend and the components all move together. On by default, and a
  board without bend areas is unaffected. What stays in the XY plane is the
  piece lying over the **origin** — put whatever should stay flat there, or name
  another point in `gui.foldAnchor`. If the log says two bends claim the same
  material, set `gui.foldNeutral` to `0` (README, *The K factor*).

**Silk options**
- **Top**/**Bottom** tickboxes, **White/Black** for the ink, and on its own line
  **Make surface (minimum file size)** — surfaces instead of thin solids. With
  both sides off the whole group greys out.
- Inside it, a **Layers** group — the layers found in this JSON, each with its
  polygon count (**All**/**None**). A side that is switched off greys its own.

**Compact STEP (reuse component geometry)** — one shared part per model, and no
parametric surface curves.

## The result

`<board>_simple_DD_MM_YYYY.step`; a name that already exists gets a trailing
`_`. A `Variants.lst` beside the `.brd` gives one STEP per variant — it is
looked for there and nowhere else, and when there is none the console says which
path it tried and exports everything into one file.

The export also writes **the whole board** — every component except those marked
`NO_STEP_EXPORT` — as `<board>.json`, for the drawing that has to show the bare
board rather than one assembly. `settings.exportFullBoard` turns it off; the
**Build the full-board file too** checkbox decides whether a queued folder
builds it.

## Worth knowing

- **Board thickness** = dielectrics + planes + conductors + both soldermasks;
  silkscreen and paste are not part of it.
- **Mechanical parts** (holders, brackets) are exported even without a reference
  designator — a `PKGDEF_STEP_FILE` on the symbol is enough.
- **`NO_STEP_EXPORT`** on the symbol / component / component definition keeps a
  part out of the export; each one is named in the console.
- **The variant list decides what is installed**, but only for parts that have a
  reference designator — a symbol without one cannot be named in a list, so it
  is in every variant. **`ALWAYS_STEP_EXPORT`** is the way back in: a part
  carrying it stays in every variant even when the list omits it, which is what
  a wire-solder pad needs. Simple 3D creates that property in the board; you
  attach it through Edit → Properties. A variant with every part set to *not
  installed* gives the **bare board** — that is how one is asked for; there is
  no checkbox.
- **The silkscreen is the same in every variant** — one bare board is
  manufactured for all of them.

## If something is wrong

- Read the Allegro console (warnings orange, errors red) and the window's log.
  The line `Settings loaded from …` confirms the settings were read.
- **Your settings live in `simple3d_config.local.json`**, beside the tracked
  `simple3d_config.json`: only what differs from the shipped default, and not in
  git, so an update cannot touch your model folders. The shipped files hold no
  path at all — where the tool is installed comes from `set SIMPLE3D_DIR = …` in
  your own `pcbenv\env`, or from the folder `simple3d.il` was loaded from; the
  console says which.
- Python 3.10 or newer and `cadquery-ocp` (OpenCASCADE) are required; the script
  checks the interpreter before opening the window, and the console names the
  interpreter that answered. If installing something else (node.js does this)
  puts a second Python ahead of yours on PATH, pin the one you meant by full
  path in the `allegro` section of `simple3d_config.local.json`.
- A window that vanished mid-build means OpenCASCADE died, not Simple 3D: the
  window survives that and shows the exit code with advice. What usually gets a
  board through: **Body stitching → Not stitched** (which fuses nothing) or a
  coarser `gui.foldSliceAngle`.
- Allegro sometimes comes up on an empty design rather than your board; the
  export refuses it and says so. Open the `.brd` itself and run it again.
- **Components and legend in the STEP but no board?** An intermediate written
  before 2026-08-11 repeated the through-holes in every file after the first —
  usually the whole-board one — and two identical holes leave OpenCASCADE with
  nothing to build. The current version drops the repeats and says so in the
  log; re-export from Allegro to get a clean file.

---

<a name="русский"></a>

# Русский

Экспорт платы Allegro в STEP-сборку: тело платы в истинной толщине с вырезами и
отверстиями, 3D-модели компонентов из STEP-маппинга Allegro и, по желанию,
шелкография. Полное описание, с обоснованиями, — в [README.md](README.md).

## Запуск

1. В Allegro PCB Editor: **File → Export → Simple 3D**. Единица измерения
   дизайна должна быть **мм**.
2. Плата читается, `<плата>.json` пишется в папку `cad` рядом с `pcb` (или
   рядом с самим `.brd`, если её нет), затем открывается окно с уже
   заполненными путями. Всё это время на экране форма прогресса Allegro — наше
   окно появляется в самом конце.
3. Нажать **Generate**. Остальное окно гаснет, а кнопка превращается в
   **Cancel**.

## Окно

**Input**
- **STEP files** — папки с моделями, **по одной на строку**, просматриваются
  сверху вниз: побеждает первая, где есть нужный файл, поэтому проектная папка
  выше общей библиотеки перекрывает отдельные модели. Вложенные подпапки ищутся
  сами. **Add...** дописывает папку в конец, порядок правится прямо в тексте.
  Правая кнопка в любом поле пути — Cut / Copy / Paste / Select all. Папка с
  символами вне ASCII (кириллица) называется в начале журнала: сборка её
  читает, половина Allegro — не всегда; если модель пропала, начинайте с
  этого.
- **JSON file** — промежуточный JSON (подставляется автоматически); папка
  собирает все лежащие в ней варианты.
- **Output** — куда положить STEP.

**Board options**
- **Board color** — цвет платы, 8 тем из палитры Allegro (Dark_green и др.).
- **Board edge color** — цвет торца: `Same as board`, `Cream` или `Custom…`,
  который активирует квадратик рядом. Своё тело одного цвета, с которым может
  контрастировать торец, есть только у `Solid`, поэтому в двух других сшивках
  элемент гаснет.
- **Z = 0 at** — где начало координат по Z: верх или низ платы.
- **Body stitching** — как собрано тело платы, на любой плате: у обычной зон
  нет, поэтому её контур становится одной неявной зоной на единственном стекапе.
  - `Solid` — одно тело одного цвета, самый лёгкий файл;
  - `Solid colored layers` — одно тело, но границы слоёв сохранены и каждая
    грань покрашена по виду слоя, торец показывает стек;
  - `Not stitched` — каждый слой отдельной деталью, чтобы разобрать глазами.

  Двум последним нужны слои стека: интермедиат от старой версии их не несёт —
  лог об этом скажет и соберёт одно тело. Обе пользуются рядом квадратиков ниже
  — медь, база, покров, адгезив, упрочнитель, паяльная маска; **Reset colors**
  возвращает цвета материалов Allegro.
- **Do not include soldermask layers** — стек смыкается к ядру на убранную
  толщину, и плата действительно становится тоньше.
- **Fold flex bends** — согнуть плату по зонам сгиба из Allegro (*Setup –
  Bend*); плата, легенда и компоненты едут вместе. Включено по умолчанию, на
  плате без зон сгиба ничего не меняет. В плоскости XY остаётся тот кусок, над
  которым лежит **начало координат**, — разместите там то, что должно остаться
  плоским, или укажите другую точку в `gui.foldAnchor`. Если в логе написано,
  что два сгиба претендуют на один материал, поставьте `gui.foldNeutral` в `0`
  (README, *K-фактор*).

**Silk options**
- Галочки **Top**/**Bottom**, цвет **White/Black**, отдельной строкой
  **Make surface (minimum file size)** — поверхности вместо тонких тел. Если
  сняты обе стороны, вся группа гаснет.
- Внутри отдельная группа **Layers** — слои, найденные в этом JSON, у каждого
  число полигонов (**All**/**None**). Выключенная сторона свои слои сереет.

**Compact STEP (reuse component geometry)** — одна общая деталь на модель и
отказ от поверхностных кривых.

## Результат

Файл `<плата>_simple_ДД_ММ_ГГГГ.step`; при совпадении имени в конец добавляется
`_`. `Variants.lst` рядом с `.brd` даёт по одному STEP на вариант — ищется он
только там, и если его нет, консоль пишет, по какому пути смотрела, и
экспортирует всё одним файлом.

Экспорт дополнительно пишет **всю плату** — все компоненты, кроме помеченных
`NO_STEP_EXPORT`, — файлом `<плата>.json`: для чертежа, которому нужна голая
плата, а не конкретная сборка. Отключается через `settings.exportFullBoard`;
галочка **Build the full-board file too** решает, собирать ли его, когда в
очереди папка.

## Что важно знать

- **Толщина платы** = диэлектрики + плейны + проводники + обе паяльные маски;
  шелкография и паста в толщину не входят.
- **Механические детали** (держатели, кронштейны) экспортируются, даже если у
  них нет позиционного обозначения — достаточно `PKGDEF_STEP_FILE` на символе.
- **`NO_STEP_EXPORT`** на символе / компоненте / его определении исключает
  деталь из экспорта; каждая названа в консоли.
- **Что установлено, решает список варианта**, но только для деталей с
  позиционным обозначением: символ без обозначения списком описать нельзя,
  поэтому он есть во всех вариантах. **`ALWAYS_STEP_EXPORT`** — путь обратно:
  деталь с этим свойством остаётся во всех вариантах, даже если список её не
  перечисляет, — то, что нужно площадке под пайку провода. Свойство заводится в
  плате самим Simple 3D, а вешается штатно, через Edit → Properties. Вариант,
  где все детали помечены *not installed*, даёт **голую плату** — так она и
  заказывается, отдельной галочки нет.
- **Шелкография одинакова во всех вариантах** — текстолит производится один раз
  под все сборки.

## Если что-то не так

- Смотрите консоль Allegro (предупреждения — оранжевым, ошибки — красным) и лог
  в окне. Строка `Settings loaded from …` подтверждает, что настройки прочитаны.
- **Ваши настройки лежат в `simple3d_config.local.json`** рядом с отслеживаемым
  `simple3d_config.json`: только то, что отличается от поставляемого умолчания,
  и вне git — поэтому обновление не тронет ваши папки моделей. В поставляемых
  файлах путей нет вообще: где установлен инструмент, берётся из
  `set SIMPLE3D_DIR = …` в вашем `pcbenv\env` либо из папки, откуда загружен
  `simple3d.il`; консоль говорит, что сработало.
- Нужен Python 3.10 или новее и пакет `cadquery-ocp` (OpenCASCADE); перед
  запуском GUI скрипт проверяет интерпретатор и печатает в консоль тот, который
  ответил. Если установка чего-то ещё (так делает node.js) поставила второй
  Python впереди вашего в PATH — закрепите нужный по полному пути в секции
  `allegro` файла `simple3d_config.local.json`.
- Окно исчезло во время сборки — значит упал OpenCASCADE, а не Simple 3D: окно
  переживает это и показывает код выхода вместе с советом. Что обычно помогает:
  **Body stitching → Not stitched** (там ничего не сплавляется) или более
  крупный `gui.foldSliceAngle`.
- Allegro иногда открывается на пустом проекте вместо вашей платы; экспорт
  откажется работать и скажет об этом. Откройте сам `.brd` и запустите снова.
- **В STEP есть компоненты и шелкография, а тела платы нет?** Интермедиат,
  записанный до 2026-08-11, повторял сквозные отверстия в каждом файле после
  первого — обычно это файл полной платы, — а два одинаковых отверстия не
  оставляют OpenCASCADE ничего. Текущая версия отбрасывает повторы и пишет об
  этом в лог; переэкспортируйте плату из Allegro, чтобы файл был чистым.
