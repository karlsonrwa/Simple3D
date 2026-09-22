# Changelog / История изменений

Dated, user-facing changes to Simple 3D, newest first. What changed and why —
not how it was built; that record is `PROJECT_NOTES_simple3d.md`, round by
round, and it is a development memo rather than something anyone needs in order
to use the tool.

Датированный список изменений Simple 3D, новые сверху. Что изменилось и почему —
без рассказа о том, как это делалось: тот раунд-за-раундом разбор лежит в
`PROJECT_NOTES_simple3d.md` и нужен разработке, а не работе с инструментом.

---

- **2026-09-22** — **Runs on cadquery-ocp 8.0 as well as 7.9, and the tests
  are proved on copies of the tree.** Since September a bare `pip install
  cadquery-ocp` brings OpenCASCADE 8.0, and Simple 3D died at its first import
  there: 8.0 moved seven collection classes into one module under other
  names, dropped the `_s` suffix from the `TopoDS` casts, and broke
  `Bnd_Box.Get()` outright. All three are handled in one small module, and
  the geometry modules read their collections from it; the suite, the seven
  golden cases and the C++ regression give the same numbers under both
  versions, and a STEP file written by 8.0 is line for line the one 7.9
  writes except for the colour section, which 8.0 encodes in another
  structure. The install line in README pins `>=7.7,<9`. The mutation harness
  (`tools/mutate.py`) no longer writes into the working tree at all: each
  worker breaks its own copy under `build/mutants/`, the copies run in
  parallel, and the copy carries only what is under version control - the
  honest form, since a test can borrow its power from a file only the
  developer has. Measured on the 48 faults already in the table: 48 caught on
  copies too, 878 s of wall for 2382 s of suite runs on four copies beside
  other work (the in-place runner took 20-30 minutes alone). The sentinel suite
  now also checks that a copy carries every file a row names and none of what
  must stay out. And `tools/golden.py` reads each case's numbers from a file
  instead of the child's last line of output, which under 8.0 was the STEP
  writer's own "Write Done". Then the table itself was grown from 48 faults
  to **220**, one per decision the suites claim, by four agents working on
  disjoint suites: 179 mutations run, 51 survived their first run, 45 of
  those were weak tests and every one was fixed the same day in the suite
  that claims the behaviour (a component's whole placement arithmetic, the
  datum's position, thirteen SKILL procedures pinned by name only, the
  pcb → cad rule, a fold stub that could not tell the order of two
  transforms, and more), six were dropped with the measurement that shows
  them equivalent, one stays open (an arc through a wrapped bend is not
  required to stay an arc); not one showed the code wrong. Three faults were
  found in the checks themselves - a docs-audit check that could not fail, a
  GUI test that hung on a modal box for 31 minutes, a launch deadline that
  broke on a loaded machine - and fixed. The whole table, run once more on
  four copies of the final tree: 220 of 220 caught, 50 minutes of wall for
  2 h 49 min of suite runs; by the evening 230, with the eleven fold rows
  there had been no machine time for (ten caught, two of them after the
  suite learned to ask a point near a bend's seam, one dropped as
  equivalent). /
  **Работает на cadquery-ocp 8.0 так же, как на 7.9, а тесты доказываются на
  копиях дерева.** С сентября голый `pip install cadquery-ocp` приносит
  OpenCASCADE 8.0, и Simple 3D падал там на первом же импорте: 8.0 перенёс
  семь классов-коллекций в один модуль под другими именами, убрал суффикс
  `_s` у приведений `TopoDS` и сломал `Bnd_Box.Get()` целиком. Все три случая
  собраны в одном небольшом модуле, и геометрические модули берут коллекции
  из него; набор тестов, семь золотых случаев и регрессия против C++ дают под
  обеими версиями одни и те же числа, а STEP, записанный 8.0, строка в строку
  повторяет записанный 7.9, кроме секции цветов, которую 8.0 кодирует другой
  структурой. Строка установки в README закрепляет `>=7.7,<9`. Харнесс мутаций
  (`tools/mutate.py`) больше вообще не пишет в рабочее дерево: каждый рабочий
  ломает свою копию под `build/mutants/`, копии идут параллельно, и копия
  несёт только то, что под версионным контролем, — честная форма, потому что
  тест может брать силу из файла, который есть только у разработчика.
  Измерено на 48 поломках, уже бывших в таблице: все 48 ловятся и на копиях,
  878 с стены при 2382 с прогонов на четырёх копиях рядом с другой работой
  (харнесс на месте тратил 20–30 минут в одиночестве). Набор-страж теперь
  проверяет ещё и то, что копия несёт каждый файл, названный в строке, и ничего
  из того, что должно остаться снаружи. А `tools/golden.py` читает числа
  каждого случая из файла, а не из последней строки вывода ребёнка, которой
  под 8.0 оказывалось «Write Done» самого писателя STEP. Затем сама таблица
  выросла с 48 поломок до **220**, по одной на каждое решение, которое
  объявляют наборы, силами четырёх агентов на непересекающихся наборах:
  прогнано 179 мутаций, 51 пережила первый прогон, 45 из них оказались
  слабыми тестами, и каждый починен в тот же день в наборе, который
  объявляет это поведение (вся арифметика установки компонента, положение
  датума, тринадцать процедур SKILL, закреплённых лишь по имени, правило
  pcb → cad, заглушка свёртки, не различавшая порядок двух преобразований, и
  другое), шесть отброшены с замером, показывающим их эквивалентность, одна
  остаётся открытой (дуга через обёрнутый сгиб не обязана оставаться дугой);
  ни одна не показала, что код неправ. Три дефекта нашлись в самих
  проверках — проверка аудита документации, которая не могла упасть, тест
  окна, зависший на модальном диалоге на 31 минуту, дедлайн запуска,
  ломавшийся на загруженной машине, — и починены. Вся таблица, прогнанная
  ещё раз на четырёх копиях итогового дерева: 220 из 220 поймано, 50 минут
  стены при 2 ч 49 мин прогонов наборов; к вечеру — 230, с одиннадцатью
  строками по свёртке, на которые не хватило машинного времени (десять
  пойманы, две из них после того, как набор научился спрашивать точку у шва
  сгиба, одна отброшена как эквивалентная).

- **2026-09-17** — **The exposed-copper work is on `main`, after a review
  that fixed a fold and kept the proof of the tests in the tree.** Three
  things changed in the model. On a folded rigid-flex board, the bare
  laminate a drawn mask opening shows AROUND copper - a ring - used to lose
  its face in the fold: what came out was its outline as loose edges, part of
  them left flat where the folded panel used to be, 43% of that part's area
  gone on the board that showed it, and 2199 warnings that named none of it;
  a ring folds whole now, and the file carries no loose edge. A DONUT pad
  standing at an offset had its hole the whole offset away from its ring
  (the area was right, only the hole was in the wrong place); it is at the
  ring's centre. And on a plain board a mask opening drawn past the edge -
  the board outline drawn as a stroke on the mask layer, as Cadence's demo
  does it - was built half in the air; it is clipped to the outline, and one
  lying outside is left out with a word in the log. The exporter now also
  says so when Allegro's polygon engine FAILS on an opening (a failure used
  to read as "nothing under it", and the opening vanished from the file);
  the opening is written whole as laminate and the console names it. One
  question stays open and is written into *Known limitations*: a mirrored
  pin on a padstack whose drill is offset from its pad - the pad's hole and
  the board's hole follow different rules, no board here has such a padstack,
  and which one Allegro means has not been measured. The tests: every fault
  the audit of 15 September planted is now a table in the repository
  (`tests/mutations.json`, 48 faults, all caught, 21 of them new to this
  round), with the harness that applies them and a 27th suite that checks in
  a fraction of a second that every entry still aims at the code it was
  written for. The documentation was read against the code from end to end;
  fifty stale statements were corrected. `python tests/run_all.py` is
  31 of 31 in 225 s. /
  **Работа с открытой медью влита в `main` после ревью, которое починило
  свёртку и оставило в репозитории доказательство тестов.** В модели
  изменились три вещи. На сложенной гибко-жёсткой плате голый текстолит,
  который нарисованное вскрытие маски показывает ВОКРУГ меди — кольцо, —
  терял при свёртке свою грань: на выходе был его контур россыпью рёбер,
  часть их оставалась плоской там, где раньше стояла сложенная панель, 43 %
  площади этой детали пропадало на плате, где это проявилось, и 2199
  предупреждений, ни одно из которых этого не называло; теперь кольцо
  складывается целиком, и в файле нет ни одного висячего ребра. У площадки
  DONUT со смещением отверстие стояло на всё смещение в стороне от кольца
  (площадь была верной, не на месте было только отверстие); теперь оно в
  центре кольца. А на плоской плате вскрытие маски, нарисованное за край —
  контур платы штрихом на слое маски, как это делает демо-плата Cadence, —
  строилось наполовину в воздухе; теперь оно режется по контуру, а лежащее
  снаружи пропускается со словом в логе. Экспортёр теперь ещё и говорит,
  когда полигонный движок Allegro на вскрытии ОТКАЗЫВАЕТ (отказ читался как
  «под ним ничего нет», и вскрытие исчезало из файла): вскрытие пишется
  целиком как текстолит, а консоль его называет. Один вопрос остаётся
  открытым и записан в *Известные ограничения*: зеркальный вывод на
  падстеке, у которого сверло смещено относительно площадки, — отверстие в
  площадке и отверстие в плате подчиняются разным правилам, такого падстека
  здесь нет ни на одной плате, и какое из двух имеет в виду Allegro, не
  измерено. Тесты: каждая поломка, которую аудит 15 сентября вносил в код,
  теперь таблица в репозитории (`tests/mutations.json`, 48 поломок, все
  ловятся, 21 из них новые в этом раунде), вместе с харнессом, который их
  применяет, и 27-м набором, за долю секунды проверяющим, что каждая запись
  по-прежнему целит в тот код, для которого написана. Документация прочитана
  против кода от начала до конца; исправлено пятьдесят устаревших
  утверждений. `python tests/run_all.py` — 31 из 31 за 225 с.

