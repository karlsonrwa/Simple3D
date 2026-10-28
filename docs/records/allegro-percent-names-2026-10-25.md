# Record: `%` in a variant name, exported by Allegro (25.10.2026, round 100)

Evidence for the 23.10.2026 review's R1-1 (a `%` in a model, zone, layer or variant name reached `fprintf` as its format). Made by `tools/skill_export.py`, which runs Allegro headless (`allegro -nograph -s <script> <board copy>`), on the owner's test board `variants_test-b0.brd` with the `Variants.lst` below beside it: twice, with the exporter as of round 99 (`4fcce38`, folder `before`) and with round 100's change (committed as `954cf89`, folder `after`). The board's own output is not in git (`input/` is ignored): this file keeps each JSON's first lines, size and SHA-256; the files themselves go with a review package. The Allegro console below is verbatim except that the repository's absolute path, in either case, is written `<repo>`; written by `build/fix-2026-10-28/make_pct_record.py`.

Allegro's own BOM report fails in both runs (`SPMHSK-7`, "Cannot find temporary data file"): that is Allegro's tool, not this exporter.

## Variants.lst

```
(
	("BOM 100%"

		(base
			(VT1 VT2 VT3 VT4 X1 X2 )
		)

	)
	("R_1%%"

		(base
			(VT1 VT2 VT3 VT4 X1 X2 )
		)

	)


)
```

## Before: round 99's exporter

Allegro's console (`variants_test-b0.allegro.txt`):

```
Loading axlcore.cxt 
Opening existing design...
Revising design for compatibility with current software.
Loading variants.cxt 
Generating Bill-of-Material report 'var-bom 100%.rpt' for design variant 'BOM 100%' ...
Loading cmds.cxt 
W- (SPMHSK-12): Component 'VT2' was not found in the design ... ignored.
W- (SPMHSK-12): Component 'VT3' was not found in the design ... ignored.
W- (SPMHSK-12): Component 'VT4' was not found in the design ... ignored.
W- (SPMHSK-12): Component 'X1' was not found in the design ... ignored.
W- (SPMHSK-12): Component 'X2' was not found in the design ... ignored.
E- (SPMHSK-7): Cannot find temporary data file 'var-bom 100%.srt' for input.
nil
Generating Bill-of-Material report 'var-r_1%%.rpt' for design variant 'R_1%%' ...
W- (SPMHSK-12): Component 'VT2' was not found in the design ... ignored.
W- (SPMHSK-12): Component 'VT3' was not found in the design ... ignored.
W- (SPMHSK-12): Component 'VT4' was not found in the design ... ignored.
W- (SPMHSK-12): Component 'X1' was not found in the design ... ignored.
W- (SPMHSK-12): Component 'X2' was not found in the design ... ignored.
E- (SPMHSK-7): Cannot find temporary data file 'var-r_1%%.srt' for input.
W- *WARNING* (axlSetFindFilter): Options are ignored for onButtons - "DYNTHEMALS"
nil
t
Simple 3D: silkscreen config: <repo>/simple3d_config.json
Simple 3D: negative (opening) layers: ("COVERLAY" "SOLDERMASK" "PASTEMASK")
Simple 3D: collecting silkscreen...
Simple 3D: silkscreen polygons - top 72, bottom 479
Simple 3D:   MANUFACTURING/AUTOSILK_TOP - 36 polygon(s)
Simple 3D:   PACKAGE GEOMETRY/SILKSCREEN_TOP - 36 polygon(s)
Simple 3D:   MANUFACTURING/AUTOSILK_BOTTOM - 236 polygon(s)
Simple 3D:   PACKAGE GEOMETRY/SILKSCREEN_BOTTOM - 236 polygon(s)
Simple 3D:   REF DES/SILKSCREEN_BOTTOM - 7 polygon(s)
Simple 3D: clipping silkscreen to the board outline...
Simple 3D: after clipping - top 18, bottom 85
Simple 3D: copper pads - 131 pin(s) and 65 via(s) on 21 padstack(s)
Simple 3D: exposed copper TOP - 0 drawn opening(s), 0 copper object(s), 0 polygon(s) of copper under them, 0 of bare laminate
Simple 3D: exposed copper BOTTOM - 58 drawn opening(s), 291 copper object(s), 60 polygon(s) of copper under them, 112 of bare laminate
Simple 3D: 2 variant(s) parsed from <repo>/build/tmp/s3dexport__h7m842t/Variants.lst
Simple 3D: variant list covers 1 of 48 placed component(s).
Exporting .json for variant: R_1%%
Simple 3D: MH1 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: MH2 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: FID4 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: FID3 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: FID2 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: FID1 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: 6 symbol(s) excluded by NO_STEP_EXPORT.
Simple 3D: 41 component(s) not installed in variant R_1%%.
Simple 3D: stackup PRIMARY - 2 silkscreen/paste layer(s) left out of the body.
Simple 3D: writing -> <repo>/build/fix-2026-10-25/pct/before/variants_test-b0/variants_test-b0_r_1%%.json
Simple 3D: wrote <repo>/build/fix-2026-10-25/pct/before/variants_test-b0/variants_test-b0_r_1%%.json
Exporting .json for variant: BOM 100%
Simple 3D: MH1 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: MH2 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: FID4 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: FID3 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: FID2 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: FID1 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: 6 symbol(s) excluded by NO_STEP_EXPORT.
Simple 3D: 41 component(s) not installed in variant BOM 100%.
Simple 3D: stackup PRIMARY - 2 silkscreen/paste layer(s) left out of the body.
Simple 3D: writing -> <repo>/build/fix-2026-10-25/pct/before/variants_test-b0/variants_test-b0_bom 100%.json
W- Simple 3D: variant R_1%% lists 5 component(s) that are not on this board: VT2, VT3, VT4, X1, X2
W- Simple 3D: variant BOM 100% lists 5 component(s) that are not on this board: VT2, VT3, VT4, X1, X2
E- *Error* fprintf/sprintf: illegal format spec. - "\t\"name\": \"variants_test-b0_bom 100%\","
nil
Allegro X Venture 25.1 S050 Windows SPB 64-bit Edition
   (c) Copyright 2025 Cadence Design Systems, Inc.
             All Rights Reserved.
```

