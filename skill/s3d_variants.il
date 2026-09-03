;=====================================================================
;  skill/s3d_variants.il - Variants.lst (the upstream parser), which symbols a variant exports
;
;  Part 4 of 9 of the Simple 3D exporter, cut from
;  makeVariant3dIntermediates.il in round 76 (plan D6) with every procedure
;  and comment as it was; that file loads the parts in order. Load it, or
;  simple3d.il, never a part on its own.
;=====================================================================


; Every refdes the variant table mentions anywhere, upper-cased. Used to judge
; whether the FILE describes this board (s3dVariantFit), not to decide any one
; symbol's fate: a refdes the table never mentions is not exported either, since
; the list governs everything that has one.
;
; Is this token from the variant list a reference designator at all?
;
; The parser splits its lines on spaces and strips a fixed set of characters,
; which leaves the odd bare "\n" behind when a line ends in " )". Such a token
; can never match a real refdes, so it has never changed an export - but it does
; land in the counts ("variant list covers N of M"), and a diagnostic number
; that is quietly one too big is worse than no number.
procedure( s3dIsRefdesToken( t_token )
    stringp( t_token ) && rexMatchp( "[A-Za-z0-9]" t_token )
)

procedure( s3dVariantKnownRefdes( g_variantSymbolList )
    let( ( known )
        known = makeTable( "s3dKnownRefdes" nil )
        when( g_variantSymbolList
            foreach( variant g_variantSymbolList
                foreach( refdes g_variantSymbolList[variant]
                    when( s3dIsRefdesToken( refdes )
                        known[upperCase( refdes )] = t
                    )
                )
            )
        )
        known
    )
)

; Is this symbol a mechanical part? DIAGNOSTIC ONLY - it does not decide an
; export.
;
; It used to be the variant rule (round 49). The rule is now simply "has a
; refdes -> the variant list governs it" (user decision, 2026-08-03), because a
; MECHANICAL-class part with a refdes CAN be named in the list, and when the
; list does not name it the honest reading is "not installed" - the same as for
; any other part. What survives of round 49 is its first test: a symbol with no
; refdes has no logical component either (the docs: refdes is "nil if no
; associated component"), so the two are one condition and the export tests the
; simpler one.
;
; Kept because probe_variants.il reports WHICH KIND of part each symbol is, and
; the three reads below are the only place that question is answered. All read
; defensively - a board can carry a symbol in an unusual state, and none of
; these reads is worth an aborted export:
;
;   * NO LOGICAL COMPONENT. A symbol placed in the layout that the netlist does
;     not know has no `component` at all - and a part that is not in the
;     schematic cannot possibly be in a variant list generated from it. This is
;     the one that matters for a bracket or a mating connector added in Allegro
;     alone, whatever class its symbol happens to carry.
;   * the SYMBOL's own type, "MECHANICAL" (an .osm placed directly, usually
;     without a refdes at all).
;   * the component definition's CLASS, where a PLACED part with a refdes says
;     it is mechanical. On variants_test-b0, A1 and A2 are MOLEX housings
;     sitting exactly on XP1 and XP2 - refdes, a STEP model, no BOM line.
procedure( s3dIsMechanical( o_sym )
    let( ( kind cls comp )
        kind = nil
        cls = nil
        comp = nil
        errset( kind = o_sym->type )
        errset( comp = o_sym->component )
        errset( cls = o_sym->component->compdef->class )
        !comp ||
        (stringp( kind ) && (upperCase( kind ) == "MECHANICAL")) ||
        (stringp( cls ) && (upperCase( cls ) == "MECHANICAL"))
    )
)