- **2026-09-15** — **The tests were audited by breaking the code, and what
  they missed was fixed.** Nothing about the tool changed; what changed is how
  much its tests are worth. 27 deliberate faults were put into the code one at
  a time to see whether any test noticed, and 11 went through unnoticed: the
  silkscreen arc code had never run on an arc (every test polygon was a square
  with no curve in it), the check that ten identical resistors cost one solid
  instead of ten was printed and compared to nothing, the only measure of "did
  the folded board join up" had never been seen reporting a gap, and four
  faults planted in the Allegro half of the tool - among them "no layer is
  negative any more" and "the drill offset is applied backwards" - passed the
  whole suite, because what the tests check is a Python copy of those
  procedures and nothing tied the copy to the original. All of it is closed.
  The legend is now tested against six real polygons of Cadence's demo board
  and the areas Allegro itself reports for them; the shared-part check
  compares a board with two copies of a model against one with five; the seam
  measure is handed a deliberately mis-stitched fold and has to report 23.8 mm
  as 23.8 mm. The Allegro half is now both read and RUN: a new probe calls
  those procedures inside a real headless Allegro over 59 cases, and the
  Python copies are required to answer exactly as Allegro did - they do, all
  59. The suite is 26 sets, 30 of 30 pass in 235 s, and the report of the
  audit and its repair is in docs/test-audit.md. /
  **Тесты проверены поломкой кода, и то, что они пропускали, починено.** В
  самом инструменте не изменилось ничего; изменилось то, чего стоят его
  тесты. В код по одной внесли 27 намеренных поломок, чтобы посмотреть,
  заметит ли хоть один тест, — и 11 прошли незамеченными: код дуг
  шелкографии ни разу не исполнялся на дуге (все тестовые полигоны —
  квадраты без единой кривой), проверка «десять одинаковых резисторов стоят
  одного солида, а не десяти» печаталась и ни с чем не сравнивалась,
  единственная мера «сошлась ли сложенная плата» никогда не была замечена
  сообщающей о зазоре, а четыре поломки в Allegro-половине инструмента —
  среди них «негативных слоёв больше нет» и «смещение сверловки применяется
  наоборот» — прошли весь набор, потому что тесты проверяют питоновскую
  копию тех процедур, а с оригиналом её не связывало ничто. Всё это
  закрыто. Легенда теперь проверяется на шести настоящих полигонах
  демо-платы Cadence и площадях, которые сообщает про них сам Allegro;
  проверка разделяемой детали сравнивает плату с двумя копиями модели и с
  пятью; мере шва подсовывают заведомо неверно сшитый фолд, и она обязана
  сообщить про 23.8 мм именно 23.8 мм. Allegro-половина теперь не только
  читается, но и ЗАПУСКАЕТСЯ: новый зонд вызывает эти процедуры в настоящем
  headless-Allegro на 59 случаях, и питоновские копии обязаны отвечать ровно
  так же, как ответил Allegro, — отвечают, все 59. Набор вырос до 26
  комплектов, 30 из 30 проходят за 235 с, а отчёт об аудите и о починке — в
  docs/test-audit.ru.md.

- **2026-09-14** — **Exposed copper: the pour comes back.** On a board whose
  copper is opened by a shape drawn on the soldermask layer, *Exposed copper
  (as surfaces)* showed the traces and the pads and no pour - the
  polygon's area was written into the file as bare laminate instead. The
  exporter looked for the copper under each opening with Allegro's
  interactive box find, and what that returns depends on the session: run
  from the menu in a live Allegro it left the pour out, run headless it did
  not, and nothing in the log said a difference. It now sweeps the side's
  copper once, the way the legend, the openings, the pins and the vias have
  always been swept, and matches it to the openings itself. On the board
  that showed it, 60.758 mm2 moved back from bare laminate to copper. The
  console line now also says how many copper objects the sweep found, and
  warns when a board with drawn openings turns up none - so the same kind of
  fault cannot be silent again. **This lives in the Allegro side, so it
  takes effect once the exporter is updated where Allegro loads it from and
  the board is exported again; an intermediate written before that still has
  the copper missing.** /
  **Открытая медь: полигон вернулся.** На плате, медь которой вскрыта
  фигурой, нарисованной на слое паяльной маски, *Exposed copper (as
  surfaces)* показывал дорожки и площадки без полигона — его площадь попадала в
  файл как голый ламинат. Экспортёр искал медь под каждым вскрытием
  интерактивным поиском Allegro по рамке, а его результат зависит от сессии:
  из меню в живом Allegro полигон в выборку не попадал, в headless-прогоне
  попадал, и в логе об этом не было ни слова. Теперь медь стороны
  обходится один раз — так же, как всегда обходились легенда, вскрытия,
  выводы и переходные, — и сопоставляется со вскрытиями самим экспортёром. На
  плате, где это проявилось, 60.758 мм² вернулись из голого ламината в медь.
  В строке консоли теперь ещё и число найденных медных объектов, а если на
  плате есть нарисованные вскрытия и меди не нашлось вовсе — предупреждение,
  чтобы такая ошибка больше не могла пройти молча. **Правка в Allegro-части,
  поэтому она заработает после обновления экспортёра там, откуда его грузит
  Allegro, и повторного экспорта платы; в уже записанном интермедиате медь
  по-прежнему отсутствует.**

- **2026-09-14** — **The same compound in two more places, and a word when
  two bend areas cross.** The holes-with-plugs fix below was one of three
  places that handed a boolean a tool made of pieces that overlap each other.
  A layer's own shapes were the second: two shapes on one coverlay or
  stiffener layer that merely TOUCH, and one of them was silently gone -
  the opening never cut, or the patch of material never built. No board we
  have does that (the closest two shapes on one layer are 0.6 mm apart), so
  nothing changes on today's designs; it would have been a whole patch
  missing with nothing in the log. The bend strips were the third: two bends
  whose areas cross on the board left the cut a single pinched piece instead
  of four, and the repair that put it back quietly made four separate corners
  into one panel - which is what the fold moves as one rigid piece. Both are
  cut properly now. And when two bend areas really do cross, the log says so
  in mm2 instead of leaving it to the coarse "claimed twice" figure, which
  reads a small crossing as 0.04% and stays silent. Neither bend is dropped
  for it: a board can have two bends at right angles and both must fold. /
  **Тот же compound ещё в двух местах и сообщение о пересечении областей
  гиба.** Правка «отверстий с пробками» ниже была одним из трёх мест, где
  булевой операции отдавали инструмент из перекрывающихся кусков. Второе —
  собственные фигуры слоя: две фигуры на одном коверлее или стиффенере,
  просто КАСАЮЩИЕСЯ друг друга, и одна из них молча пропадала — вскрытие не
  прорезалось, либо патч материала не появлялся. На имеющихся платах такого
  нет (ближайшие две фигуры на одном слое разнесены на 0.6 мм), так что на
  сегодняшних проектах ничего не меняется; но обошлось бы это в целый
  пропавший патч без единой строки в логе. Третье — полосы гибов: два гиба,
  области которых пересекаются на плате, оставляли после реза один
  защемлённый кусок вместо четырёх, а чинящий код тихо сводил четыре
  отдельных угла в одну панель — а панель это то, что фолд двигает как одно
  жёсткое целое. Теперь режется правильно. И если области гиба
  действительно пересекаются, лог говорит об этом в мм², а не оставляет это
  грубой оценке «заявлено дважды», которая читает небольшое пересечение как
  0.04% и молчит. Ни один гиб за это не выбрасывается: на плате могут быть
  два гиба под прямым углом, и сложиться должны оба.

