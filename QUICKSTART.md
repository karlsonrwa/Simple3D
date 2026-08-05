# Simple 3D — quick reference / краткая справка

[English](#english) · [Русский](#русский)

<a name="english"></a>

# English

Exports an Allegro board to a STEP assembly: the board solid at its true
thickness with cutouts and holes, the component 3D models from Allegro's STEP
mapping, and optionally the silkscreen. The full description is in
[README.md](README.md); this is the short version.

## Running it

1. In Allegro PCB Editor: **File → Export → Simple 3D**.
2. The script reads the board, writes the intermediate `<board>.json` into the
   `cad` folder and opens the window with the paths already filled in. While
   that happens Allegro's own progress form is on screen and names each stage —
   our window appears at the very end.
3. Press **Generate**. While it builds, the rest of the window is greyed out
   and that button becomes **Cancel**.

The design units must be **mm**.

## The window

**Input**
- **STEP files** — folders holding the component STEP models, **one per line**.
  Searched top to bottom: the first folder that has the file wins, so put a
  project folder **above** the shared library to override individual models.
  Subfolders are searched on their own and need no entry. **Add...** appends a
  folder; the order is edited in the text itself.
- **JSON file** — the intermediate JSON (filled in for you).
- **Output** — where the STEP goes.

**Board options**
- **Board color** — 8 themes from Allegro's own palette (Dark_green and so on).
- **Board edge color** — the rim: `Same as board`, `Cream` or `Custom…`. For
  `Custom…` the swatch beside it becomes live; click it to pick.
- **Z = 0 at** — which board face the origin sits on, top or bottom.
- **Body stitching** — how the board body is put together. Multi-stackup /
  rigid-flex only:
  - `Solid` — one body in one color, the smallest file;
  - `Solid colored layers` — one body, but the layer interfaces are kept and
    every face is colored by the kind of layer, so the rim shows the stack;
  - `Not stitched` — every layer its own part, for taking the board apart by eye.
  For the last two there is a row of swatches below: copper, base, coverlay,
  adhesive, stiffener, soldermask. Click one to pick its color; **Reset colors**
  puts Allegro's material colors back.
- **Do not include soldermask layers** — leave the mask out; the stack closes up
  toward the core by what was removed, so the board really does get thinner.
- **Fold flex bends** — fold the board along Allegro's bend areas (*Setup –
  Bend*): the board, the legend and the components all move together. On by
  default; does nothing on a board without bend areas. Unticked gives the flat
  board.
  **The part of the board over the ORIGIN is the part that stays in the XY
  plane** — put whatever should lie flat over it, or name another point in
  `gui.foldAnchor`.
  If the log says two bends claim the same material while their drawn bend areas
  do not overlap, set `gui.foldNeutral` to `0`: that is how Allegro lays its flat
  pattern out, and on a board whose bend areas touch (a flex rolled into a ring)
  it is the only value that fits. The log names the number itself.

**Silk options**
- **Top**/**Bottom** tickboxes, **White/Black** for the ink, and on its own line
  **Make surface (minimum file size)** — surfaces instead of thin solids. With
  both sides off the whole group greys out.
- Inside it, a **Layers** group — which layers count as silkscreen (tickboxes;
  **All**/**None**). A side that is switched off greys its own layers.

**Compact STEP (reuse component geometry)** — a smaller file: one shared part
per model, plus dropping the parametric surface curves.

## The result

`<board>_simple_DD_MM_YYYY.step`. A name that already exists gets a trailing
`_`. With a `Variants.lst` beside the `.brd` you get one STEP per variant. It is
looked for there and nowhere else; when there is none, the console says which
path it tried and exports every component into one file.

Even with variants, the export also writes **the whole board** — every component
except those marked `NO_STEP_EXPORT` — as `<board>.json`, for the drawing that
has to show the bare board rather than one assembly. `settings.exportFullBoard`
turns it off; the **Build the full-board file too** checkbox decides whether a
queued folder builds it.

## Worth knowing

- **Board thickness** = dielectrics + planes + conductors + both soldermasks.
  Silkscreen and paste are not part of it.
- **Mechanical parts** (holders, brackets) are exported even without a reference
  designator — a `PKGDEF_STEP_FILE` on the symbol is enough.
- **`NO_STEP_EXPORT`** on the symbol / component / component definition keeps a
  part out of the export; each one is named in the console.