The JSON files written:

`variants_test-b0_bom 100%.json` - 51 bytes, SHA-256 `d4cf3bb77f77eb1d51a50d95ba1d750ceb3c1374cc36c260ff70c56ce514052b`, does not parse (JSONDecodeError: Expecting property name enclosed in double quotes: line 4 column 1 (char 51)). Its first lines:

```
{
	"format": "simple3d",
	"format_version": 12,
```

`variants_test-b0_r_1%%.json` - 248975 bytes, SHA-256 `96a609ac1b6a0ae608c75315814271ead87c29a353d469eb91cb3b6d6b72e2d2`, parses. Its first lines:

```
{
	"format": "simple3d",
	"format_version": 12,
	"name": "variants_test-b0_r_1%",
	"stackups": {
```

## After: round 100's exporter

Allegro's console (`variants_test-b0.allegro.txt`):

```
Loading axlcore.cxt 
Opening existing design...
Revising design for compatibility with current software.
Loading variants.cxt 
Generating Bill-of-Material report 'var-bom 100%.rpt' for design variant 'BOM 100%' ...
Loading cmds.cxt 
W- (SPMHSK-12): Component 'VT2' was not found in the design ... ignored.
W- (SPMHSK-12): Component 'VT3' was not found in the design ... ignored.
W- (SPMHSK-12): Component 'VT4' was not found in the design ... ignored.
W- (SPMHSK-12): Component 'X1' was not found in the design ... ignored.
W- (SPMHSK-12): Component 'X2' was not found in the design ... ignored.
E- (SPMHSK-7): Cannot find temporary data file 'var-bom 100%.srt' for input.
nil
Generating Bill-of-Material report 'var-r_1%%.rpt' for design variant 'R_1%%' ...
W- (SPMHSK-12): Component 'VT2' was not found in the design ... ignored.
W- (SPMHSK-12): Component 'VT3' was not found in the design ... ignored.
W- (SPMHSK-12): Component 'VT4' was not found in the design ... ignored.
W- (SPMHSK-12): Component 'X1' was not found in the design ... ignored.
W- (SPMHSK-12): Component 'X2' was not found in the design ... ignored.
E- (SPMHSK-7): Cannot find temporary data file 'var-r_1%%.srt' for input.
W- *WARNING* (axlSetFindFilter): Options are ignored for onButtons - "DYNTHEMALS"
nil
t
Simple 3D: silkscreen config: <repo>/simple3d_config.json
Simple 3D: negative (opening) layers: ("COVERLAY" "SOLDERMASK" "PASTEMASK")
Simple 3D: collecting silkscreen...
Simple 3D: silkscreen polygons - top 72, bottom 479
Simple 3D:   MANUFACTURING/AUTOSILK_TOP - 36 polygon(s)
Simple 3D:   PACKAGE GEOMETRY/SILKSCREEN_TOP - 36 polygon(s)
Simple 3D:   MANUFACTURING/AUTOSILK_BOTTOM - 236 polygon(s)
Simple 3D:   PACKAGE GEOMETRY/SILKSCREEN_BOTTOM - 236 polygon(s)
Simple 3D:   REF DES/SILKSCREEN_BOTTOM - 7 polygon(s)
Simple 3D: clipping silkscreen to the board outline...
Simple 3D: after clipping - top 18, bottom 85
Simple 3D: copper pads - 131 pin(s) and 65 via(s) on 21 padstack(s)
Simple 3D: exposed copper TOP - 0 drawn opening(s), 0 copper object(s), 0 polygon(s) of copper under them, 0 of bare laminate
Simple 3D: exposed copper BOTTOM - 58 drawn opening(s), 291 copper object(s), 60 polygon(s) of copper under them, 112 of bare laminate
Simple 3D: 2 variant(s) parsed from <repo>/build/tmp/s3dexport_f522624j/Variants.lst
Simple 3D: variant list covers 1 of 48 placed component(s).
Exporting .json for variant: R_1%%
Simple 3D: MH1 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: MH2 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: FID4 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: FID3 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: FID2 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: FID1 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: 6 symbol(s) excluded by NO_STEP_EXPORT.
Simple 3D: 41 component(s) not installed in variant R_1%%.
Simple 3D: stackup PRIMARY - 2 silkscreen/paste layer(s) left out of the body.
Simple 3D: writing -> <repo>/build/fix-2026-10-25/pct/after/variants_test-b0/variants_test-b0_r_1%%.json
Simple 3D: wrote <repo>/build/fix-2026-10-25/pct/after/variants_test-b0/variants_test-b0_r_1%%.json
Exporting .json for variant: BOM 100%
Simple 3D: MH1 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: MH2 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: FID4 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: FID3 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: FID2 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: FID1 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: 6 symbol(s) excluded by NO_STEP_EXPORT.
Simple 3D: 41 component(s) not installed in variant BOM 100%.
Simple 3D: stackup PRIMARY - 2 silkscreen/paste layer(s) left out of the body.
Simple 3D: writing -> <repo>/build/fix-2026-10-25/pct/after/variants_test-b0/variants_test-b0_bom 100%.json
Simple 3D: wrote <repo>/build/fix-2026-10-25/pct/after/variants_test-b0/variants_test-b0_bom 100%.json
Simple 3D: MH1 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: MH2 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: FID4 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: FID3 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: FID2 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: FID1 - NOT exported: the symbol carries the NO_STEP_EXPORT property.
Simple 3D: 6 symbol(s) excluded by NO_STEP_EXPORT.
Simple 3D: stackup PRIMARY - 2 silkscreen/paste layer(s) left out of the body.
Simple 3D: writing -> <repo>/build/fix-2026-10-25/pct/after/variants_test-b0/variants_test-b0.json
Simple 3D: wrote <repo>/build/fix-2026-10-25/pct/after/variants_test-b0/variants_test-b0.json
Simple 3D: plus the whole board (variants ignored) -> variants_test-b0.json
Simple 3D: export complete - 2 variant(s) written.
W- Simple 3D: variant R_1%% lists 5 component(s) that are not on this board: VT2, VT3, VT4, X1, X2
W- Simple 3D: variant BOM 100% lists 5 component(s) that are not on this board: VT2, VT3, VT4, X1, X2
(t)
Allegro X Venture 25.1 S050 Windows SPB 64-bit Edition
   (c) Copyright 2025 Cadence Design Systems, Inc.
             All Rights Reserved.
```