- **2026-09-14** — **Holes with plugs in them: cutouts that overlap each
  other are cut properly now.** On a round board broken out of its panel by
  six break-off tabs, three of the mouse-bite holes looked uncut in the model
  while the wall of the hole was plainly there. The hole *was* cut - what was
  also in the file was a loose plug sitting in it, a separate little body of
  0.1654 mm3. Every cutout prism went into one compound and that compound was
  handed to the boolean as its tool, and OCC never intersects the members of
  one argument against each other: where a tab's 1.0 mm circle overlapped the
  0.25 mm bite beside it - by 0.118 mm, which is simply what a mouse bite next
  to a tab looks like - the result was undefined. Which holes came out wrong
  was arbitrary: two tabs that are mirror images of each other across the
  board came out differently. The prisms are separate tools now; the board is
  one body, every hole is open, and the build takes the same time. The same
  change also survives the duplicated cutout that used to erase the whole
  board body. / **Отверстия с пробками: пересекающиеся катауты теперь
  прорезаются как надо.** На круглой плате, отделяемой от панели шестью
  перемычками, три отверстия мышиного укуса выглядели непрорезанными, хотя
  стенка отверстия была на месте. Отверстие прорезано - в файле рядом лежала
  ещё и пробка, отдельное тельце в 0.1654 мм3 ровно в этом отверстии. Все
  призмы катаутов складывались в один compound, и он отдавался булевой
  операции как инструмент, а OCC никогда не пересекает между собой части
  одного аргумента: там, где круг перемычки 1.0 мм накрывал соседний укус
  0.25 мм - на 0.118 мм, то есть ровно так, как укус рядом с перемычкой и
  выглядит, - результат был не определён. Какие именно отверстия выйдут
  неверными, оказывалось делом случая: две зеркальные друг другу перемычки
  повели себя по-разному. Теперь призмы идут отдельными инструментами: плата
  - одно тело, все отверстия открыты, время сборки то же. Эта же правка
  переживает и продублированный катаут, который раньше стирал тело платы
  целиком.

- **2026-09-07** — **Windows below the copper; *Copper pads* is now
  *Exposed copper*.** In step2html the demo board showed the white window of
  one through pin eating the copper ring of its neighbour: the windows and
  the copper sat at one height, a micron above the mask, and where two
  overlap a viewer draws whichever it drew last. Now there are three
  heights, a `silkscreenFlatHeight` apart - the windows lowest, the copper
  above them, the drawn openings' parts above both - so the copper is on top
  by construction. And the first checkbox draws every copper feature the
  mask exposes, not only the pads - the via rings, a pour or a label under a
  drawn opening - so it is *Exposed copper (as surfaces)* now, with
  `gui.exposedCopper` and `--exposed-copper` to match (`copperPads` and
  `--copper-pads` lived one day, on a branch). Windows only where there is
  a mask: a zone whose stackup has no soldermask on that side - a flex or
  stiffener zone under coverlay - gets no windows for its pins and no drawn
  openings, and an opening running across zones (the demo's outline is
  drawn as strokes on the mask layers through every zone) is clipped to
  the masked zones, each piece at its own zone's face, instead of floating
  above the flex. / **Окна под медью;
  *Copper pads* теперь *Exposed copper*.** В step2html на демо-плате белое
  окно одного вывода «съедало» медное кольцо соседнего: окна и медь лежали
  на одной высоте, на микрон над маской, а там, где две грани совпадают,
  просмотрщик показывает ту, что нарисовал последней. Теперь высот три, через
  `silkscreenFlatHeight`: окна ниже всех, медь над ними, детали нарисованных
  вскрытий выше обоих — медь сверху по построению. А первая галочка рисует
  всю медь, которую открывает маска, а не только площадки — кольца отверстий,
  заливку или надпись под нарисованным вскрытием, — поэтому теперь она
  *Exposed copper (as surfaces)*, с `gui.exposedCopper` и `--exposed-copper`
  (`copperPads` и `--copper-pads` прожили один день, в ветке). Окна только
  там, где маска есть: зона, чей стек не несёт паяльной маски с этой стороны
  — флекс или стиффенер под коверлеем, — не получает ни окон для своих
  выводов, ни нарисованных вскрытий, а вскрытие, пересекающее зоны (контур
  демо-платы нарисован штрихами на слоях маски сквозь все зоны), обрезается
  по зонам с маской, каждый кусок на грани своей зоны, вместо того чтобы
  висеть над флексом.

- **2026-09-07** — **Mask openings, as surfaces; copper drawn with no net.**
  A second checkbox, *Mask openings (as surfaces)*, draws the windows in the
  solder mask in the dielectric's colour: every pin's and via's opening from
  its padstack, instanced like the pads, and every opening drawn on the mask
  layers - a line, a shape or rectangle, a text - flat like the legend. With
  *Exposed copper* on, what the copper leaves of each opening: the ring around
  a copper-defined pad, the laminate a label cut into the mask shows (which
  the copper pads drew on their own for a few hours and now leave to this
  checkbox); alone, the openings whole. And a label written in copper with
  *Add Line* on an etch layer - on no net, a "line" to Allegro's find filter
  rather than a "cline" - is copper under its opening now: the sweep asks
  for both, where it asked for clines alone and found none of the 51 strokes
  of the user's label. / **Вскрытия маски поверхностями; медь без цепи.**
  Вторая галочка, *Mask openings (as surfaces)*, рисует окна в паяльной
  маске цветом диэлектрика: вскрытие каждого вывода и переходного отверстия
  из его падстека, вхождениями как площадки, и каждое вскрытие,
  нарисованное на слоях маски — линия, фигура или прямоугольник, текст, —
  плоско, как легенда. Вместе с *Exposed copper* — то, что от вскрытия
  оставляет медь: кольцо вокруг copper-defined площадки, текстолит, который
  показывает прорезанная в маске надпись (несколько часов его рисовали сами
  площадки, теперь он у этой галочки); сами по себе — вскрытия целиком. И
  надпись, нарисованная медью через *Add Line* на слое etch — без цепи, для
  фильтра поиска Allegro «line», а не «cline», — теперь медь под своим
  вскрытием: развёртка спрашивает и то и другое, а спрашивая одни clines, не
  находила ни одного из 51 штриха надписи пользователя.

- **2026-09-07** — **Copper pads, as surfaces.** A new checkbox, *Exposed
  copper (as surfaces)* (named *Copper pads* for a few hours), draws the
  copper of every pin's pad on the two outer faces
  in the copper colour, a micron above the mask - so the model reads as a
  board with its pads rather than as a plain slab. Nothing is cut into the
  board and no boolean runs: each pad figure is built once from the outline
  Allegro itself holds for it (every figure kind carries one - circle,
  oblong, rounded rectangle, *Shape*) and instanced per pin, the way
  component models are shared, so a pad costs a placement in the file and
  not a body. Through-hole pads keep their drill; a mounting hole whose pad
  is smaller than its drill draws nothing. Which face a pin reaches is its
  own layer span against the outer copper of its zone, so the flex connector
  on Cadence's demo board lands on the flex's top face and a part on an
  inner layer of a rigid zone is counted, not drawn. Every placed pad on
  five boards - 54 000 placements, offset, mirrored and turned padstacks
  included - agrees with the polygon Allegro reports for that pin. A pad's
  corner arc is built through its two end points, because Allegro keeps an
  arc's centre only to the design's resolution and an arc rebuilt on its
  radius can miss the next line by a fraction of a micron - which is how
  four rounded-rectangle padstacks first came out as nothing. Measured on
  the demo: 2982 pads add 2.3 MB to a 94 MB file and five seconds to a
  three-minute build. Only what the mask exposes is drawn: the padstack's
  own mask opening travels beside the copper, and a solder-mask-defined
  pad shows the opening's shape, a copper-defined one its copper, a pad
  with no opening nothing (Dell: 621 mask-defined and 101 covered of
  12 146 pins). Vias are rows like pins, so an untented via shows its ring
  and a tented one draws nothing (the demo tents none: 2484 rings). An
  opening drawn in the footprint or on the board - a line, a shape or a
  text on a SOLDERMASK layer, the `soldermask` section of the config says which -
  exposes the copper under it: computed in Allegro with `axlPolyOperation`
  and built like a flat legend, one part per side (`copper_top_<board>`),
  a micron above the pads - and the bare laminate it shows where there is
  no copper (a label cut into the mask as strokes) comes the same way, in
  the dielectric's colour (`bare_top_<board>`), so the label is in the
  model. The exporter now writes `format_version` 12
  with a `pads` object (`settings.exportPads`, on by default); an 11 file
  has no vias and nothing under drawn openings, a 10 file draws the copper
  whole and an older one none - the log says which. Off by default.
  / **Медь площадок, поверхностями.** Новая галочка *Exposed copper (as
  surfaces)* (несколько часов звалась *Copper pads*) рисует медь площадок
  всех выводов на двух наружных гранях
  цветом меди, на микрон над маской, — чтобы модель читалась как плата с
  площадками, а не как гладкая пластина. В плату ничего не вырезается,
  булевых операций нет: фигура площадки строится один раз по контуру,
  который сам Allegro хранит для неё (он есть у каждого вида фигуры — круг,
  овал, скруглённый прямоугольник, *Shape*), и ставится вхождением на
  каждый вывод, как общие модели компонентов, так что площадка стоит в
  файле как размещение, а не как тело. Сквозные площадки сохраняют
  отверстие; крепёжное отверстие с площадкой меньше сверла не рисует ничего.
  Какой грани достигает вывод, решает его собственный диапазон слоёв против
  наружной меди его зоны: разъём на флексе демо-платы Cadence ложится на
  верхнюю грань флекса, а деталь на внутреннем слое жёсткой зоны считается,
  но не рисуется. Каждая поставленная площадка на пяти платах — 54 000
  размещений, включая смещённые, зеркальные и повёрнутые падстеки —
  совпадает с полигоном, который Allegro сообщает для этого вывода. Дуга
  угла площадки строится через свои две концевые точки: центр дуги Allegro
  хранит лишь с разрешением проекта, и дуга, восстановленная по радиусу,
  может не дойти до соседнего отрезка на доли микрона — так четыре
  падстека со скруглёнными прямоугольниками сначала не нарисовались вовсе.
  Замер на демо: 2982 площадки добавляют 2.3 МБ к файлу в 94 МБ и пять
  секунд к трёхминутной сборке. Рисуется только то, что открыто маской:
  вскрытие из самого падстека едет рядом с медью, и mask-defined площадка
  показывает форму вскрытия, copper-defined — свою медь, площадка без
  вскрытия — ничего (Dell: 621 mask-defined и 101 закрытая из 12146).
  Переходные отверстия — такие же строки, как выводы: незакрытое показывает
  кольцо, закрытое не рисуется (демо не закрывает ни одного: 2484 кольца).
  Вскрытие, нарисованное в посадочном месте или на плате — линия, фигура
  или текст на слое SOLDERMASK, секция `soldermask` конфига говорит, на
  каких, —
  открывает медь под собой: считается в Allegro через `axlPolyOperation` и
  строится как плоская легенда, одна деталь на сторону
  (`copper_top_<плата>`), на микрон выше площадок, — а голый текстолит,
  который оно показывает там, где меди нет (надпись, прорезанная в маске
  штрихами), едет так же, цветом диэлектрика (`bare_top_<плата>`), и
  надпись есть в модели. Экспорт теперь пишет
  `format_version` 12 с объектом `pads` (`settings.exportPads`, по
  умолчанию включено); файл 11 не несёт отверстий и меди под нарисованными
  вскрытиями, файл 10 рисует медь целиком, более старый — ничего, лог
  говорит, что именно. По умолчанию выключено.