- **The variant list decides what is installed**: everything with a reference
  designator reaches the model only if the variant being built lists it. A
  symbol **without** one (a bracket, a holder — anything placed straight in
  Allegro) cannot be named in the list, so it is in every variant.
- **`ALWAYS_STEP_EXPORT`** is the opposite: a part carrying it stays in every
  variant even when the list does not name it. This is for wire-solder pads —
  they have a refdes, they are not in the BOM, and a drawing needs them. Simple
  3D creates the property in the board when it opens (and again before every
  export); attaching it is ordinary Edit → Properties work.
- **The silkscreen is the same in every variant** — the bare board is
  manufactured once for all of them.

## If something is wrong

- Read the Allegro console (warnings orange, errors red) and the window's log.
  The line `Settings loaded from …` confirms the settings were read.
- **Your settings live in `simple3d_config.local.json`**, beside the tracked
  `simple3d_config.json`. The window writes only the local one and it is not
  in git, so an update cannot conflict with your model folders or overwrite
  them. Where the tool itself is installed is the exception - put
  `set SIMPLE3D_DIR = …` in your own `pcbenv\env`.
- Python 3.10 or newer and the `cadquery-ocp` package (OpenCASCADE) are
  required. Before opening the window the script checks the interpreter and says
  so if something is missing.
- If the window vanished mid-build, OpenCASCADE died rather than Simple 3D: the
  window survives that and shows the exit code together with advice. What
  usually gets a board through: **Body stitching → Not stitched** (which fuses
  nothing) or a coarser `gui.foldSliceAngle`.
- If Allegro comes up on an empty design rather than your board — it does that
  now and then when started from its own icon — the export refuses it and says
  so. Open the `.brd` itself and run it again.

---

<a name="русский"></a>

# Русский

Экспорт платы Allegro в STEP-сборку: тело платы в истинной толщине с вырезами и
отверстиями, 3D-модели компонентов из STEP-маппинга Allegro и, по желанию,
шелкография. Полное описание — в [README.md](README.md); здесь только суть.

## Запуск

1. В Allegro PCB Editor: **File → Export → Simple 3D**.
2. Скрипт читает плату, пишет промежуточный `<плата>.json` в папку `cad` и
   открывает окно с уже заполненными путями. Пока это идёт, на экране висит
   форма прогресса Allegro и называет этап — окно появляется в самом конце.
3. Нажать **Generate**. Пока идёт сборка, остальное окно погашено, а кнопка
   превращается в **Cancel**.

Единица измерения дизайна должна быть **мм**.

## Окно

**Input**
- **STEP files** — папки с STEP-моделями компонентов, **по одной на строку**.
  Просматриваются сверху вниз: побеждает первая папка, где есть нужный файл.
  Поэтому проектную папку ставьте **выше** общей библиотеки, если хотите
  переопределить отдельные модели. Вложенные подпапки ищутся сами, перечислять
  их не нужно. Кнопка **Add...** дописывает папку в конец, порядок правится
  прямо в тексте.
- **JSON file** — промежуточный JSON (подставляется автоматически).
- **Output** — куда положить STEP.

**Board options**
- **Board color** — цвет платы, 8 тем из палитры Allegro (Dark_green и др.).
- **Board edge color** — цвет торца: `Same as board`, `Cream` или `Custom…`.
  Для `Custom…` рядом активируется квадратик — клик открывает выбор цвета.
- **Z = 0 at** — где начало координат по Z: верх или низ платы (список).
- **Body stitching** — как собрано тело платы. Действует только на
  мультистэкапе / rigid-flex:
  - `Solid` — одно тело одного цвета, самый лёгкий файл;
  - `Solid colored layers` — одно тело, но границы слоёв сохранены и каждая
    грань покрашена по виду слоя, торец показывает стек;
  - `Not stitched` — каждый слой отдельной деталью, чтобы разобрать глазами.
  Для двух последних ниже стоит ряд квадратиков: медь, база, покров, адгезив,
  упрочнитель, паяльная маска. Клик по квадратику — выбор цвета, кнопка
  **Reset colors** возвращает цвета материалов Allegro.
- **Do not include soldermask layers** — исключить паяльную маску из платы; стек
  смыкается к ядру на убранную толщину, и плата становится тоньше.
