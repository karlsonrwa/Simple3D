# Changelog / История изменений

Dated, user-facing changes to Simple 3D, newest first. What changed and why —
not how it was built; that record is `PROJECT_NOTES_simple3d.md`, round by
round, and it is a development memo rather than something anyone needs in order
to use the tool.

Датированный список изменений Simple 3D, новые сверху. Что изменилось и почему —
без рассказа о том, как это делалось: тот раунд-за-раундом разбор лежит в
`PROJECT_NOTES_simple3d.md` и нужен разработке, а не работе с инструментом.

---

- **2026-08-04** — **The window goes inert while it builds, and Generate
  becomes Cancel.** Every control stayed live during a build: paths, colors and
  checkboxes could be changed under a build that had already taken its snapshot
  of them, and Generate could be pressed again. Now the whole window is greyed
  out for the duration — except the log, which is what you read while you wait.
  The colour swatches and the STEP-paths field are dimmed by hand, because a
  `Canvas` and a `Text` keep their bright look however disabled they are, and
  each control's own state is remembered and put back exactly, so the ones
  the window greys out by its own rules (the rim color outside *Solid*, a side's
  silkscreen layers when that side is off) do not come back switched on.
  **Cancel** kills the build outright, which is the only thing that works
  against a boolean that has been inside OpenCASCADE for a minute; the file
  being written at that moment may be left incomplete, and the log says so. A
  cancelled build is not reported as a crash.
  / **Окно гаснет на время сборки, а Generate становится Cancel.** Во время
  сборки все элементы оставались доступными: пути, цвета и галочки можно было
  менять под уже снятым снимком настроек, а Generate — нажать ещё раз. Теперь на
  время сборки окно гаснет целиком, кроме лога, который в это время и читают.
  Квадраты цвета и поле путей к STEP гасятся вручную: `Canvas` и `Text`
  остаются яркими, в каком бы состоянии ни были. Состояние каждого элемента
  запоминается и возвращается в точности — поэтому
  то, что окно гасит по своим правилам (цвет торца вне режима *Solid*, слои
  шелкографии выключенной стороны), не включается обратно. **Cancel** убивает
  сборку немедленно: с булевой операцией, которая уже минуту внутри
  OpenCASCADE, иначе нельзя. Файл, который писался в этот момент, может
  остаться недописанным — лог об этом говорит. Отменённая сборка не выдаётся за
  падение.

- **2026-08-04** — **The whole board, beside the variants.** With a
  `Variants.lst` present the export now also writes `<design>.json`: every
  component except those marked `NO_STEP_EXPORT`, with the variant list taking
  nothing away. A drawing sometimes has to show what is on the bare board rather
  than what one assembly installs — the same need `ALWAYS_STEP_EXPORT` answers
  part by part, answered for the whole board at once. The file carries
  `"full_board": true`, so the window can name it in the queue instead of
  guessing from a filename a variant is free to collide with. Written under
  `settings.exportFullBoard`; the **Build the full-board file too** checkbox
  decides whether a queued folder builds it, while a file you point at directly
  is always built.
  / **Вся плата рядом с вариантами.** Когда есть `Variants.lst`, экспорт теперь
  пишет ещё и `<плата>.json`: все компоненты, кроме помеченных
  `NO_STEP_EXPORT`, и список вариантов из них ничего не вычитает. Чертежу иногда
  нужно показать голую плату, а не конкретную сборку — та же задача, которую
  `ALWAYS_STEP_EXPORT` решает подетально, решённая сразу для всей платы. В файле
  стоит `"full_board": true`, чтобы окно называло его в очереди, а не гадало по
  имени, с которым вариант волен совпасть. Пишется под
  `settings.exportFullBoard`; галочка **Build the full-board file too** решает,
  собирать ли его, когда в очереди папка, а файл, выбранный напрямую,
  собирается всегда.

- **2026-08-04** — **`ALWAYS_STEP_EXPORT`: a part that stays in every variant.**
  Since the variant rule was settled on the reference designator, anything
  carrying one obeys `Variants.lst` — right for a connector housing, wrong for a
  wire-solder pad, which has a refdes and no BOM line but is part of the bare
  board and belongs on every drawing. In the database the two are
  indistinguishable, so the intent is now written on the part. `NO_STEP_EXPORT`
  still outranks it. The property is **not one of Allegro's own** and does not
  exist until it is created, so `simple3d.il` defines it (as BOOLEAN) in the open
  design's dictionary — when a board is opened and again before every export,
  because a dictionary belongs to a design, not to the installation. Attaching it is then ordinary
  Edit → Properties work. Defining it is a change to the board;
  `allegro.defineAlwaysExportProp: false` switches that off and the export still
  reads the property wherever it is already defined.
  / **`ALWAYS_STEP_EXPORT`: деталь, которая остаётся во всех вариантах.** С тех
  пор как правило вариантов свелось к позиционному обозначению, всё, у чего оно
  есть, подчиняется `Variants.lst` — верно для корпуса разъёма и неверно для
  площадки под пайку провода: у неё есть обозначение и нет строки в BOM, но она
  часть голой платы и нужна на каждом чертеже. В базе эти две детали неотличимы,
  поэтому намерение теперь записывается на самой детали. `NO_STEP_EXPORT`
  по-прежнему сильнее. Свойство **не штатное** и не существует, пока его не
  заведут, поэтому `simple3d.il` создаёт его (типа BOOLEAN) в словаре открытого
  проекта — при открытии платы и ещё раз перед каждым экспортом, так как словарь
  принадлежит проекту, а не установке. Дальше оно вешается обычным Edit → Properties.
  Заведение меняет плату; `allegro.defineAlwaysExportProp: false` это отключает,
  а экспорт всё равно читает свойство там, где оно уже заведено.

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