; How well the parsed variant table fits THIS board - said out loud, once.
;
; Round 6 caught the Variants.lst that parses into ZERO variants. Two more ways
; the same mistake arrives parse perfectly and then quietly export the whole
; board under variant names, which is indistinguishable from variants working:
;
;   * a STUB - one variant, usually called "dummy", whose base list is empty.
;     It installs nothing, so under the current rule every part with a refdes is
;     dropped and the variant file holds only the symbols that have none.
;     Several projects on this disk carry exactly that file.
;   * a file belonging to a DIFFERENT project: plenty of refdes, none of which
;     exists on this board. Same outcome, and more convincing still, because
;     the variant names look real.
;
; The rule the export follows - "the list governs every part that has a refdes;
; a symbol without one is outside it" - does not change here. This only names
; what is about to happen.
;
; Returns t to go on, and raises for the foreign file: a board exported under
; another project's variant names is worse than no export at all, because
; nothing downstream can tell. The stub is no longer refused (2026-09-03):
; a variant that installs nothing is also the deliberate bare-board export,
; and the file cannot say which - so it is named, loudly, and written.
procedure( s3dVariantFit( g_variantSymbolList t_path )
    prog( ( known nKnown nBoard onBoard refdes examples )
        known = s3dVariantKnownRefdes( g_variantSymbolList )
        nKnown = 0
        examples = nil
        foreach( key known
            nKnown = nKnown + 1
            when( length( examples ) < 5  examples = cons( key examples ) )
        )

        nBoard = 0
        onBoard = 0
        foreach( sym axlDBGetDesign()->symbols
            refdes = sym->refdes
            when( refdes
                nBoard = nBoard + 1
                when( known[upperCase( refdes )]  onBoard = onBoard + 1 )
            )
        )

        ; A warning, not an error, since 2026-09-03: a variant that installs
        ; nothing is how the schematic asks for the BARE BOARD - every part set
        ; to "not installed" in Capture's variant - and that export is wanted.
        ; It is also what a stub Variants.lst (one empty "dummy" variant,
        ; copied from project to project) produces, and nothing in the file
        ; tells the two apart; so this says exactly what is about to be
        ; written, in the console's warning colour, and goes on. The foreign
        ; file below stays an error: it carries the evidence.
        when( nKnown == 0
            s3dWarn( sprintf( nil "Simple 3D: %s installs no components - every variant in it is the bare board." t_path ) )
            printf( "Simple 3D: the variant file(s) will hold the outline, the silkscreen and the\n" )
            printf( "  symbols that have no refdes, and nothing else. That is right when every\n" )
            printf( "  part was set to not installed in the schematic. If this is a stub\n" )
            printf( "  Variants.lst (one empty \"dummy\" variant) left from another project,\n" )
            printf( "  delete it to export every component.\n" )
            return( t )
        )

        when( (nBoard > 0) && (onBoard == 0)
            error( strcat(
                sprintf( nil "Simple 3D: %s does not describe this board.\n" t_path )
                sprintf( nil "None of the %d component(s) it lists is placed here, and %d are.\n"
                         nKnown nBoard )
                sprintf( nil "It lists, for example: %L\n" reverse( examples ) )
                "That file belongs to a different project. Exporting with it would\n"
                "install none of this board's components, writing one STRIPPED\n"
                "board per variant name, which nothing downstream could tell from\n"
                "a real set of variants.\n"
                "Replace it with this board's own Variants.lst, or delete it to\n"
                "export everything once, without variants.\n" ) )
        )

        printf( "Simple 3D: variant list covers %d of %d placed component(s).\n"
                onBoard nBoard )
        t
    )
)