- **Fold flex bends** — согнуть плату по зонам сгиба из Allegro (*Setup –
  Bend*): плата, легенда и компоненты едут вместе. Включено по умолчанию; на
  плате без зон сгиба ничего не меняет. Снятая галочка — плоская плата.
  **В плоскости XY остаётся та часть платы, где лежит начало координат** —
  разместите над ним то, что должно остаться плоским, или укажите другую точку
  в `gui.foldAnchor`.
  Если в логе написано, что два сгиба претендуют на один материал, а сами зоны
  сгиба не пересекаются — поставьте `gui.foldNeutral` в `0`: Allegro
  раскладывает плоскую заготовку именно так, и на плате, где зоны сгиба
  соприкасаются (свёрнутое кольцо), это единственное значение, при котором
  сходится. Лог называет нужное число сам.

**Silk options**
- Галочки **Top**/**Bottom**, цвет **White/Black**, отдельной строкой
  **Make surface (minimum file size)** — поверхности вместо тонких тел.
  Если сняты обе стороны, вся группа гаснет.
- Внутри отдельная группа **Layers** — какие слои считать шелкографией
  (галочки; **All**/**None**). Выключённая сторона свои слои сереет.

**Compact STEP (reuse component geometry)** — уменьшить файл: одна общая
деталь на модель плюс отказ от поверхностных кривых.

## Результат

Файл `<плата>_simple_ДД_ММ_ГГГГ.step`. При совпадении имени в конец
добавляется `_`. Если рядом с `.brd` лежит `Variants.lst` — один STEP на каждый
вариант. Ищется он только там, рядом с платой; если его нет, консоль пишет, по
какому пути смотрела, и экспортирует все компоненты одним файлом.

Даже при вариантах экспорт дополнительно пишет **всю плату** — все компоненты,
кроме помеченных `NO_STEP_EXPORT`, — файлом `<плата>.json`: для чертежа, которому
нужна голая плата, а не конкретная сборка. Отключается через
`settings.exportFullBoard`; галочка **Build the full-board file too** решает,
собирать ли его, когда в очереди папка.

## Что важно знать

- **Толщина платы** = диэлектрики + плейны + проводники + обе паяльные маски.
  Шелкография и паста в толщину не входят.
- **Механические детали** (держатели, кронштейны) экспортируются, даже если у
  них нет позиционного обозначения — достаточно `PKGDEF_STEP_FILE` на символе.
- **`NO_STEP_EXPORT`** на символе / компоненте / его определении исключает
  деталь из экспорта; каждая названа в консоли.
- **Что установлено, решает список варианта**: всё, у чего есть позиционное
  обозначение, попадает в модель, только если собираемый вариант это
  перечисляет. Символ **без** обозначения (кронштейн, держатель — всё, что
  поставлено прямо в Allegro) списком описать нельзя, поэтому он есть во всех
  вариантах.
- **`ALWAYS_STEP_EXPORT`** — обратное: деталь с этим свойством остаётся во всех
  вариантах, даже если список её не перечисляет. Для площадок под пайку
  проводов: у них есть обозначение, но в BOM их нет, а на чертеже они нужны.
  Свойство заводится в плате при её открытии (и ещё раз перед каждым экспортом),
  а вешается штатно, через Edit → Properties.
- **Шелкография одинакова во всех вариантах** — текстолит производится один раз
  под все сборки.

## Если что-то не так

- Смотрите консоль Allegro (предупреждения — оранжевым, ошибки — красным) и лог
  в окне. Строка `Settings loaded from …` подтверждает, что настройки прочитаны.
- **Ваши настройки лежат в `simple3d_config.local.json`** рядом с отслеживаемым
  `simple3d_config.json`. Окно пишет только локальный файл, и его нет в git —
  поэтому обновление не может ни конфликтовать с вашими папками моделей, ни
  затереть их. Исключение — где установлен сам инструмент: для этого
  `set SIMPLE3D_DIR = …` в вашем `pcbenv\env`.
- Нужен Python 3.10 или новее и пакет `cadquery-ocp` (OpenCASCADE). Перед
  запуском GUI скрипт проверяет интерпретатор и сообщает, если чего-то нет.
- Если окно исчезло во время сборки — упал OpenCASCADE, а не Simple 3D: окно
  переживает это и показывает код выхода вместе с советом. Что обычно помогает:
  **Body stitching → Not stitched** (там ничего не сплавляется) или более
  крупный `gui.foldSliceAngle`.
- Если Allegro открылся на пустом проекте вместо вашей платы — так бывает при
  запуске с его собственной иконки — экспорт откажется работать и скажет об
  этом. Откройте сам `.brd` и запустите снова.