- **2026-09-06** — **A flex layer no longer loses a corner where its zone
  contour carries a hairline.** On flex2-a0 the FLEX zone's outline, as
  Allegro writes it, runs out along the round stiffener's arc and back on a
  circle 0.2 µm off it - a spike of zero width. Since 14 August every layer
  is cut down to the panel it belongs to with a prism of that panel's exact
  face, and where the spike lay on the prism's own cylinder the boolean
  threw the whole corner of the panel beyond BEND_6 away: a 0.12 mm²
  triangle on five of the seven flex layers, visible as a notch at the edge
  of the flex. The cutter is now the panel's face grown ten microns along
  the board outline and exact at the bend seams, so it never shares a wall
  with a layer. Measured: every layer of that board folds to the volume it
  had before 14 August, to 1e-5 mm³; the golden corpus and every other
  board are unchanged. The exporter was not involved - the fresh
  intermediate is identical to the one from before the refactoring.
  / **Слой гибкой части больше не теряет угол там, где контур его зоны
  несёт «волосок».** На flex2-a0 контур зоны FLEX, как его пишет Allegro,
  уходит вдоль дуги круглого стиффенера и возвращается по окружности,
  смещённой на 0.2 мкм, - шип нулевой ширины. С 14 августа каждый слой
  вырезается под свою панель призмой точной грани этой панели, и там, где
  шип лежал на цилиндре самой призмы, булева операция выбрасывала весь
  угол панели за BEND_6: треугольник 0.12 мм² на пяти слоях из семи,
  заметный как выемка на краю шлейфа. Теперь резак - грань панели,
  раздутая на десять микрон вдоль контура платы и точная по швам сгибов,
  так что он нигде не делит стенку со слоем. Измерено: каждый слой этой
  платы складывается в тот же объём, что до 14 августа, с точностью
  1e-5 мм³; golden-корпус и остальные платы не изменились. Экспортёр ни
  при чём: свежий промежуточный файл совпадает с тем, что был до
  рефакторинга.

- **2026-09-03** — **Ctrl+C / Ctrl+V work in the window's fields on a Russian
  keyboard layout.** Tk binds the shortcuts to the Latin letters, so under
  any non-Latin layout the same keys did nothing in every path field and
  the STEP-folders box. The fields now go by the physical key: Ctrl+C,
  Ctrl+V, Ctrl+X and Ctrl+A act whatever the layout, once each.
  / **Ctrl+C / Ctrl+V в полях окна работают в русской раскладке.** Tk
  привязывает сочетания к латинским буквам, поэтому в любой нелатинской
  раскладке те же клавиши ничего не делали ни в полях путей, ни в списке
  папок STEP. Теперь поля смотрят на физическую клавишу: Ctrl+C, Ctrl+V,
  Ctrl+X и Ctrl+A срабатывают в любой раскладке, по одному разу.

- **2026-09-03** — **A variant naming components the board does not have says so.**
  A `Variants.lst` comes from the schematic and the board from Allegro; when
  a variant lists a reference designator that no symbol on the board carries,
  the two describe different revisions - and the export used to say nothing,
  because `variant list covers 1 of 48` counts from the board's side only.
  Now each variant reports the ones it lists and the board lacks, by name, in
  the Allegro console, and the line travels in the intermediate (an optional
  `"warnings"` list) so the 3D window's log repeats it when the model is
  built. A file whose listed components are *all* absent is still refused as
  another project's.
  / **Вариант, называющий компоненты, которых нет на плате, теперь говорит
  об этом.** `Variants.lst` приходит из схемы, плата - из Allegro; если в
  варианте есть обозначение, которого нет ни у одного символа на плате, это
  разные ревизии - а экспорт молчал: строка `variant list covers 1 of 48`
  считает только со стороны платы. Теперь каждый вариант называет те свои
  обозначения, которых на плате нет, в консоли Allegro, и та же строка едет
  в промежуточном файле (необязательный список `"warnings"`), чтобы окно
  повторило её в своём логе при сборке. Файл, где отсутствуют *все*
  перечисленные компоненты, по-прежнему отвергается как чужой.

- **2026-09-03** — **A variant that installs nothing exports the bare board.**
  Setting every part to *not installed* in the schematic's variant gives a
  `Variants.lst` whose variant has no base list at all. The export used to
  wait for one, register no variant, and refuse the file as another
  project's - with the progress form left standing at 20 %. Now that
  variant is written as the bare board (the outline, the silkscreen and the
  symbols that have no reference designator), with a warning in the console
  saying so - a stub `"dummy"` file produces the same shape, and the file
  cannot tell the two apart. A file naming another project's components is
  still refused. Two more things from the same report: the menu command
  takes the progress form down when the export fails, and says so; and
  `Variants.lst` is closed after reading - it used to stay open until
  Allegro exited, so it could not be deleted or replaced during the session.
  / **Вариант, в котором ничего не установлено, экспортирует голую плату.**
  Если в варианте схемы все детали помечены *not installed*, в `Variants.lst`
  у варианта нет базового списка вовсе. Экспорт ждал его, вариант не
  регистрировал и отвергал файл как чужой - а индикатор прогресса оставался
  на 20 %. Теперь такой вариант пишется как голая плата (контур, шелкография
  и символы без позиционного обозначения) с предупреждением в консоли:
  заглушка `"dummy"` даёт файл той же формы, и различить их по файлу нельзя.
  Файл с обозначениями другого проекта по-прежнему отвергается. Ещё два
  исправления из того же сообщения: при ошибке экспорта команда меню убирает
  индикатор и говорит об этом; `Variants.lst` закрывается после чтения -
  раньше он оставался открытым до выхода из Allegro, и удалить или заменить
  его во время сеанса было нельзя.

- **2026-09-03** — **The window opens sooner.** It used to load OpenCASCADE
  before drawing anything, for three default numbers that live in a small
  file of their own now; the geometry kernel is loaded by the build's child
  process only. Importing the window went from 1.53 s to 0.25 s on the
  development machine. Nothing else changes.
  / **Окно открывается быстрее.** Раньше оно загружало OpenCASCADE до
  того, как что-то нарисовать, ради трёх чисел по умолчанию, которые теперь
  лежат в своём маленьком файле; геометрическое ядро загружает только
  дочерний процесс сборки. Импорт окна на машине разработки: было 1.53 с,
  стало 0.25 с. Больше ничего не меняется.