; The symbol dbids to export for one variant (or for the whole design when
; there is no variant table). Returns dbids, not names: iterating the design
; already has the symbol in hand, so nothing has to be looked up again by
; refdes - which is one less way for a symbol to go missing.
; g_state, when given, receives what this variant had to say about itself
; in its 'warnings slot (2026-09-03) - the writer puts those lines in the
; file, and the window's log repeats them.
procedure( s3dSymbolsToExport( g_variantSymbolList t_variant @optional ( g_state nil ) )
    let( ( out installed refdes label key missing shown message ( n 0 ) ( nMissing 0 )
           ( nNoExport 0 ) ( nNotInVariant 0 ) ( nUntracked 0 ) ( nAlways 0 ) )
        out = tconc( nil nil )
        ; Only what THIS variant installs is needed now. The union over all
        ; variants (s3dVariantKnownRefdes) is still built, once, by
        ; s3dVariantFit - to judge whether the file describes this board at all.
        installed = makeTable( "s3dInstalled" nil )
        when( g_variantSymbolList && t_variant
            foreach( refdes g_variantSymbolList[t_variant]
                when( s3dIsRefdesToken( refdes )
                    installed[upperCase( refdes )] = t
                )
            )
        )

        foreach( sym axlDBGetDesign()->symbols
            refdes = sym->refdes
            ; Met on the board: the entry turns from t to 'placed, so what is
            ; still t after the loop is a refdes the variant names and the
            ; board does not have (2026-09-03). Both are truthy, so the tests
            ; below read as before.
            when( refdes && installed[upperCase( refdes )]
                installed[upperCase( refdes )] = 'placed
            )
            ; Admit a symbol that has a refdes (a placed component) OR one that
            ; carries a STEP model but no refdes (a mechanical part, e.g. a
            ; CR2032 holder). Short-circuit keeps the extra axlStepGet probe off
            ; the refdes-bearing symbols, so their path is unchanged.
            when( refdes || s3dHasStepModel( sym )
                cond(
                    ( s3dNoStepExport( sym )
                        nNoExport = nNoExport + 1
                        ; %s on nil throws ("format spec. incompatible with
                        ; data"), which would kill the whole export from inside
                        ; a message. sym->name is documented as a string, but
                        ; this branch exists precisely for symbols in unusual
                        ; states - and symbolReturn3DElements already guards the
                        ; same read the same way.
                        label = if( refdes then
                                    refdes
                                else
                                    if( sym->name then sym->name else "(unnamed symbol)" ) )
                        printf( "Simple 3D: %s - NOT exported: the symbol carries the %s property.\n"
                                label S3D_NoExportProp )
                    )
                    ; With a variant table, ANYTHING THAT HAS A REFDES is
                    ; exported only if this variant installs it - mechanical or
                    ; not. Absence from the list is the list saying "not
                    ; installed", and a refdes is exactly what makes a part
                    ; nameable in the list at all.
                    ;
                    ; Two earlier rules stood here (user decision, 2026-08-03):
                    ; "the variant list IS the export list" lost mechanical
                    ; parts; "subtract only what the table mentions somewhere"
                    ; kept R3 in every variant; and "subtract only what is not
                    ; s3dIsMechanical" kept a MECHANICAL-class part with a
                    ; refdes - A1/A2/A4, MOLEX housings - in variants that do
                    ; not install it. The distinction is now the one the data
                    ; actually carries: a refdes can be listed, so the list
                    ; governs it; a symbol without one never can be, so nothing
                    ; but NO_STEP_EXPORT governs it. See s3dIsMechanical, which
                    ; remains for the probe and no longer decides an export.
                    ;
                    ; t_variant is tested for the same reason `installed` is
                    ; built under it: a table with no variant named fills nothing
                    ; in, and under this rule that would drop EVERY component
                    ; rather than a few. No caller does it - both do exist, so
                    ; the guard costs one comparison and removes a silent one.
                    ;
                    ; ALWAYS_STEP_EXPORT is the one way out, and it is tested
                    ; LAST so that it cannot rescue a symbol NO_STEP_EXPORT has
                    ; already excluded: "never" outranks "always". It is also
                    ; the only test here that costs a property read per symbol,
                    ; and the && chain reaches it only for a part the variant
                    ; was about to drop.
                    ( g_variantSymbolList && t_variant && refdes &&
                      !installed[upperCase( refdes )] &&
                      !s3dAlwaysStepExport( sym )
                        nNotInVariant = nNotInVariant + 1
                    )
                    ( t
                        when( g_variantSymbolList && !refdes
                            nUntracked = nUntracked + 1
                        )
                        when( g_variantSymbolList && refdes &&
                              !installed[upperCase( refdes )]
                            nAlways = nAlways + 1
                        )
                        tconc( out sym )
                    )
                )
            )
        )

        ; The variant names components the board does not have. The list
        ; comes from the schematic and the board from Allegro, and a refdes
        ; in one and not the other is a revision mismatch worth a line - the
        ; export used to say nothing, and the coverage line ("covers 1 of
        ; 48") counts from the board's side only. Said in the console, in
        ; its warning colour, and handed to the file so the window's log
        ; repeats it (2026-09-03; found with a list of six, one placed).
        missing = nil
        foreach( key installed
            when( eq( installed[key] t )  missing = cons( key missing ) )
        )
        when( missing
            missing = sort( missing 'alphalessp )
            nMissing = length( missing )
            ; the first ten by name; a list of hundreds is its own message
            shown = nil
            n = 0
            foreach( key missing
                when( n < 10
                    shown = cons( key shown )
                    n = n + 1
                )
            )
            message = sprintf( nil "variant %s lists %d component(s) that are not on this board: %s%s"
                               t_variant nMissing
                               buildString( reverse( shown ) ", " )
                               if( nMissing > 10 then
                                   sprintf( nil " and %d more" difference( nMissing 10 ) )
                               else
                                   "" ) )
            s3dWarn( strcat( "Simple 3D: " message ) )
            when( g_state
                g_state['warnings] = cons( message g_state['warnings] )
            )
        )

        when( nNoExport > 0
            printf( "Simple 3D: %d symbol(s) excluded by %s.\n" nNoExport S3D_NoExportProp )
        )
        when( nNotInVariant > 0
            printf( "Simple 3D: %d component(s) not installed in variant %s.\n"
                    nNotInVariant t_variant )
        )
        when( nUntracked > 0
            printf( "Simple 3D: %d symbol(s) have no refdes and cannot be named in a variant; exported in every variant.\n"
                    nUntracked )
        )
        when( nAlways > 0
            printf( "Simple 3D: %d component(s) not installed in variant %s but kept by %s.\n"
                    nAlways t_variant S3D_AlwaysExportProp )
        )
        cdr( car( out ) )
    )
)

; Pre-flight check for the Simple 3D menu. Returns
;   ( refDesWithoutMfrPn  refDesWithoutStepModel ).
; Only components that would be exported (refdes + STEP mapping) are checked.
procedure( s3dCheckMfrPn()
    let( ( noMfrPn noModel sym comp mapping )
        noMfrPn = tconc( nil nil )
        noModel = tconc( nil nil )
        foreach( sym axlDBGetDesign()->symbols
            ; Symbols excluded on purpose must not be reported as missing a 3D
            ; model - that list is for parts that WOULD be exported if they had
            ; one, and padding it with deliberate exclusions makes it useless.
            when( sym->refdes && !s3dNoStepExport( sym )
                mapping = nil
                errset( mapping = axlStepGet( nil nil sym ) )
                if( mapping && mapping->step_name then
                    ; MFRPN check DISABLED (property attachment unreliable);
                    ; kept for future - restore the two lines below to re-enable:
                    ; comp = sym->component
                    ; unless( s3dGetMfrPn( comp )  tconc( noMfrPn sym->refdes ) )
                    t
                else
                    tconc( noModel sym->refdes )
                )
            )
        )
        list( cdr( car( noMfrPn ) ) cdr( car( noModel ) ) )
    )
)

;=====================================================================
;  ORIGINAL SCRIPT (with the inline fixes noted in the header)
;=====================================================================

procedure( gdsysGetVariantInfo()
    ; FIX (simple3d): beside the BOARD, not in Allegro's working directory.
    ; See s3dVariantFilePath.
    let(    (   ( variantFile s3dVariantFilePath() )
            ( state "findVariant" )
            pattern inPort currentVariant variantTable alternateParts part partProperties refDes symbols
            ; Declared since round 75 (plan D2): SKILL is dynamically scoped, so
            ; a name assigned here without a declaration became a session
            ; global - tools/skill_checks.py check #5 reports such a name now.
            newLine newLineEnd newLineWithinProperty propertyStart propertySeparator blankSpace
            line parts subStrings properties temp valueKey )

        pattern = pcreCompile("[\"\t+\\()]")
        newLine = pcreCompile("\t\t")
        newLineEnd = pcreCompile("\t\t \\)")
        newLineWithinProperty = pcreCompile( "=\"\t\t " )
        propertyStart = pcreCompile( "^\t\t\\(.*" )
        propertySeparator = pcreCompile( "(\" )" )
        blankSpace = pcreCompile( " " )

        inPort = infile( variantFile )

        if( inPort then

            variantTable = makeTable( "variantTable" nil )
            alternateParts = makeTable( "alternateParts" nil )
            parts = makeTable( "parts" nil )
            partProperties = makeTable( "partProperties" nil )

            while( gets( line inPort )

                ; A variant with no (base block. Capture writes none when the
                ; variant installs nothing - every part set to "not installed"
                ; in the schematic, which is how a user asks for the bare board
                ; (2026-09-03):
                ;     (
                ;         ("BOM"
                ;
                ;         )
                ;     )
                ; The machine used to wait for "(base" for the rest of the file,
                ; so the variant was never registered, the table came out empty
                ; and the export refused the file as another project's. The
                ; variant closing - or an alternate-part block opening - before
                ; any (base means the base list is over before it began: an empty
                ; list, and the line itself is then read by the state that knows
                ; it. The (base line is excluded because propertyStart matches
                ; it too.
                when( (state == "awaitStartCondition") && (strcmp( line "\t\t(base\n" ) != 0) &&
                      ((strcmp( line "\t)\n" ) == 0) || pcreMatchp( propertyStart line ))
                    symbols = list()
                    state = "awaitEndCondition"
                )

                case( state
                    (
                        "findVariant"
                        ; parse for \"
                        subStrings = parseString( line "\"" )

                        when( length( subStrings ) == 3
                            currentVariant = nth( 1 subStrings )
                            state = "awaitStartCondition"
                        )
                    )
                    (
                        "awaitStartCondition"
                        when( strcmp( line "\t\t(base\n" ) == 0
                            state = "appendSymbols"
                            symbols = list()
                        )
                    )
                    (
                        "appendSymbols"
                        if( strcmp( line "\t\t)\n" ) == 0 then
                            state = "awaitEndCondition"
                        else
                            ;append symbols to list
                            symbols = nconc( symbols parseString( line ) )
                        )
                    )
                    (
                        "awaitEndCondition"
                        if( strcmp( line "\t)\n" ) == 0 then
                            ;remove ")" in list
                            symbols = remove( ")" symbols )
                            symbols = mapcar( lambda( ( symbol ) pcreReplace( pattern symbol "" 0 ) )  symbols )

                            ; append components to array
                            variantTable[currentVariant] = symbols
                            alternateParts[currentVariant] = parts

                            ; initialize parts (again, clear previous values)
                            parts = makeTable( "parts" nil )

                            state = "findVariant"
                        else
                            ; alternate part properties
                            when( pcreMatchp( propertyStart line )

                                ; find variant specific information
                                subStrings = parseString( line )

                                when( length( subStrings ) > 1
                                    refDes = pcreReplace( pattern nth( 0 subStrings ) "" 0 )

                                    ; substrings without first element (refDes)
                                    properties = buildString( cdr(subStrings) )

                                    temp = pcreReplace( propertySeparator properties "\\\\" 0 )
                                    subStrings = parseString( temp "\\\\" )

                                    ; check, if property information ends in this line
                                    if( strcmp( car(last(subStrings)) ")\n" ) == 0 then

                                        foreach( subString subStrings
                                            ; parse properties
                                            valueKey = parseString( subString "=" )

                                            when( length(valueKey ) == 2
                                                partProperties[nth( 0 valueKey )] = pcreReplace( pattern nth( 1 valueKey ) "" 0 )
                                            )
                                        )

                                        ; set part properties, clear properties
                                        parts[refDes] = partProperties
                                        partProperties = makeTable( "partProperties" nil )

                                        ; append to symbol list
                                        ; FIX (simple3d): was nth( 0 subStrings ),
                                        ; but subStrings was reassigned above to the
                                        ; PROPERTY chunks, so this appended the first
                                        ; property token ("VALUE=12pF") to the variant's
                                        ; symbol list instead of the refdes. Seen on
                                        ; PAG30N/BNO as two
                                        ;   Simple 3D: VALUE=12pF - not found in the design
                                        ; lines. refDes is already correct here - it is
                                        ; what parts[refDes] above is keyed by.
                                        symbols = nconc( symbols list( refDes ) )
                                    else
                                        state = "awaitMoreProperties"
                                    )
                                )
                            )
                        )
                    )
                    (
                        "awaitMoreProperties"
                        ; add more properties

                        ; append line to properties and check
                        ; newLineEnd needs to be replaced by space + ), because the last space is ignore by buildString (...) in previous loop
                        properties = strcat( properties pcreReplace( newLineEnd line " )" 0 ) )
                        properties = pcreReplace( newLineWithinProperty properties "=\"" 0 )
                        properties = pcreReplace( newLine properties "" 0 )
                        temp = pcreReplace( propertySeparator properties "\\\\" 0 )
                        temp = pcreReplace( newLineEnd temp "\\\\" 0 )
                        subStrings = parseString( temp "\\\\" )

                        ; check, if property information ends in this line
                        when( strcmp( car(last(subStrings)) ")\n" ) == 0
                            foreach( subString subStrings

                                ; parse properties
                                valueKey = parseString( subString "=" )

                                when( length(valueKey ) == 2
                                    partProperties[nth( 0 valueKey )] = pcreReplace( blankSpace pcreReplace( pattern cadr( valueKey ) "" 0 ) "" 0 )
                                )
                            )

                            ; set part properties, clear properties
                            parts[refDes] = partProperties
                            partProperties = makeTable( "partProperties" nil )

                            ; append to symbol list
                            ; FIX (simple3d): same bug as in the single-line branch
                            ; above - subStrings holds property chunks by now, not
                            ; the refdes. This is the multi-line-properties path.
                            symbols = nconc( symbols list( refDes ) )

                            properties = ""

                            state = "awaitEndCondition"
                        )
                    )
                    (
                        t
                        warn( "I should not be here ... " )
                    )
                )
            )
            ; Never closed until 2026-09-03: Allegro kept Variants.lst open,
            ; one handle per export, until it exited - and the file could not
            ; be deleted or replaced while the session lived ("permission
            ; denied", seen headless with deleteFile after one export).
            close( inPort )
            list( variantTable alternateParts )
        else
            error( "Can not read from file ... " )
            nil
        )
    )
)