The JSON files written:

`variants_test-b0.json` - 263040 bytes, SHA-256 `5d74aaa524d971f4c8e85b9e9fce5e266f2a7982fe4c73745ba24549b4c63ad4`, parses. Its first lines:

```
{
	"format": "simple3d",
	"format_version": 12,
	"name": "variants_test-b0",
	"full_board": true,
```

`variants_test-b0_bom 100%.json` - 248983 bytes, SHA-256 `9376c8722b7a7843836c630c2bc01fcbd0e081f31550a761cafd69279db8bd4f`, parses. Its first lines:

```
{
	"format": "simple3d",
	"format_version": 12,
	"name": "variants_test-b0_bom 100%",
	"stackups": {
```

`variants_test-b0_r_1%%.json` - 248977 bytes, SHA-256 `b4ba5b3f4cd3cf2bc360cd7997c8b3eb391356b57549c1edada4a3bc1e24a90d`, parses. Its first lines:

```
{
	"format": "simple3d",
	"format_version": 12,
	"name": "variants_test-b0_r_1%%",
	"stackups": {
```

## По-русски

Запись к находке R1-1 ревью 23.10.2026: знак `%` в имени варианта попадал в `fprintf` как формат. Allegro 25.1 без окна дважды выгрузил тестовую плату владельца `variants_test-b0.brd` с вариантами «BOM 100%» и «R_1%%»: экспортёром раунда 99 (`before`) и с правкой раунда 100 (`after`). До правки файл варианта «BOM 100%» обрывается на третьей строке (51 байт), консоль пишет «illegal format spec.», файл всей платы не записан, а у «R_1%%» в имени `r_1%`. После правки все три файла целы и читаются, имена точные. Консоль Allegro приведена дословно, заменён только абсолютный путь репозитория на `<repo>`. Сами JSON в git не кладутся (это плата владельца, папка `input/` не отслеживается): здесь их начало, размер и SHA-256, а файлы идут в пакет ревью.