- **2026-09-03** — **`format_version` 9: the components under one key.** The
  intermediate now keeps every component under `"components"` instead of
  beside the board's metadata, so a reader no longer needs a list of which
  keys are *not* components. Every older file still builds. The one thing
  to know: a file written by this release needs this release's Python - an
  older `stepbuilder` would read one component named `components`. Also
  with 9, `pcb.thickness` is written only when one stackup is the board;
  otherwise the build measures it from the stackups and says so, and when
  a file's number disagrees with its stackup the stackup wins, with a
  warning naming both.
  / **`format_version` 9: компоненты под одним ключом.** Промежуточный файл
  теперь держит все компоненты под ключом `"components"`, а не рядом с
  метаданными платы, так что читателю больше не нужен список ключей,
  которые *не* компоненты. Все старые файлы по-прежнему собираются. Одно
  надо знать: файлу этого релиза нужен Python этого релиза — старый
  `stepbuilder` прочитал бы один компонент по имени `components`. Ещё в
  9: `pcb.thickness` пишется только когда какой-то стек и есть плата;
  иначе сборка измеряет толщину по стекам и говорит об этом, а если число
  в файле расходится со стеком, побеждает стек — с предупреждением,
  называющим оба числа.

- **2026-09-03** — **Cyrillic in a name no longer crashes the build; a right-click
  menu; a plain warning about non-ASCII paths.** Allegro writes text in the
  Windows code page, so a board, a model file or a layer named in Cyrillic
  produced an intermediate the reader crashed on; it reads such a file now
  (UTF-8 first, the code page second) and says so in the log. Every path
  field and the STEP-folders box have a right-click menu: Cut, Copy, Paste,
  Select all. A path with characters outside ASCII is named at the top of
  the build log: the build itself reads and writes such paths (measured),
  but Allegro's own half may not - it opens a board from a Cyrillic folder
  since 25.1, and a board whose *file name* is Cyrillic still comes up
  empty. Measured as well, against the question whether the rebuild made
  the STEP slower: it did not - the same three boards build in the same
  time as at round 69, within the noise of a run, with identical STEP
  output.
  / **Кириллица в имени больше не роняет сборку; контекстное меню;
  честное предупреждение о не-ASCII путях.** Allegro пишет текст в
  кодировке Windows, и плата, файл модели или слой с кириллическим именем
  давали промежуточный файл, на котором читатель падал; теперь он читает
  такой файл (сначала UTF-8, потом кодовая страница) и говорит об этом в
  журнале. У каждого поля пути и у списка папок STEP есть меню по правой
  кнопке: Cut, Copy, Paste, Select all. Путь с символами вне ASCII
  называется в начале журнала сборки: сама сборка такие пути читает и
  пишет (измерено), а половина Allegro — не всегда: с 25.1 плата из
  папки с кириллицей открывается, но плата, у которой кириллическое *имя
  файла*, открывается пустой. Измерено и другое — не стала ли сборка STEP
  медленнее после переделки: нет, те же три платы собираются за то же
  время, что и в раунде 69, в пределах разброса прогона, при идентичном
  STEP.

