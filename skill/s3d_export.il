;=====================================================================
;  skill/s3d_export.il - symbolReturn3DElements, makePcb, the JSON writer, the entry point
;
;  Part 9 of 9 of the Simple 3D exporter, cut from
;  makeVariant3dIntermediates.il in round 76 (plan D6) with every procedure
;  and comment as it was; that file loads the parts in order. Load it, or
;  simple3d.il, never a part on its own.
;=====================================================================

;=====================================================================
;  makeVariant3dIntermediates.il
;
;  Exports an Allegro PCB design to an intermediate JSON that the
;  "Simple 3D" Python tool turns into a STEP assembly.
;
;  ORIGIN & CREDIT
;  Based on the original makeVariant3dIntermediates.il by juulsA
;  (https://github.com/juulsA/exportStep). This copy has been
;  modified for the Simple 3D toolchain. Changes vs the original are
;  marked inline with "FIX (simple3d)" or "NEW (simple3d)":
;    * addIndent() - was called 8x but never defined in the repo; added here
;      as s3dAddIndent(), prefixed so it cannot collide with the real one.
;    * getVariantInfo -> gdsysGetVariantInfo (the defined name).
;    * calculateBoardThickness - only SOLDERMASK counts toward the mask
;      thickness; SILKSCREEN/PASTEMASK are also layerType "MASK" and were
;      wrongly folded in and overwritten. Side is decided by position.
;    * makePcb - the no-cutout branch emitted a bare "thickness": 1.67
;      scalar the reader rejects; now emits the real thickness object.
;    * makeSlot - makeCircle was called with 3 args; it takes (xy diameter).
;    * removed a leftover debug printf("i am here").
;    * symbolReturn3DElements - now also emits "mfr_pn" (the MFRPN article
;      number, read from the component definition) for the STEP writer.
;    * s3dGetMfrPn / s3dJsonEscape / s3dCheckMfrPn helpers added.
;    * SILKSCREEN export (format_version 2) - see the SILKSCREEN section
;      below. Adds a small JSON reader so the layer list lives in
;      simple3d_config.json, collection of the silkscreen as filled
;      polygons, and clipping to the board area.
;    * create3dIntermediateFormat - guarded the case where no component has
;      a STEP mapping (car of an unbound marker faulted).
;    * WHAT GETS EXPORTED - the symbol list is built from the design and the
;      variant table only removes from it, so a symbol the Variants.lst
;      parser does not return (mechanical components) is no longer lost.
;      NO_STEP_EXPORT excludes a symbol outright, and says so by name.
;    * symbolReturn3DElements - takes the symbol dbid the caller already
;      holds instead of resolving a refdes string through two lookups.
;
;  USAGE
;    makeVariant3dIntermediates( outputDir [ pcbColor ] [ configFile ] )
;  Writes <design>.json (or one <design>_<variant>.json per variant if a
;  Variants.lst sits BESIDE THE BOARD) into outputDir. Design units must be mm.
;  configFile is the silkscreen layer/settings JSON; when omitted,
;  "simple3d_config.json" in the working directory is used if present, and
;  otherwise the built-in defaults apply.
;=====================================================================


; FIX (simple3d 2026-07-22): takes the SYMBOL dbid, not a refdes string.
;
; It used to take a name and resolve it with axlDBFindByName( 'refdes ... ),
; which returns a component instance, whose ->symbol is then the symbol. Two
; lookups that can each come back empty, for a symbol the caller was already
; holding. Callers now iterate the design, so the dbid is passed straight
; through and refdes is read off it. A string is still accepted, because it
; costs three lines and keeps the old call shape working.
procedure( symbolReturn3DElements( g_symbol g_state )
    let( ( stepPackageMapping refDes dbid sym mappingData stepFileName offset_x offset_y offset_z rotation_x rotation_y rotation_z isMirrored xy angle hole mfrPn zone zoneName ( holes 'unbound ) )

        stepPackageMapping = nil

        if( stringp( g_symbol ) then
            refDes = g_symbol
            dbid = axlDBFindByName( 'refdes refDes )
            sym = dbid->symbol
        else
            sym = g_symbol
            refDes = sym->refdes
            ; A mechanical symbol has no refdes (docs: "nil if no associated
            ; component"). Synthesise a unique, readable JSON key from the symbol
            ; name plus a per-export sequence (CR2032_MECH1, CR2032_MECH2, ...),
            ; so several of them cannot collapse onto one duplicate JSON key -
            ; json.load keeps only the last, which would silently drop the rest.
            unless( stringp( refDes )
                g_state['mechSeq] = g_state['mechSeq] + 1
                refDes = sprintf( nil "%s_MECH%d"
                                  if( sym->name then sym->name else "MECH" )
                                  g_state['mechSeq] )
            )
        )

        ; step package mappingData
        ; Guard the call: an unresolved refdes used to reach axlStepGet(nil nil
        ; nil), which warned opaquely and then dropped the component in silence.
        ; Name it instead. mappingData stays nil -> stepFileName stays nil -> the
        ; when(stepFileName ...) below still skips it, so behaviour is unchanged
        ; apart from the message.
        if( sym then
            mappingData = axlStepGet( nil nil sym )
        else
            printf( "Simple 3D: %s - not found in the design, skipped.\n" refDes )
        )
        stepFileName = mappingData->step_name

        offset_x = mappingData->offset_x
        offset_y = mappingData->offset_y
        offset_z = mappingData->offset_z

        rotation_x = mappingData->rotation_x
        rotation_y = mappingData->rotation_y
        rotation_z = mappingData->rotation_z

        ; MFRPN DISABLED (property attachment unreliable); kept for future.
        ; It lives on the component definition, not the instance:
        ; mfrPn = s3dGetMfrPn( dbid->component )

        ; symbol
        if( sym->isMirrored then
            isMirrored = "true"
        else

            isMirrored = "false"
        )

        xy = sym->xy
        angle = sym->rotation

        ; The zone this part stands in, by its own placement point.
        ; axlZoneAccess is the documented way to ask; its reference says the
        ; return is "xy", which cannot be right for a zone lookup, so the name
        ; is read defensively and stays nil if the answer is not a zone dbid.
        zoneName = nil
        zone = nil
        errset( zone = axlZoneAccess( 'point xy ) )
        when( zone
            errset( zoneName = zone->name )
        )
        unless( stringp( zoneName )  zoneName = nil )

        ; set step package mapping
        when( stepFileName
            stepPackageMapping = strcat(
                s3dJsonQuote( sprintf( nil "%s" refDes ) ) ": {\n"
                "\t\"step_mapping\": {\n"
                "\t\t\"step_name\": " s3dJsonQuote( sprintf( nil "%s" stepFileName ) ) ",\n"
                "\t\t\"rotation_x\": " sprintf( nil "%f" rotation_x ) ",\n"
                "\t\t\"rotation_y\": " sprintf( nil "%f" rotation_y ) ",\n"
                "\t\t\"rotation_z\": " sprintf( nil "%f" rotation_z ) ",\n"
                "\t\t\"offset_x\": " sprintf( nil "%f" offset_x ) ",\n"
                "\t\t\"offset_y\": " sprintf( nil "%f" offset_y ) ",\n"
                "\t\t\"offset_z\": " sprintf( nil "%f" offset_z ) "\n"
                "\t},\n"
                ; MFRPN DISABLED (kept for future). The "},\n" above already ends
                ; step_mapping with a comma, so dropping mfr_pn keeps valid JSON:
                ; "\t\"mfr_pn\": " if( mfrPn then
                ;                      strcat( "\"" s3dJsonEscape( mfrPn ) "\"" )
                ;                  else
                ;                      "null" ) ",\n"
                ; Which stackup zone this part stands on. On a rigid-flex board
                ; a part on a 2.44 mm stiffener and one on 0.365 mm flex sit at
                ; very different heights, so the reader needs to know which
                ; surface to place it on. nil on an ordinary board, and the
                ; reader then falls back to the single board surface.
                "\t\"zone\": " s3dJsonQuote( zoneName ) ",\n"     ; nil -> null
                "\t\"is_mirrored\": " isMirrored ",\n"
                "\t\"x\": " sprintf( nil "%f" xCoord( xy ) ) ",\n"
                "\t\"y\": " sprintf( nil "%f" yCoord( xy ) ) ",\n"
                "\t\"angle\": " sprintf( nil "%f" angle ) "\n"
                "}"
            )
        )

        stepPackageMapping
    )
)

procedure( makePcb( thicknesses edges cuts color )
    let( ( colorJson arrays )
        ; colorJson, not pcbColor: that is the caller's parameter name, and an
        ; undeclared assignment to it here rebound the caller's variable
        ; (round 75, D2).
        colorJson = strcat(
          "\"color\": {\n"
          "\t\"r\": " sprintf( nil "%f" car( color ) ) ",\n"
          "\t\"g\": " sprintf( nil "%f" cadr( color ) ) ",\n"
          "\t\"b\": " sprintf( nil "%f" caddr( color ) ) "\n"
          "}"
        )
        ; FIX (simple3d 2026-07-22): was  if( boundp( 'cuts ) ...).
        ; cuts is a FORMAL PARAMETER, so it is bound the moment the call
        ; succeeds - boundp is always t here and the else branch below was dead
        ; code. Test the value instead, so a board that really has nothing to
        ; cut takes the no-cuts branch and emits a valid "edges" array. With the
        ; boundp test, nil cuts produced a trailing comma:
        ;     "edges": [ [ ...outline... ],  ]
        ; which is not JSON. See also the call site, which must not evaluate an
        ; unbound cuts in the first place.
        ; "edges" is an array of arrays: the outline first, then each cutout
        ; and hole. Built as a LIST and joined once (round 77, D8) - the two
        ; branches this replaces differed only in whether a comma followed
        ; the outline, and the no-cuts branch once emitted a bare scalar
        ; thickness the reader rejected (FIX, simple3d 2026-07-22).
        arrays = list( strcat( "[\n" s3dAddIndent( buildString( car( edges ) ",\n" ) ) "\n]" ) )
        when( cuts
            arrays = append( arrays car( cuts ) )
        )
        ; "thickness" is optional since format_version 9 (round 79, E2): nil on
        ; a rigid-flex design with no PRIMARY stackup, and the reader measures
        ; it from the stackups instead.
        strcat(
            "\"pcb\": {\n"
            if( thicknesses then
                strcat(
                    "\t\"thickness\": {\n"
                    "\t\t\"soldermask_top\": " sprintf( nil "%f" car( thicknesses ) ) ",\n"
                    "\t\t\"board\": " sprintf( nil "%f" cadr( thicknesses ) ) ",\n"
                    "\t\t\"soldermask_bottom\": " sprintf( nil "%f" caddr( thicknesses ) ) "\n"
                    "\t},\n" )
            else
                "" )
            s3dAddIndent( colorJson )
            ",\n"
            "\t\"edges\": [\n"
            s3dAddIndent( buildString( arrays ",\n" ) 2 )
            "\n\t]\n}"
        )
    )
)

; g_fullBoard: this file is the WHOLE board with variants ignored, and says so
; in the JSON. An explicit argument rather than a global, because a global read
; at write time is the round-42 shape - it would describe whatever the previous
; call set if this one ever forgot to.
procedure( create3dIntermediateFormat( thicknesses edgeCuts pcbColor symbols variantName fileName g_state @optional ( silk nil ) ( g_fullBoard nil ) )
    let( ( ( stepModelPlacements 'unbound ) ( edges 'unbound ) ( cut 'unbound ) ( cuts 'unbound ) baseCut body
           placement members pcb outFile outPort lines )   ; declared here, not in the caller (round 75, D2)
        ; The export state, per FILE (round 77, D7; the caller made the table
        ; and owns its per-design half): the no-refdes mechanicals are numbered
        ; from 1 in each file (see symbolReturn3DElements), and the RIGID FLEX
        ; shapes are rebuilt - a shape added between two runs in one session
        ; must be picked up, and it is one query.
        g_state['mechSeq] = 0
        g_state['shapes] = nil

        ; reset base board contour
        when( car( edgeCuts )
            edges = car( edgeCuts )
        )

        ; The cutouts are collected ONCE, by makePcbContour, and the SAME list
        ; is handed to every export of this run - one per variant, plus the
        ; whole-board file. So it has to be COPIED here, not aliased.
        ;
        ; FIX (simple3d 2026-08-11): was  cuts = cadr( edgeCuts ), an alias.
        ; The tconc below appends IN PLACE, so each export's pin holes stayed
        ; in the caller's list and the next file got them a second time. The
        ; first file written was correct and every one after it carried one
        ; more copy of every through-hole - with one variant, that is the
        ; whole-board file; with two, the second variant already. A duplicated
        ; cutout is not cosmetic: two coincident prisms make OCC's boolean
        ; return an empty result, and the board body disappears from the STEP
        ; with no error anywhere. Found on 8231-a2, whose two slot holes came
        ; out twice.
        when( cadr( edgeCuts )
            foreach( baseCut car( cadr( edgeCuts ) )
                if( boundp( 'cuts ) then
                    tconc( cuts baseCut )
                else
                    cuts = tconc( nil baseCut )
                )
            )
        )

        ; export step package mapping information
        foreach( symbol symbols
            placement = symbolReturn3DElements( symbol g_state )

            when( placement
                if( boundp( 'stepModelPlacements ) then
                    tconc( stepModelPlacements placement )
                else
                    stepModelPlacements = tconc( nil placement )
                )
            )
        )

        ; export symbol pin holes
        cut = symbolReturnPinHoles()
        when( cut
            if( boundp( 'cuts ) then
                tconc( cuts cut )
            else
                cuts = tconc( nil cut )
            )
        )

        ; The top-level members, each a `"key": value` string with NO comma:
        ; the join below is the one place that puts commas between them
        ; (round 77, D8; until then the header carried them by hand, the
        ; placements were joined separately and glued on with another, and
        ; the silkscreen needed a third). First a format marker, so the
        ; Python side can tell a Simple 3D intermediate from any other .json
        ; that happens to sit in the folder - files without "format":
        ; "simple3d" are ignored by the GUI.
        ; NOTE: no embedded \t here - the line writer below prefixes every line
        ; with one tab, so embedding another would double-indent these keys
        ; (still valid JSON, but inconsistent with the rest of the file).
        ; format_version 2 added the optional "silkscreen" object; 3 tags every
        ; silkscreen polygon with the layer it came from, so the layers can be
        ; switched on and off when the model is built instead of at export
        ; time; 4 adds the optional "embedded_models" list; 5 adds "zones" plus
        ; a per-component "zone", for multi-stackup and rigid-flex boards; 6
        ; gives every stackup layer its own extent and shapes; 7 adds "bends";
        ; 8 gives every stackup a "silkscreen" object saying which of its sides
        ; is printed on, which is how a zone says it carries no legend; 9 puts
        ; every component under one "components" object instead of beside the
        ; metadata (round 79, plan E1), so a reader of v9 need not know which
        ; keys are NOT components.
        ; All of them are optional to a reader - an older file simply has no
        ; layers to choose from, nothing to say about embedded models, an empty
        ; zone list, which means "ordinary single-stackup board", and no bends,
        ; which means a board that is exported flat.
        ;
        ; NOTE: every top-level key added here must also be listed in the RESERVED
        ; tuple of stepbuilder/intermediate.py: that is how a v1-v8 file, whose
        ; components sit beside the metadata, is still read.
        members = list(
            "\"format\": \"simple3d\""
            "\"format_version\": 9"
            strcat( "\"name\": " s3dJsonQuote( variantName ) )
        )
        ; Optional, and only ever true: the whole board, variants ignored.
        ; A reader that does not know the key sees an ordinary intermediate,
        ; which is what every version before this one will do.
        when( g_fullBoard
            members = append( members list( "\"full_board\": true" ) )
        )
        members = append( members list(
            s3dEmbeddedModelsJson()
            s3dStackupsJson( g_state )
            s3dZonesJson()
            s3dBendsJson( g_state )
        ) )

        ; make pcb (including all cutouts and holes)
        ;
        ; FIX (simple3d 2026-07-22): "*Error* eval: unbound variable - cuts",
        ; and no JSON written at all, on a board with NO cutouts and NO
        ; through-hole pins. Both `when`s above then leave `cuts` holding the
        ; 'unbound marker, and passing it here evaluates it. An all-SMD board
        ; without a CUTOUT shape is perfectly ordinary; it just had not been
        ; exported before. Same for `edges` if a design somehow has no outline
        ; segments - nil reaches the Python reader, which says "pcb.edges is
        ; empty" instead of dying in SKILL.
        pcb = makePcb( thicknesses
                       if( boundp( 'edges ) then edges else nil )
                       if( boundp( 'cuts ) then cuts else nil )
                       pcbColor )
        members = append( members list( pcb ) )

        ; the step model placements, under one "components" object (v9) - {}
        ; when no component has a STEP mapping, which is a legitimate export
        ; (a bare board with its silkscreen) and used to fault on the 'unbound
        ; marker (FIX, simple3d).
        members = append( members list(
            if( boundp( 'stepModelPlacements ) then
                strcat( "\"components\": {\n"
                        s3dAddIndent( buildString( car( stepModelPlacements ) ",\n" ) )
                        "\n}" )
            else
                "\"components\": {}"
            ) ) )

        ; write to file
        outFile = fileName
        printf( "Simple 3D: writing -> %s\n" outFile )
        outPort = outfile( outFile )

        ; FIX (simple3d): outfile returns nil if the path could not be opened
        ; (missing folder, permissions, etc). Without this guard the following
        ; fprintf's silently do nothing and the caller still prints
        ; "Export complete!", leaving an empty/absent .json that the GUI then
        ; cannot find. Fail loudly instead.
        unless( outPort
            error( "Simple 3D: outfile() returned nil for: %s\n(check the folder exists and the path/permissions)\n" outFile )
        )

        ; One join decides the commas. The body is re-indented line by line
        ; below rather than written in one fprintf (which ran out of memory
        ; on a large board); the silkscreen is streamed after it, so when
        ; there is one the last member needs its comma too.
        body = buildString( members ",\n" )
        when( silk
            body = strcat( body "," )
        )
        lines = parseString( body "\n" )

        fprintf( outPort "{\n")

        foreach( line lines
            fprintf( outPort strcat( "\t" line ) )
            fprintf( outPort "\n" )
        )

        ; Streamed straight to the port instead of being folded into the string
        ; above - see s3dWriteSilkPolys for why.
        when( silk
            s3dWriteSilkscreen( outPort silk )
        )

        fprintf( outPort "}\n")

        close( outPort )

        ; confirm the file actually landed on disk
        if( isFile( outFile ) then
            printf( "Simple 3D: wrote %s\n" outFile )
        else
            error( "Simple 3D: file was NOT created after close: %s\n" outFile )
        )

        t
    )
)

procedure( makeVariant3dIntermediates( dir, @optional ( pcbColor list( 0.0 0.4 0.0) ) ( configFile nil ) )
    let( (  ( variantFile s3dVariantFilePath() ) dsnName dsn thicknesses edgeCuts silk variantInformation variantSymbolList alternateParts variant variantCount symbols variantName fileName state )
        ; The list used to go on: a second `thicknesses`, and `elements placement
        ; outFile outPort pcb lines` - names this procedure never touches. They
        ; were create3dIntermediateFormat's, reaching its let through SKILL's
        ; dynamic scope; since round 75 (D2) it declares them itself.

        ; get design and design name
        dsnName = axlCurrentDesign()
        dsn = axlDBGetDesign()

        ; The export state (round 77, D7): what one export accumulates, in one
        ; table handed down through the writers instead of four session
        ; globals reset in two places. Per DESIGN: the RIGID FLEX shapes and
        ; the bend lines - dbids of THIS database; as globals they used to
        ; survive from one board to the next (the SKILL files load once per
        ; session) and the second export described the FIRST board, with
        ; nothing to say so - and the silkscreen warnings. Per FILE: the
        ; sequence that numbers no-refdes mechanicals, which
        ; create3dIntermediateFormat restarts.
        state = makeTable( "s3dExportState" nil )
        state['shapes] = nil
        state['bendLines] = nil
        state['silkWarnings] = nil
        state['mechSeq] = 0

        ; create dir (recursively - createDir makes only one level at a time,
        ; so walk the path and create each missing segment).
        s3dMakeDirs( dir )

        ; calculate pcb thickness - by position, from the board's own stackup
        ; (round 76, D5); nil when no stackup is the board (round 79, E2).
        thicknesses = s3dBoardThickness()

        ; make pcb contour
        edgeCuts = makePcbContour( dsn )

        ; Collect the silkscreen ONCE, outside the variant loop. The bare board
        ; is manufactured once and serves every assembly variant, so its printed
        ; legend does not change when a component is not installed - the legend
        ; of a DNP part is still physically on the board. Every variant JSON
        ; therefore carries the same silkscreen (and, like edgeCuts, it costs
        ; one collection pass no matter how many variants there are).
        ; errset with a second argument PRINTS the SKILL error before
        ; returning nil, and errset itself returns nil only on failure. The
        ; bare errset this replaces hid every silkscreen fault behind an empty
        ; legend: the export finished, the JSON had no "silkscreen" key, and
        ; the console said nothing at all. A swallowed error is worse than a
        ; loud one - the board still exports either way.
        silk = nil
        unless( errset( silk = s3dMakeSilkscreen( s3dSilkConfig( configFile ) state ) t )
            s3dErr( "Simple 3D: silkscreen collection failed (message above)." )
            s3dErr( "Simple 3D: the board and its components are still exported; only the legend is missing." )
            silk = nil
        )

        if( isFile( variantFile ) then
            ; Read / parse variant list
            variantInformation = gdsysGetVariantInfo()

            if( variantInformation then
                variantSymbolList = car( variantInformation )
                alternateParts = cadr( variantInformation )

                ; FIX (simple3d): variantSymbolList is a table (from makeTable),
                ; not a list - it is always truthy and length() does not apply,
                ; so count its keys by iterating. If a Variants.lst is present
                ; but yields zero variants for THIS board, the foreach below
                ; runs zero times, no JSON is written, yet "Export complete!"
                ; still prints. That usually means the Variants.lst in the
                ; working folder belongs to a DIFFERENT project. Surface it.
                variantCount = 0
                foreach( variant variantSymbolList
                    variantCount = variantCount + 1
                )
                printf( "Simple 3D: %d variant(s) parsed from %s\n"
                        variantCount variantFile )
                when( variantCount == 0
                    error( strcat(
                        "Simple 3D: a Variants.lst was found but no matching "
                        "variants were parsed for this board.\n"
                        "The file likely belongs to a different project. "
                        "Delete or replace the Variants.lst in the design "
                        "folder, or remove it to export all components.\n" ) )
                )

                ; Does the table describe THIS board? A file that parses but
                ; names another project's components, or none at all, exports
                ; the whole board under variant names and says nothing.
                s3dVariantFit( variantSymbolList variantFile )

                foreach( variant variantSymbolList
                    printf( "Exporting .json for variant: %s\n" variant )

                    ; FIX (simple3d 2026-07-21): was
                    ;   symbols = append( variantSymbolList[variant]
                    ;                     alternateParts[variant]~>? )
                    ; The ~>? half was actually FINE - alternateParts[variant] is
                    ; a table (dumps as "table:parts") keyed by refdes, so ~>?
                    ; returned (C43 C44) and those components were placed. The
                    ; junk came from the OTHER side: gdsysGetVariantInfo's parser
                    ; appended the first property token instead of the refdes to
                    ; the variant's symbol list (fixed above, both branches), so
                    ; variantSymbolList carried two bogus "VALUE=12pF" entries.
                    ;
                    ; With the parser fixed, variantSymbolList[variant] holds every
                    ; installed refdes - base parts AND alternate parts - so the
                    ; append is now redundant and would duplicate C43/C44.
                    ; alternateParts stays available for its actual purpose: the
                    ; per-part property overrides, which a 3D export does not need.
                    ;
                    ; (The old boundp('alternateParts) test was dead anyway - a
                    ; plain let local assigned unconditionally above, so always
                    ; bound. Noted as "Minor" back in round 2.)
                    ;
                    ; FIX (simple3d 2026-07-22): was
                    ;   symbols = variantSymbolList[variant]
                    ; i.e. the parsed variant list WAS the export list, so a
                    ; symbol the parser did not return could not be exported at
                    ; all - which is how mechanical components went missing.
                    ; The list now comes from the design and the variant table
                    ; only removes from it. See s3dSymbolsToExport.
                    symbols = s3dSymbolsToExport( variantSymbolList variant )

                    variantName = lowerCase( strcat( dsnName "_" variant ) )
                    fileName = lowerCase( strcat( dir "/" variantName ".json" ) )
                    create3dIntermediateFormat( thicknesses edgeCuts pcbColor symbols variantName fileName state silk )
                )

                ; And the whole board, variants ignored, as one more file. Same
                ; routine with no variant table - so NO_STEP_EXPORT still
                ; excludes, and nothing else does. The name is the one the
                ; no-variant export uses, which cannot collide with
                ; <design>_<variant>.json; the window tells it apart by the
                ; "full_board" marker rather than by guessing from the name.
                when( S3D_ExportFullBoard
                    symbols = s3dSymbolsToExport( nil nil )
                    variantName = lowerCase( dsnName )
                    fileName = strcat( dir "/" variantName ".json" )
                    create3dIntermediateFormat( thicknesses edgeCuts pcbColor
                                                symbols variantName fileName
                                                state silk t )
                    printf( "Simple 3D: plus the whole board (variants ignored) -> %s.json\n"
                            variantName )
                )

                ; print() quotes its argument and adds no newline; this is a
                ; message to a person, not a value being dumped.
                ;
                ; No green: axlUIWPrint's severities are info0, info1, warn,
                ; error and fatal, and none of them is "success". A completion
                ; line therefore prints in the console's ordinary color. The
                ; GUI log does color its own completion line green, and that
                ; is where the result is actually judged.
                printf( "Simple 3D: export complete - %d variant(s) written.\n"
                        variantCount )
            else
                error( "No variant information could be read!" )
            )
        else
            ; export all symbols, if no variant.lst can be found
            ; Name the path it looked at. "No variant information present" on
            ; its own is indistinguishable from "your Variants.lst was not
            ; found", and those need different things done about them.
            warn( "No variant information present!\n Exporting all components!" )
            printf( "Simple 3D: no Variants.lst beside the board (looked for %s)\n"
                    variantFile )

            ; Same routine as the variant path, with no variant table: every
            ; symbol that has a refdes and is not marked NO_STEP_EXPORT.
            symbols = s3dSymbolsToExport( nil nil )

            variantName = lowerCase( dsnName )
            fileName = strcat( dir "/" variantName ".json" )
            create3dIntermediateFormat( thicknesses edgeCuts pcbColor symbols variantName fileName state silk )
        )
    )
)