- **2026-09-03** — **One `load()` line, and the exporter in nine files.**
  `simple3d.il` now loads the exporter itself, so `allegro.ilinit` needs one
  line - `load("…/simple3d.il")` - instead of two; the old pair keeps
  working. The exporter, `makeVariant3dIntermediates.il`, became a loader
  for nine parts under a new `skill\` folder (util, json, props, variants,
  geometry, stackup, bends, silk, export), each one subject; **an install
  copies that folder too.** Nothing the exporter writes has changed: every
  board in the test corpus exports byte-identically through the new files.
  / **Одна строка `load()`, и экспортёр в девяти файлах.** `simple3d.il`
  теперь сам загружает экспортёр, так что в `allegro.ilinit` достаточно
  одной строки — `load("…/simple3d.il")` — вместо двух; прежняя пара
  продолжает работать. Экспортёр `makeVariant3dIntermediates.il` стал
  загрузчиком девяти частей в новой папке `skill\` (util, json, props,
  variants, geometry, stackup, bends, silk, export), по одной теме в каждой;
  **при установке копируйте и эту папку.** Ничего из того, что пишет
  экспортёр, не изменилось: каждая плата из тестового корпуса
  экспортируется через новые файлы байт в байт.

- **2026-09-02** — **A quote in a name no longer breaks the export.** A
  reference designator, a STEP model name, a zone or layer name, or the
  variant name with a `"` or `\` in it used to produce an intermediate
  the Python side refused whole; an embedded-model name like that was
  left out of the file with a warning. Every string the exporter writes
  is escaped now, and a test refuses any new place that would write one
  raw. Under the hood the exporter also declares every name it assigns
  (Allegro's SKILL is dynamically scoped, so an undeclared one leaked
  into the session), has one copy of its layer-sweep instead of five,
  and is checked headless - `tools/skill_export.py` runs it on every
  board in `input/` and compares the JSON, so a change like this is
  proven to change nothing on a board without such names.
  / **Кавычка в имени больше не ломает экспорт.** Позиционное
  обозначение, имя STEP-модели, зоны или слоя, имя варианта с `"` или
  `\` давали промежуточный файл, который Python-половина отвергала
  целиком; имя встроенной модели с такими символами вообще
  выбрасывалось из файла с предупреждением. Теперь каждая строка,
  которую пишет экспортер, экранируется, а тест не пропустит новое место,
  где строка пишется как есть. Внутри экспортер к тому же объявляет
  каждое имя, которое присваивает (SKILL в Allegro — с динамической
  областью видимости, необъявленное имя утекало в сеанс), держит одну
  копию развёртки по слоям вместо пяти и проверяется без окна:
  `tools/skill_export.py` прогоняет его по каждой плате в `input/` и
  сравнивает JSON, так что такое изменение доказанно ничего не меняет на
  плате без подобных имён.

- **2026-09-02** — **The launcher's command line is checked, not skimmed.**
  `python -m stepbuilder --gui ...` (what the Allegro button runs) used to
  have a parser of its own that dropped any flag it did not know without a
  word; now one parser serves the window and the headless build, so a
  misspelt flag is an error with a message, and `--help` shows the
  window-only flags (`--config`, `--json-dir`, `--json-file`,
  `--output-dir`) alongside the rest. Inside the window three pieces
  became modules of their own - where the window opens, the silkscreen
  layer list, and the child process that builds - each closed by the
  same tests it had before plus a 21st suite for the launcher line.
  Nothing the tool writes has changed.
  / **Командная строка запуска проверяется, а не просматривается.**
  У `python -m stepbuilder --gui ...` (то, что запускает кнопка в Allegro)
  был свой разборщик, молча отбрасывавший незнакомый флаг; теперь окно и
  консольная сборка разбирают командную строку одним разборщиком, так что
  опечатка во флаге — ошибка с сообщением, а `--help` показывает флаги
  только для окна (`--config`, `--json-dir`, `--json-file`,
  `--output-dir`) рядом с остальными. Внутри окна три куска стали
  отдельными модулями — где открывается окно, список слоёв шелкографии и
  дочерний процесс сборки; каждый закрыт теми же тестами, что и раньше,
  плюс 21-й набор для строки запуска. Содержимое файлов не изменилось.

- **2026-09-02** — **`--no-full-board`, and a mode that is not a mode is an
  error.** The headless `--batch` can now leave the whole-board file out, the
  way the window's *Build the full-board file too* checkbox always could -
  one rule for both. A `board_mode` that is not `solid`, `layers` or
  `inspect` is refused with a message; it used to build a plain solid
  without a word. Under the hood `core.py` finished coming apart: the board,
  the legend, the models, the assembly document and the build's options are
  modules of their own and `generate` is the sequence that calls them -
  every step closed by the full suite and the golden corpus, so nothing a
  STEP file contains has changed.
  / **`--no-full-board`, и режим, которого нет, — ошибка.** Консольный
  `--batch` теперь умеет не собирать файл всей платы — так, как галочка
  *Build the full-board file too* в окне умела всегда; правило одно на
  обоих. `board_mode`, отличный от `solid`, `layers` и `inspect`, отвергается
  с сообщением; раньше он молча собирал обычное тело. Внутри `core.py`
  разобран до конца: плата, шелкография, модели, документ сборки и
  параметры сборки — отдельные модули, а `generate` — последовательность их
  вызовов; каждый шаг закрыт полным набором тестов и золотым корпусом, так
  что содержимое STEP-файлов не изменилось.

- **2026-09-02** — **The Python half is in pieces, deliberately.** The two
  large files behind the window — `core.py` and `bend.py` — have started to
  come apart along the lines `REFACTORING_PLANS.md` drew: the contour
  primitives, the one exception, the intermediate read once per file, the
  settings pair and the window's key table are modules of their own, and
  `bend/` is a package of nine. Every step was a verbatim move closed by the
  full suite and by the golden corpus, so nothing the tool writes has changed.
  Two things did: the window now parses each intermediate once instead of
  three or four times, and a fourth mechanical check (`tools/python_names.py`,
  pyflakes) catches a moved function that left a name behind — it caught two.
  / **Половина на Python разобрана на части, намеренно.** Два больших файла
  за окном — `core.py` и `bend.py` — начали расходиться по линиям, которые
  провёл `REFACTORING_PLANS.md`: примитивы контура, единственное исключение,
  промежуточный файл, читаемый один раз, пара настроек и таблица ключей окна
  стали отдельными модулями, а `bend/` — пакетом из девяти. Каждый шаг —
  дословный перенос, закрытый полным набором тестов и золотым корпусом, так
  что то, что инструмент пишет, не изменилось. Изменились две вещи: окно
  разбирает каждый промежуточный файл один раз вместо трёх-четырёх, и
  четвёртая механическая проверка (`tools/python_names.py`, pyflakes) ловит
  перенесённую функцию, оставившую имя позади — она поймала две.

- **2026-09-02** — **The test net can fail now.** The one test that compares
  the port against the original C++ exporter had printed MATCH or DRIFT and
  exited 0 either way since the day it was written; it now fails on a volume
  drift or on a change in the STEP entity count (5038, with the history of
  when and why it moved). Every test script shares one `tests/_support.py`
  instead of carrying its own copy of the paths and the `check()` helper, and
  `tools/golden.py` builds the repository's own boards and compares the result
  after every refactoring step. This is the first step of
  `REFACTORING_PLANS.md`; nothing the tool writes has changed.
  / **Сеть тестов теперь умеет падать.** Единственный тест, сравнивающий порт с
  исходным экспортёром на C++, со дня написания печатал MATCH или DRIFT и
  всегда выходил с кодом 0; теперь он падает при уходе объёма или при смене
  числа сущностей STEP (5038, с историей того, когда и почему оно менялось).
  Все тестовые скрипты используют общий `tests/_support.py` вместо своих копий
  путей и `check()`, а `tools/golden.py` собирает платы из самого репозитория и
  сравнивает результат после каждого шага рефакторинга. Это первый шаг
  `REFACTORING_PLANS.md`; то, что инструмент пишет, не изменилось.

- **2026-09-02** — **A structural review, written down.** Two new documents for
  whoever works *on* the tool rather than with it: `ARCHITECTURE.md` — what each
  file holds, how the two halves talk through the intermediate, the pipeline
  stage by stage, and which pieces are monoliths and which could be reused
  elsewhere — and `REFACTORING_PLANS.md`, the order in which to take the five
  monoliths apart without changing a single STEP file, each step pinned by the
  tests that already exist. Nothing in the tool's behaviour changed. Two small
  things did: the README no longer claims that nothing temporary is written
  beside the board — the Python pre-flight writes `_simple3d_preflight.txt` into
  the output folder and deletes it again; and `input/` joined `failed/` in
  `.gitignore`, so a board put there to be looked at cannot reach the public
  repository by accident.
  / **Структурное ревью, записанное.** Два новых документа для тех, кто работает
  *над* инструментом, а не с ним: `ARCHITECTURE.md` — что лежит в каждом файле,
  как две половины общаются через промежуточный JSON, конвейер по стадиям и
  какие куски являются монолитом, а какие можно переиспользовать, — и
  `REFACTORING_PLANS.md`: в каком порядке разбирать пять монолитов, не меняя ни
  одного STEP-файла, где каждый шаг закреплён уже существующими тестами.
  Поведение инструмента не изменилось. Две мелочи изменились: README больше не
  утверждает, что рядом с платой ничего временного не пишется — предполётная
  проверка Python пишет `_simple3d_preflight.txt` в выходную папку и тут же
  удаляет; а `input/` добавлен в `.gitignore` вслед за `failed/`, чтобы
  положенная туда плата не могла случайно попасть в публичный репозиторий.

- **2026-08-21** — **A drilled hole is cut where the drill is, not where the pad
  is.** A padstack can carry an offset from its origin to the hole — Allegro's
  Padstack Editor, *Drill Offset* tab, *Offset from padstack origin to hole* —
  and an edge connector is what it is for: the pads sit on the board while the
  holes straddle the edge as half-holes. Slots had honoured that offset all
  along; ordinary round holes did not, so they were cut at the pad centre. On
  `bone-a2` the four PLS-4 holes have an offset of 0.375 mm towards the board
  edge: Allegro's own 3D showed clean half-circles in the edge, and our STEP put
  the same circles 0.375 mm inboard, where each becomes a keyhole with a 0.66 mm
  mouth instead of a 1.00 mm one. Both hole kinds now go through one procedure,
  so they cannot disagree again. Boards whose padstacks have no drill offset —
  most boards — are unchanged.
  / **Отверстие сверлится там, где сверло, а не там, где площадка.** У падстека
  может быть задано смещение от начала координат до отверстия — Allegro,
  Padstack Editor, вкладка *Drill Offset*, *Offset from padstack origin to
  hole*, — и краевой разъём ровно для этого: площадки лежат на плате, а
  отверстия садятся на её край полуотверстиями. Пазы это смещение учитывали
  всегда, обычные круглые отверстия — нет, и сверлились по центру площадки. На
  `bone-a2` у четырёх отверстий PLS-4 смещение 0.375 мм к краю платы: штатная
  трёхмерка Allegro показывала аккуратные полукруги в кромке, а наш STEP ставил
  те же окружности на 0.375 мм внутрь, где каждая превращается в замочную
  скважину с устьем 0.66 мм вместо 1.00 мм. Теперь оба вида отверстий проходят
  через одну процедуру и разойтись больше не могут. Платы, у которых смещения
  сверловки нет — а это большинство, — не меняются.

- **2026-08-21** — **Export does not fail silently when a second Python appears
  on PATH.** Installing node.js brings a Python of its own along, into the
  machine PATH — which comes before your per-user one — so `python` and
  `pythonw` began meaning a fresh 3.14 with no `cadquery-ocp` in it. Nothing had
  been uninstalled; a different interpreter was answering to the same name. The
  pre-flight check that exists to catch exactly this **passed anyway**: it looked
  for the text `S3D_OK` in the interpreter's output, and Python 3.13 and newer
  echo the source line of a `-c` command in the traceback — so the check's own
  success marker appeared in its own failure output. The GUI was then started
  under `pythonw`, which has no console, and died where nothing could report it.
  The marker is now built so a traceback cannot spell it, the check prints
  **which interpreter answered** (path and version) so a shadowed Python is
  visible at a glance, a failed check also raises a dialog rather than only a
  console line, and the advice names the setting that pins an interpreter —
  `allegro.python` / `allegro.pythonw` in `simple3d_config.local.json` — instead
  of a line in `simple3d.il` that has not existed since 2026-08-05.
  / **Экспорт больше не проваливается молча, когда в PATH появляется второй
  Python.** Установка node.js приносит с собой свой Python — в системный PATH,
  который идёт раньше пользовательского, — и `python` с `pythonw` стали означать
  свежий 3.14, где нет `cadquery-ocp`. Ничего не удалялось: на то же имя стал
  отзываться другой интерпретатор. Предполётная проверка, которая существует
  ровно для этого случая, **всё равно прошла**: она искала в выводе строку
  `S3D_OK`, а Python 3.13 и новее печатают в трассировке исходную строку команды
  `-c` — и собственный признак успеха оказался в собственном тексте ошибки. GUI
  после этого запускался под `pythonw`, у которого нет консоли, и умирал там, где
  сообщить об этом некому. Теперь признак устроен так, что трассировка не может
  его написать; проверка печатает, **какой интерпретатор ответил** (путь и
  версию), так что подменённый Python виден сразу; при отказе поднимается ещё и
  диалог, а не только строка в консоли; а совет называет настройку, которой
  интерпретатор закрепляется, — `allegro.python` / `allegro.pythonw` в
  `simple3d_config.local.json`, — вместо строки в `simple3d.il`, которой нет с
  2026-08-05.

- **2026-08-15** — **A folded panel is no longer painted with the board edge
  colour.** On a board with *Board edge color* set to something of its own, a
  panel that a bend turns over could come back entirely in that colour — on
  Cadence's demo board the whole 2398 mm² LCD stiffener panel did. The rim is
  found by asking whether a face stands vertical **in the frame it was built
  in**, since after a fold half a board's flat faces stand vertical; that frame
  was being looked up by trying each region's inverse, and a wrong one does not
  fail, it answers — it threw the panel's face out to z = 31 on a board 1.6 mm
  thick, where it duly looked vertical. An unfolded face now has to land back
  inside the board, and flat panels are tried before the facets of a bend. On
  that board the rim goes from 4359 mm² to 2022, which is side walls and the
  panel's own edges — a rim. Only *Solid* mode with a rim colour was affected.
  / **Сложенная панель больше не красится цветом торца платы.** На плате, где
  *Board edge color* задан отдельно, панель, перевёрнутая сгибом, могла целиком
  прийти в этом цвете — на демо-плате Cadence так вышло со всей LCD-панелью
  стиффенера, 2398 мм². Торец определяется вопросом, стоит ли грань вертикально
  **в том кадре, где она была построена**, — после свёртки половина плоских
  граней платы стоит вертикально; кадр искался перебором обратных трансформаций
  областей, а неверная не отказывает, а отвечает — она выбрасывала грань панели
  на z = 31 при толщине платы 1.6 мм, где та закономерно выглядела вертикальной.
  Теперь развёрнутая грань обязана вернуться внутрь платы, а плоские панели
  проверяются раньше долек сгиба. На той плате торец ужался с 4359 мм² до 2022 —
  это боковые стенки и собственные кромки панели, то есть торец. Затронут был
  только режим *Solid* с заданным цветом торца.

- **2026-08-14** — **A rounded board edge stays round through a bend, and the log
  now says how much *K factor* your board can take.** Two things you could see in
  the model. A rounded arm end came out of the fold visibly faceted — not the
  bend, whose surfaces are true cylinders, but the *edge*: the flat board was
  being cut with the outline sampled into eight chords per arc, which is 67 µm of
  flat on a 14 mm corner. It is cut with the outline's own arcs now, and a
  rounded end stays round. And when two bend areas that Allegro draws clear of
  each other do reach each other once widened to the neutral axis, the log says
  so **in blue** and names the largest `foldNeutral` that particular board takes
  cleanly — so the choice is a number rather than a guess. Blue is new: `note:`
  lines are advice, not trouble, and no longer look like warnings.
  / **Скруглённый край платы остаётся круглым на сгибе, а лог теперь говорит,
  какой *K-фактор* держит ваша плата.** Две вещи, заметные прямо в модели.
  Скруглённый конец плеча выходил из свёртки заметно гранёным — дело не в сгибе,
  его поверхности истинные цилиндры, а в **кромке**: плоская плата резалась по
  контуру, развёрнутому в восемь хорд на дугу, то есть 67 мкм плоского на
  скруглении радиусом 14 мм. Теперь режется по собственным дугам контура, и
  скругление остаётся скруглением. А когда две области сгиба, нарисованные в
  Allegro с зазором, всё же сходятся после расширения до нейтральной оси, лог
  сообщает об этом **синим** и называет наибольшее `foldNeutral`, которое эта
  плата держит чисто, — выбор становится числом, а не догадкой. Синий цвет
  новый: строки `note:` — это совет, а не беда, и больше не выглядят как
  предупреждение.

- **2026-08-14** — **The printed legend stops at zones that are not printed on**
  (`format_version: 8`). A cross section assigns its mask and coating layers per
  stackup, so a rigid-flex board says *"no silkscreen on the stiffener zones"*
  exactly by leaving the silkscreen layer out of those stackups. The exporter
  dropped that layer — correctly, it is not part of the body — and with it the
  statement, so the legend was printed over every zone alike. Each stackup now
  carries a `silkscreen` object saying which of its sides is printed, and the
  builder leaves out the glyphs that fall on a zone that is not. On Cadence's
  demo board that is 14 polygons on the top (over `CONN_FLEXI_STIFFENER` and
  `FLEXI_STIFFENER`) and 16 on the bottom (over `LCD_FLEXI_STIFFENER`), each
  named in the log with its zone. **An intermediate written before this says
  nothing about it and is not clipped at all**, so nothing you already have
  changes behaviour — but a board has to be exported again for the legend to be
  trimmed. Also fixed in this pass: `STIFFNER` — Allegro's own spelling, without
  the second *e* — and `EXPOXY` now colour as stiffener and adhesive instead of
  falling into undifferentiated grey.
  / **Шелкография больше не печатается по зонам, где её нет**
  (`format_version: 8`). Разрез назначает маски и покрытия **на каждый стек
  отдельно**, поэтому rigid-flex-плата говорит «на зонах стиффенера шелка нет»
  именно тем, что не включает слой шелка в эти стеки. Экспорт этот слой
  выбрасывал — правильно, он не часть тела — а вместе с ним и само утверждение,
  после чего легенда печаталась по всем зонам одинаково. Теперь каждый стек
  несёт объект `silkscreen` с указанием, какая его сторона печатается, а сборщик
  выбрасывает знаки, попавшие на непечатаемую зону. На демо-плате Cadence это 14
  полигонов сверху (над `CONN_FLEXI_STIFFENER` и `FLEXI_STIFFENER`) и 16 снизу
  (над `LCD_FLEXI_STIFFENER`), каждый — с именем зоны в логе. **Интермедиат,
  записанный раньше, об этом ничего не говорит и не обрезается**, так что ничего
  из уже имеющегося не изменится, — но чтобы легенду обрезало, плату надо
  экспортировать заново. Заодно: `STIFFNER` (как это пишет сам Allegro, без
  второй «e») и `EXPOXY` теперь красятся стиффенером и клеем, а не ровным серым.

- **2026-08-14** — **Arcs, seams and where the cutters go: three faults that
  each cost a flex arm.** Found by putting a build of Cadence's demo board next
  to Allegro's own 3D of it. **An arc's two angles bound it; the `ccw` flag says
  which end the contour enters it by, not which way the sweep goes** — read as a
  direction, a 90° corner becomes the 270° arc the long way round. Under the
  corrected reading every contour in that file joins up to 0.000 mm, the board
  outline included; before it, three of them had joints 5.7, 12.7 and 19.8 mm
  apart. The board body itself was safe (OpenCASCADE stitches edges in whatever
  order it likes) but every *shape* question built on the wrong answer — the
  FLEXI zone measured 2676 mm² where it is 1240. **Which side of a bend a piece
  sits on is now asked at the seam**, not from the piece's overall size: the main
  board is wide enough to lie on both sides of a bend line extended across the
  whole board, and one arm was being sewn on back to front and floated 23.8 mm
  clear of the board. **And the cutters that take a bend out of the board were
  placed relative to the origin instead of the board** — a design drawn away from
  (0, 0) missed its own cutter and simply lost that bend, with nothing said. All
  six bends of that board now build on true cylinders, and the folded body is
  99.97% of the flat one. A fold that does not join up is now reported.
  / **Дуги, швы и куда ставится резак: три ошибки, каждая стоила гибкого
  плеча.** Найдено сравнением нашей сборки демо-платы Cadence с её же 3D в
  Allegro. **Два угла дуги задают её границы, а флаг `ccw` говорит, с какого
  конца в неё входит контур, а не куда идёт обход** — прочитанный как
  направление, угол 90° превращается в дугу 270° в обход. При исправленном
  чтении все контуры файла сходятся до 0.000 мм, включая контур платы; до этого
  у трёх из них стыки расходились на 5.7, 12.7 и 19.8 мм. Само тело платы не
  страдало (OpenCASCADE сшивает рёбра в любом порядке), но все вопросы о
  *форме* отвечались неверно — зона FLEXI считалась 2676 мм² вместо 1240.
  **С какой стороны сгиба лежит кусок, теперь спрашивается на шве**, а не по
  габаритам куска: основная плата достаточно широка, чтобы лежать по обе стороны
  от линии сгиба, продлённой через всю плату, и одно плечо пришивалось задом
  наперёд и улетало от платы на 23.8 мм. **А резаки, вырезающие сгиб, ставились
  относительно нуля координат, а не платы** — проект, нарисованный в стороне от
  (0, 0), промахивался мимо собственного резака и просто терял этот сгиб, молча.
  Все шесть сгибов той платы теперь строятся на истинных цилиндрах, а объём
  сложенной платы — 99.97 % от плоской. Про несошедшийся шов теперь сообщается.

- **2026-08-14** — **A rigid-flex board with arms going several ways now folds
  correctly, and quickly.** Cadence's own demo board — three flex arms leaving
  the middle in three directions, six bends — crashed the export outright. Two
  readings behind that were wrong in the same way: a bend line was treated as a
  cut across the *whole* board rather than a segment on one arm. So two bends on
  opposite corners each counted as lying beyond the other (which is what
  crashed it), two perpendicular bends on one arm counted as claiming the same
  material and one of them was silently left flat, and — once the crash was
  fixed — a quarter of the board was being built **twice**, in two places, with
  the main board itself folded by a bend it has nothing to do with. The folded
  model weighed 114.7% of the flat one. **The bend areas now cut the flat board
  into pieces, and the pieces say what folds with what**: the piece your anchor
  is on is held, and every other is folded by the bends on the path back to it.
  Same board, same settings: 99.4% of the flat volume, a third of the geometry,
  and nothing claimed twice — which is checked on every build and reported if it
  ever is. **The printed legend is folded piece by piece instead of whole**,
  which took that board's full build from *not finished in 23 minutes* to **107
  seconds**. Also fixed: a stackup layer drawn only on the flex arms produced an
  empty part in the assembly instead of none.
  / **Rigid-flex с плечами в разные стороны теперь складывается правильно и
  быстро.** Демо-плата самой Cadence — три гибких плеча из середины в три
  стороны, шесть сгибов — валила экспорт. За этим стояли две ошибки одной
  природы: линия сгиба считалась разрезом через **всю** плату, а не отрезком на
  одном плече. Отсюда: два сгиба в противоположных углах считали друг друга
  «дальше себя» (это и было падение); два перпендикулярных сгиба на одном плече
  считались претендующими на один материал, и один из них молча оставался
  плоским; а когда падение починили — четверть платы строилась **дважды**, в
  двух местах, причём саму основную плату складывал сгиб, к которому она
  отношения не имеет. Сложенная модель весила 114.7% от плоской. **Теперь
  области сгиба режут плоскую плату на куски, и куски же говорят, что с чем
  складывается**: кусок с якорем удерживается, каждый остальной складывают
  сгибы на пути к нему. Та же плата, те же настройки: 99.4% от плоского объёма,
  втрое меньше геометрии и ничего, заявленного дважды, — это проверяется на
  каждой сборке и сообщается, если вдруг не так. **Шелкография складывается
  по одному элементу, а не целиком** — полная сборка этой платы прошла из
  «не закончилась за 23 минуты» в **107 секунд**. Заодно исправлено: слой стека,
  нарисованный только на плечах, давал в сборке пустую деталь вместо ничего.

- **2026-08-11** — **A board could come out of the export with no board in it.**
  Every file the exporter wrote after the first one carried the through-holes a
  second time: the cutout list is collected once per board and was then shared
  by every variant, each of which appended its own holes to it. With one variant
  that hit the whole-board file, with two it hit the second variant as well, and
  the repeat is not cosmetic — two identical holes make OpenCASCADE return an
  empty result, so the STEP arrived with components and legend and no board.
  Nothing said a word about it. **The exporter now gives every file its own copy
  of the list**, and **the builder drops a cutout that exactly repeats another
  one** — so an intermediate already on disk builds correctly too, with a line
  in the log — and it **no longer accepts an empty boolean as a board**: a
  boolean that produces nothing is now an error naming what to look at, instead
  of a STEP quietly missing its largest part. Fixed in the same pass:
  `settings.negativeLayers` and `settings.exportFullBoard` are restored to their
  defaults before *every* export rather than only when a config file is found,
  so a board exported with no config beside it no longer inherits whatever the
  previous board in that Allegro session set.
  / **Плата могла собраться без платы.** Каждый файл после первого нёс сквозные
  отверстия по второму разу: список вырезов собирается один раз на плату, а
  дальше был общим для всех вариантов, и каждый дописывал в него свои отверстия.
  При одном варианте это доставалось файлу полной платы, при двух — уже второму
  варианту. Повтор не косметический: два одинаковых отверстия заставляют
  OpenCASCADE вернуть пустой результат, и в STEP приезжали компоненты,
  шелкография и никакого тела платы. При этом нигде ни слова.
  **Теперь у каждого файла своя копия списка**, а **сборщик отбрасывает вырез,
  точно повторяющий другой** — так что уже записанный интермедиат тоже собирается
  правильно, со строкой в логе, — и **пустой результат булевой операции больше не
  считается платой**: теперь это ошибка с указанием, куда смотреть, а не молча
  потерянная самая большая деталь. Заодно: `settings.negativeLayers` и
  `settings.exportFullBoard` возвращаются к умолчаниям перед *каждым* экспортом,
  а не только когда файл настроек найден, — плата, экспортированная без конфига
  рядом, больше не наследует настройки предыдущей платы в той же сессии Allegro.

- **2026-08-07** — **The docs said *Body stitching* worked on rigid-flex boards
  only. It works on every board**, and has since 2026-07-25: an ordinary board
  has no zones, so its outline becomes one implicit zone on its single stackup
  and all three modes apply — *Solid colored layers* shows the stack on the rim
  of a plain two-layer board exactly as it does on a flex one. The two non-solid
  modes need the stackup layers, so an intermediate written by an older version
  says so in the log and falls back to one solid. The same wrong claim sat in
  `simple3d_config.json`, in `--board-mode --help` and in the builder's own
  docstring; all four are corrected. Found while checking the rest of the docs
  against the code, and also fixed: the ZIP-install note named the retired
  `S3D_ScriptDir` rather than `SIMPLE3D_DIR`; `settings.negativeLayers` matches
  a **substring**, not a prefix; the intermediate goes beside the `.brd` when
  there is no `cad` folder; and a part absent from a variant list is left out
  unless it carries `ALWAYS_STEP_EXPORT`. `QUICKSTART.md` says the same in
  fewer words.
  / **В документации было написано, что *Body stitching* работает только на
  rigid-flex. Он работает на любой плате**, и так с 2026-07-25: у обычной платы
  зон нет, поэтому её контур становится одной неявной зоной на единственном
  стекапе и применимы все три режима — *Solid colored layers* показывает стек на
  торце обычной двухслойки ровно так же, как на флексе. Двум режимам, кроме
  `Solid`, нужны слои стека, поэтому интермедиат от старой версии сообщает об
  этом в логе и собирается одним телом. То же неверное утверждение стояло в
  `simple3d_config.json`, в `--board-mode --help` и в докстринге сборщика —
  исправлены все четыре. Найдено при сверке остальной документации с кодом и
  тоже исправлено: в заметке про установку из ZIP упоминался снятый
  `S3D_ScriptDir` вместо `SIMPLE3D_DIR`; `settings.negativeLayers` сравнивается
  как **подстрока**, а не префикс; интермедиат пишется рядом с `.brd`, если папки
  `cad` нет; деталь, отсутствующую в списке варианта, оставляет только
  `ALWAYS_STEP_EXPORT`. `QUICKSTART.md` говорит то же самое короче.

- **2026-08-05** — **No absolute path is written into any shipped file.** The
  last two were `S3D_ScriptDir` in `simple3d.il` and the model folder in
  `simple3d_config.json`; both were one installation's path shipped to everyone
  and overwritten in everyone's working copy by the next update. Where the tool
  is installed now comes from `SIMPLE3D_DIR` in your own `pcbenv/env`, or from
  the folder `simple3d.il` was loaded from, and the console says which answered;
  when neither does, the export refuses to run rather than guessing. Model
  folders go in the window or in `simple3d_config.local.json`, which the window
  now writes **only where a value differs from the shipped default** — so
  setting one back to the default removes it again, and an improved default
  still reaches you.
  / **Ни одного абсолютного пути в поставляемых файлах.** Последними оставались
  `S3D_ScriptDir` в `simple3d.il` и папка моделей в `simple3d_config.json` —
  оба были путём одной установки, разосланным всем и затираемым в каждой рабочей
  копии очередным обновлением. Где установлен инструмент, теперь берётся из
  `SIMPLE3D_DIR` в вашем `pcbenv/env` либо из папки, откуда загружен
  `simple3d.il`; консоль называет сработавший источник, а если не ответил ни
  один — экспорт честно отказывается работать, вместо того чтобы гадать. Папки
  моделей задаются в окне или в `simple3d_config.local.json`, куда окно теперь
  пишет **только то, что отличается от поставляемого умолчания**: возврат
  значения к умолчанию убирает ключ, а улучшенное умолчание по-прежнему доходит.

- **2026-08-05** — **Your settings no longer live in a tracked file.**
  `simple3d_config.json` is under version control *and* was rewritten by the
  window on every close, so an update could not help but conflict with your
  model folders — and every commit carried someone's window position. It now
  holds the shipped defaults only. Beside it, **`simple3d_config.local.json`**
  holds what this installation does differently; the two are merged on read, key
  by key, local winning, and the window writes only the local one. It is
  gitignored, it is created for you on the first close, and deleting a key from
  it goes back to the shipped default. Improvements to the shared defaults still
  reach you, because the base file is still the one being updated. The one path
  that cannot live in a config — `S3D_ScriptDir`, which is what *finds* the
  config — can now come from your own Allegro environment file instead:
  `set SIMPLE3D_DIR = d:/…/Simple3D` in `%HOME%\pcbenv\env`, with the literal in
  `simple3d.il` left as the fallback.
  / **Ваши настройки больше не лежат в отслеживаемом файле.**
  `simple3d_config.json` был и под контролем версий, и переписывался окном при
  каждом закрытии — обновление не могло не конфликтовать с вашими папками
  моделей, а в каждый коммит попадало чьё-то положение окна. Теперь в нём только
  поставляемые умолчания. Рядом — **`simple3d_config.local.json`** с тем, что
  отличается у этой установки; при чтении они сливаются ключ за ключом, локальный
  побеждает, и окно пишет только его. Он в `.gitignore`, создаётся сам при первом
  закрытии, а удаление ключа из него возвращает поставляемое значение. Улучшения
  общих умолчаний при этом продолжают доходить, потому что обновляется по-прежнему
  базовый файл. Единственный путь, которому в конфиге места нет, — `S3D_ScriptDir`,
  который сам этот конфиг и находит, — теперь можно задать в своём файле окружения
  Allegro: `set SIMPLE3D_DIR = d:/…/Simple3D` в `%HOME%\pcbenv\env`; значение в
  `simple3d.il` остаётся запасным.

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
