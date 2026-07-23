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
;    * addIndent() - was called 8x but never defined in the repo; added.
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
;  Variants.lst is present) into outputDir. Design units must be mm.
;  configFile is the silkscreen layer/settings JSON; when omitted,
;  "simple3d_config.json" in the working directory is used if present, and
;  otherwise the built-in defaults apply.
;=====================================================================

; s3dMakeDirs( t_path ) -> create every missing level of a directory path.
; createDir makes only one level at a time; a path like ".../A1/cad" where an
; intermediate level is missing needs each segment created in turn.
; LIMITATION: UNC paths (//server/share/...) are not handled - parseString
; collapses the leading slashes, so the first segment would be created as a
; relative folder. Local drive paths (d:/...) only.
procedure( s3dMakeDirs( t_path )
    let( ( norm parts acc seg )
        ; normalise slashes; parseString drops empty tokens so "d:/a//b" is safe
        norm = buildString( parseString( t_path "\\" ) "/" )
        parts = parseString( norm "/" )
        acc = ""
        foreach( seg parts
            acc = if( acc == "" then seg else strcat( acc "/" seg ) )
            ; skip the bare drive letter "d:" (creating it is meaningless).
            ; A drive token is exactly 2 chars ending in ":".
            unless( (strlen( acc ) == 2) && (substring( acc 2 1 ) == ":")
                unless( isDir( acc )
                    errset( createDir( acc ) )
                )
            )
        )
        isDir( t_path )
    )
)

; addIndent( t_string [ x_levels ] ) -> prefix every line with x_levels tabs.
; Reconstructed from the call sites; output matches the reference demo.json
; byte-for-byte. (The original repo used this but never shipped its source.)
procedure( addIndent( t_string @optional ( x_levels 1 ) )
    let( ( pad lines i )
        pad = ""
        for( i 1 x_levels
            pad = strcat( pad "\t" )
        )
        cond(
            ( !t_string           nil )
            ( !stringp( t_string ) t_string )
            ( t
                lines = parseString( t_string "\n" )
                if( lines then
                    buildString( mapcar( lambda( (line) strcat( pad line ) ) lines ) "\n" )
                else
                    strcat( pad t_string )
                )
            )
        )
    )
)

; --- MFRPN helpers DISABLED (property attachment unreliable; kept for future) ---

; defvar( S3D_MfrPnProp "MFRPN" )

; Case-insensitive property read via axlDBGetProperties. The dictionary
; spelling is whatever the netlist declared (F4 prints MFRPN); match loosely.
; procedure( s3dPropCI( dbid t_name )
;     let( ( props p key val want )
;         val  = nil
;         want = upperCase( t_name )
;         when( dbid
;             errset( props = axlDBGetProperties( dbid ) )
;             when( props
;                 foreach( p props
;                     when( p && listp( p )
;                         key = car( p )
;                         unless( stringp( key ) key = sprintf( nil "%L" key ) )
;                         when( upperCase( key ) == want
;                             val = cdr( p )
;                             when( listp( val ) val = car( val ) )
;                         )
;                     )
;                 )
;             )
;         )
;         when( val && !stringp( val ) val = sprintf( nil "%L" val ) )
;         when( val && val != "" val )
;     )
; )

; MFRPN lives on the component definition (F4: "Properties attached to
; component definition"). An instance-level override, if present, wins.
; procedure( s3dGetMfrPn( comp )
;     let( ( val )
;         val = nil
;         when( comp
;             val = s3dPropCI( comp S3D_MfrPnProp )
;             unless( val
;                 when( comp->compdef  val = s3dPropCI( comp->compdef S3D_MfrPnProp ) )
;             )
;         )
;         val
;     )
; )

; Minimal JSON string escaping for the article number.
; procedure( s3dJsonEscape( t_string )
;     let( ( out c i n )
;         unless( stringp( t_string ) t_string = sprintf( nil "%L" t_string ) )
;         out = ""
;         n = strlen( t_string )
;         for( i 1 n
;             c = substring( t_string i 1 )
;             cond(
;                 ( c == "\""  out = strcat( out "\\\"" ) )
;                 ( c == "\\"  out = strcat( out "\\\\" ) )
;                 ( c == "\t"  out = strcat( out "\\t"  ) )
;                 ( c == "\n"  out = strcat( out "\\n"  ) )
;                 ( t          out = strcat( out c ) )
;             )
;         )
;         out
;     )
; )

;=====================================================================
;  WHAT GETS EXPORTED  (NEW - simple3d)
;
;  Two rules, and the second is the reason this section exists at all.
;
;  1. A symbol carrying NO_STEP_EXPORT is never exported, whatever else says
;     otherwise - including its presence in Variants.lst. Each one is named in
;     the console, because a part silently missing from a 3D model is a bug
;     report waiting to happen and the user has no way to tell "excluded on
;     purpose" from "lost".
;
;  2. The list of symbols to export is built from the DESIGN, not from the
;     parsed Variants.lst. That is a reversal: the variant list used to BE the
;     export list, so anything the parser did not hand back simply vanished -
;     which is what happened to mechanical components (Component Class
;     MECHANICAL: real symbols, real PKGDEF_STEP_FILE, no electrical
;     connections). Now the variant table can only ever REMOVE a symbol, never
;     be the sole source of one, and a refdes the table has never heard of is
;     present in every variant. Mechanical parts are exactly that case, and so
;     is anything else the variant machinery does not track.
;=====================================================================

S3D_NoExportProp = "NO_STEP_EXPORT"

; t if the named property is attached to this object.
;
; Presence is the test, not the value: NO_STEP_EXPORT is a flag with no value,
; so a value-based check would miss it. axlDBGetProperties is used rather than
; the generic ->prop attribute because it hands back a plain assoc list that can
; be walked with a runtime name; property names come back as symbols, hence the
; %L coercion.
procedure( s3dObjectHasProp( o_dbid t_name )
    let( ( props key ( want nil ) ( found nil ) )
        want = upperCase( t_name )
        when( o_dbid
            props = nil
            errset( props = axlDBGetProperties( o_dbid ) )
            foreach( entry props
                when( entry
                    key = if( listp( entry ) then car( entry ) else entry )
                    unless( stringp( key )  key = sprintf( nil "%L" key ) )
                    when( upperCase( key ) == want  found = t )
                )
            )
        )
        found
    )
)

; t if this symbol is marked NO_STEP_EXPORT.
;
; Checked on the symbol instance (where the F4 dump shows it), and also on the
; component and its definition: putting it on a definition to drop every
; instance of a part - every fiducial, say - is the obvious thing to want, and
; costs nothing to support.
procedure( s3dNoStepExport( o_sym )
    let( ( comp )
        comp = nil
        errset( comp = o_sym->component )
        s3dObjectHasProp( o_sym S3D_NoExportProp ) ||
        (comp && s3dObjectHasProp( comp S3D_NoExportProp )) ||
        (comp && comp->compdef && s3dObjectHasProp( comp->compdef S3D_NoExportProp ))
    )
)

; Every refdes the variant table mentions anywhere, upper-cased.
; A refdes in here but missing from the current variant is deliberately not
; installed. A refdes the table never mentions is not variant-controlled at all.
procedure( s3dVariantKnownRefdes( g_variantSymbolList )
    let( ( known )
        known = makeTable( "s3dKnownRefdes" nil )
        when( g_variantSymbolList
            foreach( variant g_variantSymbolList
                foreach( refdes g_variantSymbolList[variant]
                    when( stringp( refdes )  known[upperCase( refdes )] = t )
                )
            )
        )
        known
    )
)

; The symbol dbids to export for one variant (or for the whole design when
; there is no variant table). Returns dbids, not names: iterating the design
; already has the symbol in hand, so nothing has to be looked up again by
; refdes - which is one less way for a symbol to go missing.
procedure( s3dSymbolsToExport( g_variantSymbolList t_variant )
    let( ( out known installed refdes ( nNoExport 0 ) ( nNotInVariant 0 ) ( nUntracked 0 ) )
        out = tconc( nil nil )
        known = s3dVariantKnownRefdes( g_variantSymbolList )
        installed = makeTable( "s3dInstalled" nil )
        when( g_variantSymbolList && t_variant
            foreach( refdes g_variantSymbolList[t_variant]
                when( stringp( refdes )  installed[upperCase( refdes )] = t )
            )
        )

        foreach( sym axlDBGetDesign()->symbols
            refdes = sym->refdes
            when( refdes
                cond(
                    ( s3dNoStepExport( sym )
                        nNoExport = nNoExport + 1
                        printf( "Simple 3D: %s - NOT exported: the symbol carries the %s property.\n"
                                refdes S3D_NoExportProp )
                    )
                    ( g_variantSymbolList && known[upperCase( refdes )] &&
                      !installed[upperCase( refdes )]
                        nNotInVariant = nNotInVariant + 1
                    )
                    ( t
                        unless( g_variantSymbolList && known[upperCase( refdes )]
                            nUntracked = nUntracked + 1
                        )
                        tconc( out sym )
                    )
                )
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
            printf( "Simple 3D: %d symbol(s) are not listed in any variant (mechanical and the like); exported in all of them.\n"
                    nUntracked )
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
    let(    (   ( variantFile "Variants.lst" )
            ( state "findVariant" )
            pattern inPort currentVariant variantTable alternateParts part partProperties refDes symbols )

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
            list( variantTable alternateParts )
        else
            error( "Can not read from file ... " )
            nil
        )
    )
)

procedure( makeLine( segment )
    let( ( extents xStart yStart xEnd yEnd element )
        extents = segment->startEnd

        xStart = caar( extents )
        yStart = cadar( extents )

        xEnd = caadr( extents )
        yEnd = cadadr( extents )

        element = strcat(
            "{\n\t\"type\": \"segment\",\n"
            "\t\"start\": [" sprintf( nil "%f" xStart ) ", " sprintf( nil "%f" yStart ) "],\n"
            "\t\"end\": [" sprintf( nil "%f" xEnd ) ", " sprintf( nil "%f" yEnd ) "]\n"
            "}"
        )
    )
)

procedure( makeArc( segment )
    let( ( xy xCenter yCenter radius extents xStart yStart xEnd yEnd cw ccw angle1 angle2 startAngle endAngle element )
        xy = segment->xy
        xCenter = car( xy )
        yCenter = cadr( xy )

        radius = segment->radius

        extents = segment->startEnd

        xStart = caar( extents )
        yStart = cadar( extents )

        xEnd = caadr( extents )
        yEnd = cadadr( extents )

        cw = segment->isClockwise

        if(cw then
            ccw = "false"
        else
            ccw = "true"
        )

        angle1 =  axlRadToDeg( atan2( ( yStart - yCenter ), ( xStart - xCenter ) ) )

        ; convert to positive angle
        when( negativep( angle1 )
            angle1 = angle1 + 360
        )

        angle2 = axlRadToDeg( atan2( ( yEnd - yCenter ), ( xEnd - xCenter ) ) )

        ; convert to positive angle
        when( negativep( angle2 )
            angle2 = angle2 + 360
        )

        if( cw then
            startAngle = angle2
            endAngle = angle1
        else
            startAngle = angle1
            endAngle = angle2
        )

        element = strcat(
            "{\n\t\"type\": \"arc\",\n"
            "\t\"center\": [" sprintf( nil "%f" xCenter ) ", " sprintf( nil "%f" yCenter ) "],\n"
            "\t\"radius\": " sprintf( nil "%f" radius ) ",\n"
            "\t\"alpha\": " sprintf( nil "%f" startAngle ) ",\n"
            "\t\"beta\": " sprintf( nil "%f" endAngle ) ",\n"
            "\t\"ccw\": " ccw "\n"
            "}"
        )
    )
)

procedure( makeCircle( xy diameter )
    let( ( element )
        element = strcat(
            "{\n\t\"type\": \"circle\",\n"
            "\t\"x\": " sprintf( nil "%f" xCoord( xy ) ) ",\n"
            "\t\"y\": " sprintf( nil "%f" yCoord( xy ) ) ",\n"
            "\t\"radius\": " sprintf( nil "%f" diameter/2 ) "\n"
            "}"
        )
    )
)

procedure( rotateXY( origin xy angle )
    let( ( angleRad dX dY dXY x y )
        angleRad = axlDegToRad( angle )
        dX = xCoord( xy ) - xCoord( origin )
        dY = yCoord( xy ) - yCoord( origin )
        dXY = list( dX dY )

        x = xCoord( origin ) + xCoord( dXY ) * cos( angleRad ) - yCoord( dXY ) * sin( angleRad )
        y = yCoord( origin ) + xCoord( dXY ) * sin( angleRad ) + yCoord( dXY ) * cos( angleRad )

        list( x y )
    )
)

procedure( makeSlot( pin padstack )
    let( ( xy x y rotation drillOffset xDrillOffset yDrillOffset drillSizeWidth drillSizeHeight slot radius xCenter yCenter xyCenter alpha beta ccw segment )
        ; get coordinates
        xy = pin->xy
        x = xCoord( xy )
        y = yCoord( xy )
        rotation = pin->rotation

        drillOffset = padstack->drillOffset
        xDrillOffset = xCoord( drillOffset) + x
        yDrillOffset = yCoord( drillOffset) + y

        ; calculate origin (drilloffset)
        xy = rotateXY( list( x y ) list( xDrillOffset yDrillOffset ) rotation )
        x = xCoord( xy )
        y = yCoord( xy )

        drillSizeWidth = padstack->drillSizeWidth
        drillSizeHeight = padstack->drillSizeHeight

        ; if slot is actually a hole
        if( drillSizeWidth == drillSizeHeight then
            ; FIX (simple3d): makeCircle takes (xy diameter), not (x y d).
            slot = makeCircle( list( x y ) drillSizeWidth )
        else
            ; default state is drillSizeWidth < drillSizeHeight
            ; otherwise swap both and add 90 deg rotation
            unless( drillSizeHeight >= drillSizeWidth
                tmp = drillSizeWidth
                drillSizeWidth = drillSizeHeight
                drillSizeHeight = tmp
                rotation = rotation + 90.0
            )

            ; calculate radius
            radius = drillSizeWidth / 2

            ; make first half circle
            xCenter = x
            yCenter = y + ( drillSizeHeight - drillSizeWidth ) / 2

            ; apply rotation
            xyCenter = rotateXY( xy list( xCenter yCenter ) rotation )
            xCenter = xCoord( xyCenter )
            yCenter = yCoord( xyCenter )

            ; calculate angles
            alpha = 0.0 + rotation
            beta = 180.0 + rotation
            alpha = modf( alpha 360.0 )
            beta = modf( beta 360.0 )
            ccw = "false"

            segment = strcat(
                "{\n\t\"type\": \"arc\",\n"
                "\t\"center\": [" sprintf( nil "%f" xCenter ) ", " sprintf( nil "%f" yCenter ) "],\n"
                "\t\"radius\": " sprintf( nil "%f" radius ) ",\n"
                "\t\"alpha\": " sprintf( nil "%f" alpha ) ",\n"
                "\t\"beta\": " sprintf( nil "%f" beta ) ",\n"
                "\t\"ccw\": " ccw "\n"
                "}"
            )

            slot = tconc( nil segment )

            ; make first line
            xStart = x - radius
            yStart = y + ( drillSizeHeight - drillSizeWidth ) / 2

            xEnd = x - radius
            yEnd = y - ( drillSizeHeight - drillSizeWidth ) / 2

            ; apply rotation
            xyStart = rotateXY( xy list( xStart yStart ) rotation )
            xStart = xCoord( xyStart )
            yStart = yCoord( xyStart )

            xyEnd = rotateXY( xy list( xEnd yEnd ) rotation )
            xEnd = xCoord( xyEnd )
            yEnd = yCoord( xyEnd )

            segment = strcat(
                "{\n\t\"type\": \"segment\",\n"
                "\t\"start\": [" sprintf( nil "%f" xStart ) ", " sprintf( nil "%f" yStart ) "],\n"
                "\t\"end\": [" sprintf( nil "%f" xEnd ) ", " sprintf( nil "%f" yEnd ) "]\n"
                "}"
            )

            tconc( slot segment )

            ; make last half circle
            xCenter = x
            yCenter = y - ( drillSizeHeight - drillSizeWidth ) / 2

            ; apply rotation
            xyCenter = rotateXY( xy list( xCenter yCenter ) rotation )
            xCenter = xCoord( xyCenter )
            yCenter = yCoord( xyCenter )

            ; calculate angles
            alpha = 180.0 + rotation
            beta = 360.0 + rotation
            alpha = modf( alpha 360.0 )
            beta = modf( beta 360.0 )
            ccw = "true"

            segment = strcat(
                "{\n\t\"type\": \"arc\",\n"
                "\t\"center\": [" sprintf( nil "%f" xCenter ) ", " sprintf( nil "%f" yCenter ) "],\n"
                "\t\"radius\": " sprintf( nil "%f" radius ) ",\n"
                "\t\"alpha\": " sprintf( nil "%f" alpha ) ",\n"
                "\t\"beta\": " sprintf( nil "%f" beta ) ",\n"
                "\t\"ccw\": " ccw "\n"
                "}"
            )

            tconc( slot segment )

            ; make last line
            xStart = x + radius
            yStart = y - ( drillSizeHeight - drillSizeWidth ) / 2

            xEnd = x + radius
            yEnd = y + ( drillSizeHeight - drillSizeWidth ) / 2

            ; apply rotation
            xyStart = rotateXY( xy list( xStart yStart ) rotation )
            xStart = xCoord( xyStart )
            yStart = yCoord( xyStart )

            xyEnd = rotateXY( xy list( xEnd yEnd ) rotation )
            xEnd = xCoord( xyEnd )
            yEnd = yCoord( xyEnd )

            segment = strcat(
                "{\n\t\"type\": \"segment\",\n"
                "\t\"start\": [" sprintf( nil "%f" xStart ) ", " sprintf( nil "%f" yStart ) "],\n"
                "\t\"end\": [" sprintf( nil "%f" xEnd ) ", " sprintf( nil "%f" yEnd ) "]\n"
                "}"
            )

            tconc( slot segment )
        )
        ; return slot
        car( slot )
    )
)

procedure( boardGeometryParseSegment( segment )
    let( ( element )
        case( segment->objType
            (
                "line"
                element = makeLine( segment )
            )
            (
                "arc"
                if( segment->isCircle then
                    element = makeCircle( segment->xy 2*segment->radius )
                else
                    element = makeArc( segment )
                )
            )
            (
                t
                warn( "Unknown segment ...\n")
            )
        )
        element
    )
)

procedure( calculateBoardThickness()
    ; FIX (simple3d): SILKSCREEN_* and PASTEMASK_* are ALSO layerType "MASK"
    ; (verified on a real board), so the original
    ;     if name == "SOLDERMASK_TOP" then top else bottom
    ; put silkscreen into the bottom mask and, using plain "=", let each later
    ; MASK layer overwrite the previous one. Now: only SOLDERMASK layers count,
    ; classified top/bottom by cross-section position relative to the outermost
    ; conductor (so a renamed mask still lands correctly). Dielectric pseudo-
    ; layers have name = nil, hence the guard.
    ;
    ; NOTE (simple3d): this sums a SINGLE stackup. Multi-stackup / rigid-flex
    ; designs (more than one stackup zone) are NOT supported - the whole board
    ; is exported with this one averaged thickness. See the README limitation.
    let( ( stackup padToPadThickness topSoldermaskThickness bottomSoldermaskThickness
           topCondPos nm thk )
        stackup = axlXSectionGet( nil 'all )
        padToPadThickness = 0.0
        topSoldermaskThickness = 0.0
        bottomSoldermaskThickness = 0.0
        topCondPos = nil

        ; first conductor/plane from the top gives the reference position
        foreach( layer stackup
            case( layer->layerType
                ( ( "CONDUCTOR" "PLANE" )
                    unless( topCondPos  topCondPos = layer->position )
                )
                ( t nil )
            )
        )

        foreach( layer stackup
            thk = layer->thickness
            unless( thk  thk = 0.0 )
            case( layer->layerType
                ( ( "CONDUCTOR" "DIELECTRIC" "PLANE" )
                    padToPadThickness = padToPadThickness + thk
                )
                ( ( "MASK" )
                    nm = if( layer->name then upperCase( layer->name ) else "" )
                    when( substring( nm 1 10 ) == "SOLDERMASK"
                        if( topCondPos && layer->position && (layer->position < topCondPos) then
                            topSoldermaskThickness = topSoldermaskThickness + thk
                        else
                            bottomSoldermaskThickness = bottomSoldermaskThickness + thk
                        )
                    )
                )
                ( t nil )
            )
        )
        list( topSoldermaskThickness padToPadThickness bottomSoldermaskThickness )
    )
)

procedure( makePcbContour( dsn )
    let( ( outline segments ( edges 'unbound ) ( cut 'unbound ) ( cuts 'unbound ) )
        ; make pcb geometry
        outline = dsn->designOutline
        segments = outline->segments

        foreach( segment segments
            ; parse segment
            element = boardGeometryParseSegment( segment )

            if( boundp( 'edges ) then
                tconc( edges element )
            else
                edges = tconc( nil element )
            )
        )

        ; make cutouts
        cutouts = axlDBGetShapes( "BOARD GEOMETRY/CUTOUT" )

        when( cutouts
            foreach( cutout cutouts
                segments = cutout->segments

                foreach( segment segments
                    ; parse segment
                    element = boardGeometryParseSegment( segment )

                    if( boundp( 'cut ) then
                        tconc( cut element )
                    else
                        cut = tconc( nil element )
                    )
                )

                cut = buildString( car( cut ) ",\n" )
                cut = strcat(
                    "[\n"
                    addIndent( cut )
                    "\n]"
                )

                if( boundp( 'cuts ) then
                    tconc( cuts cut )
                else
                    cuts = tconc( nil cut )
                )

                cut = 'unbound
            )
        )

        unless( boundp( 'cuts )
            cuts = nil
        )

        ; FIX (simple3d 2026-07-22): cuts was guarded here but edges was not,
        ; so a design whose outline yields no segments faulted on this very
        ; line instead of reporting an empty outline. Same fault class as the
        ; unbound `cuts` at the makePcb call site.
        unless( boundp( 'edges )
            printf( "Simple 3D: warning - the design outline produced no segments.\n" )
            edges = nil
        )

        ; return
        list( edges cuts )
    )
)

; FIX (simple3d 2026-07-22): takes the SYMBOL dbid, not a refdes string.
;
; It used to take a name and resolve it with axlDBFindByName( 'refdes ... ),
; which returns a component instance, whose ->symbol is then the symbol. Two
; lookups that can each come back empty, for a symbol the caller was already
; holding. Callers now iterate the design, so the dbid is passed straight
; through and refdes is read off it. A string is still accepted, because it
; costs three lines and keeps the old call shape working.
procedure( symbolReturn3DElements( g_symbol )
    let( ( stepPackageMapping refDes dbid sym mappingData stepFileName offset_x offset_y offset_z rotation_x rotation_y rotation_z isMirrored xy angle hole mfrPn ( holes 'unbound ) )

        stepPackageMapping = nil

        if( stringp( g_symbol ) then
            refDes = g_symbol
            dbid = axlDBFindByName( 'refdes refDes )
            sym = dbid->symbol
        else
            sym = g_symbol
            refDes = sym->refdes
            unless( stringp( refDes )  refDes = sprintf( nil "%L" refDes ) )
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

        ; set step package mapping
        when( stepFileName
            stepPackageMapping = strcat(
                "\"" sprintf( nil "%s" refDes ) "\": {\n"
                "\t\"step_mapping\": {\n"
                "\t\t\"step_name\": \"" sprintf( nil "%s" stepFileName ) "\",\n"
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

procedure( symbolReturnPinHoles()
    let( ( symbols sym hole padstack xy element ( holes 'unbound ) )
        symbols = axlDBGetDesign()->symbols

        foreach( sym symbols
            ; export pin holes
            foreach( pin sym->pins
                when( pin->isThrough
                    ; reset hole
                    hole = nil

                    ; retrieve padstack information
                    padstack = axlLoadPadstack( pin->name )

                    ; get position
                    xy = pin->xy

                    if( padstack->usage == "Slot" then
                        element = makeSlot( pin padstack )

                        hole = strcat(
                            "[\n"
                                addIndent( buildString( element ",\n" ) )
                            "\n]"
                        )
                    else
                        ; make a simple drill hole
                        hole = makeCircle( xy padstack->drillDiameter )

                        hole = strcat(
                            "[\n"
                                addIndent( hole )
                            "\n]"
                        )
                    )

                    when( hole
                        if( boundp( 'holes ) then
                            tconc( holes hole )
                        else
                            holes = tconc( nil hole )
                        )
                    )
                )
            )
        )

        if( boundp( 'holes ) then
            holes = car( holes )
            holes = buildString( holes ",\n" )
        else
            holes = nil
        )

        ; return holes
        holes
    )
)

procedure( makePcb( thicknesses edges cuts color )
    let( ()
        pcbColor = strcat(
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
        if( cuts then
            edges = strcat(
                "\"pcb\": {\n"
                "\t\"thickness\": {\n"
                "\t\t\"soldermask_top\": " sprintf( nil "%f" car( thicknesses ) ) ",\n"
                "\t\t\"board\": " sprintf( nil "%f" cadr( thicknesses ) ) ",\n"
                "\t\t\"soldermask_bottom\": " sprintf( nil "%f" caddr( thicknesses ) ) "\n"
                "\t},\n"
                addIndent(
                    pcbColor
                )
                ",\n"
                "\t\"edges\": [\n"
                "\t\t[\n"
                addIndent(
                    buildString( car( edges ) ",\n" ),
                    3
                )
                "\n\t\t],\n"
                addIndent(
                    buildString( car( cuts ) ",\n" ),
                    2
                )
                "\n\t]\n}"
            )

        else
            ; FIX (simple3d): the original emitted  "thickness": 1.67  as a bare
            ; scalar here (reached on a board with no cutouts and no through
            ; pins, when 'cuts stays unbound), which the reader rejects. Emit
            ; the real thickness object, same as the other branch.
            edges = strcat(
                "\"pcb\": {\n"
                "\t\"thickness\": {\n"
                "\t\t\"soldermask_top\": " sprintf( nil "%f" car( thicknesses ) ) ",\n"
                "\t\t\"board\": " sprintf( nil "%f" cadr( thicknesses ) ) ",\n"
                "\t\t\"soldermask_bottom\": " sprintf( nil "%f" caddr( thicknesses ) ) "\n"
                "\t},\n"
                addIndent( 
                    pcbColor
                )
                ",\n"
                "\t\"edges\": [\n"
                "\t\t[\n"
                addIndent(
                    buildString( car( edges ) ",\n" ),
                    3
                )
                "\n\t\t]\n\t]\n}"
            )
        )
    )
)

;=====================================================================
;  SILKSCREEN  (NEW - simple3d)
;
;  Exports the silkscreen as filled regions so the Python side can extrude
;  them into thin solids sitting on the board faces.
;
;  The whole "line + width -> filled outline" problem is handed to Allegro:
;  axlPolyFromDB turns any line/cline/shape/rect dbid into o_polygon objects
;  with the width already applied and the requested end caps, and
;  axlText2Lines + axlPolyFromDB(?line2poly t) does the same for text (this is
;  the idiom the axlText2Lines documentation itself recommends). Nothing here
;  offsets or strokes geometry by hand.
;
;  Each polygon is written out in the SAME primitive vocabulary the board
;  outline already uses (segment / arc / circle), so the Python reader needs no
;  new geometry parser - build_contour() handles both.
;
;  VARIANTS: silkscreen is deliberately variant-INDEPENDENT. The bare board is
;  manufactured once for every assembly variant, so the printed legend of a
;  component that is not installed in a given variant is still physically on
;  the board. It is therefore collected once per design, not per variant.
;=====================================================================

; Built-in defaults, used when no config file is found (or it fails to parse).
; Mirrors simple3d_config.json - keep the two in step.
S3D_SilkDefaultTop = list(
    "BOARD GEOMETRY/SILKSCREEN_TOP"
    "PACKAGE GEOMETRY/SILKSCREEN_TOP"
    "REF DES/SILKSCREEN_TOP"
    "COMPONENT VALUE/SILKSCREEN_TOP"
)
S3D_SilkDefaultBottom = list(
    "BOARD GEOMETRY/SILKSCREEN_BOTTOM"
    "PACKAGE GEOMETRY/SILKSCREEN_BOTTOM"
    "REF DES/SILKSCREEN_BOTTOM"
    "COMPONENT VALUE/SILKSCREEN_BOTTOM"
)
; Ink thickness in mm. 25 um is a typical cured screen-printed legend.
S3D_SilkDefaultThickness = 0.025

;---------------------------------------------------------------------
;  A small JSON reader, so the layer list lives in an editable file
;  instead of in the source (same idea as exportJson's config.json).
;
;  Purely functional: every parse step returns  list( value nextIndex )  and
;  nothing is mutated, which avoids needing a by-reference cursor. Handles the
;  JSON subset a config file needs: objects, arrays, strings (with escapes),
;  numbers, true/false/null. \uXXXX is consumed but not decoded (a layer name
;  is ASCII).
;
;  Parsed shape:  object -> ( 'jobj ((key value) ...) )
;                 array  -> ( 'jarr (value ...) )
;---------------------------------------------------------------------

; Characters a JSON number may be built from. A list + member() rather than a
; string + index(): member on strings is used elsewhere in this toolchain and
; is known to work here, whereas index() is a core-SKILL string function that
; the Allegro API reference does not carry - not worth betting the config
; reader on.
S3D_JsonNumChars = list( "0" "1" "2" "3" "4" "5" "6" "7" "8" "9"
                         "+" "-" "." "e" "E" )

procedure( s3dJsonSlurp( t_file )
    let( ( port line out )
        out = ""
        port = infile( t_file )
        when( port
            while( gets( line port )
                out = strcat( out line )
            )
            close( port )
            out
        )
    )
)

; Skip whitespace, return the new index.
procedure( s3dJsonWs( t_txt x_i )
    let( ( n c ( go t ) )
        n = strlen( t_txt )
        while( go && (x_i <= n)
            c = substring( t_txt x_i 1 )
            if( (c == " ") || (c == "\t") || (c == "\n") || (c == "\r") then
                x_i = x_i + 1
            else
                go = nil
            )
        )
        x_i
    )
)

; x_i points at the opening quote. -> list( t_string nextIndex )
procedure( s3dJsonStr( t_txt x_i )
    let( ( n c out ( go t ) )
        n = strlen( t_txt )
        out = ""
        x_i = x_i + 1
        while( go && (x_i <= n)
            c = substring( t_txt x_i 1 )
            cond(
                ( c == "\""
                    x_i = x_i + 1
                    go = nil
                )
                ( c == "\\"
                    x_i = x_i + 1
                    c = if( x_i <= n then substring( t_txt x_i 1 ) else "" )
                    cond(
                        ( c == "n"  out = strcat( out "\n" ) )
                        ( c == "t"  out = strcat( out "\t" ) )
                        ( c == "r"  out = strcat( out "\r" ) )
                        ( c == "b"  t )
                        ( c == "f"  t )
                        ( c == "u"  x_i = x_i + 4 )
                        ( t         out = strcat( out c ) )
                    )
                    x_i = x_i + 1
                )
                ( t
                    out = strcat( out c )
                    x_i = x_i + 1
                )
            )
        )
        list( out x_i )
    )
)

; -> list( f_number nextIndex )
procedure( s3dJsonNum( t_txt x_i )
    let( ( n c start ( go t ) )
        n = strlen( t_txt )
        start = x_i
        while( go && (x_i <= n)
            c = substring( t_txt x_i 1 )
            if( member( c S3D_JsonNumChars ) then
                x_i = x_i + 1
            else
                go = nil
            )
        )
        if( x_i > start then
            list( atof( substring( t_txt start x_i - start ) ) x_i )
        else
            ; not a number at all - step over the offending character so the
            ; caller cannot spin forever on malformed input.
            list( nil x_i + 1 )
        )
    )
)

; -> list( value nextIndex )
procedure( s3dJsonVal( t_txt x_i )
    let( ( c n )
        n = strlen( t_txt )
        x_i = s3dJsonWs( t_txt x_i )
        c = if( x_i <= n then substring( t_txt x_i 1 ) else "" )
        cond(
            ( c == "{"   s3dJsonObj( t_txt x_i ) )
            ( c == "["   s3dJsonArr( t_txt x_i ) )
            ( c == "\""  s3dJsonStr( t_txt x_i ) )
            ( (x_i + 3 <= n) && (substring( t_txt x_i 4 ) == "true")   list( t x_i + 4 ) )
            ( (x_i + 4 <= n) && (substring( t_txt x_i 5 ) == "false")  list( nil x_i + 5 ) )
            ( (x_i + 3 <= n) && (substring( t_txt x_i 4 ) == "null")   list( nil x_i + 4 ) )
            ( t  s3dJsonNum( t_txt x_i ) )
        )
    )
)

; x_i points at "{". -> list( ( 'jobj alist ) nextIndex )
procedure( s3dJsonObj( t_txt x_i )
    let( ( n c key res out ( go t ) )
        n = strlen( t_txt )
        x_i = x_i + 1
        out = nil
        while( go
            x_i = s3dJsonWs( t_txt x_i )
            c = if( x_i <= n then substring( t_txt x_i 1 ) else "" )
            cond(
                ( c == "}"  x_i = x_i + 1  go = nil )
                ( c == ","  x_i = x_i + 1 )
                ( c == "\""
                    res = s3dJsonStr( t_txt x_i )
                    key = car( res )
                    x_i = s3dJsonWs( t_txt cadr( res ) )
                    when( (x_i <= n) && (substring( t_txt x_i 1 ) == ":")
                        x_i = x_i + 1
                    )
                    res = s3dJsonVal( t_txt x_i )
                    x_i = cadr( res )
                    out = cons( list( key car( res ) ) out )
                )
                ( t  go = nil )        ; malformed or end of input
            )
        )
        list( list( 'jobj reverse( out ) ) x_i )
    )
)

; x_i points at "[". -> list( ( 'jarr elements ) nextIndex )
procedure( s3dJsonArr( t_txt x_i )
    let( ( n c res out ( go t ) )
        n = strlen( t_txt )
        x_i = x_i + 1
        out = nil
        while( go
            x_i = s3dJsonWs( t_txt x_i )
            c = if( x_i <= n then substring( t_txt x_i 1 ) else "" )
            cond(
                ( c == "]"  x_i = x_i + 1  go = nil )
                ( c == ","  x_i = x_i + 1 )
                ( c == ""   go = nil )
                ( t
                    res = s3dJsonVal( t_txt x_i )
                    x_i = cadr( res )
                    out = cons( car( res ) out )
                )
            )
        )
        list( list( 'jarr reverse( out ) ) x_i )
    )
)

procedure( s3dJsonRead( t_file )
    let( ( txt res )
        txt = s3dJsonSlurp( t_file )
        when( txt
            res = nil
            errset( res = s3dJsonVal( txt 1 ) )
            when( res  car( res ) )
        )
    )
)

; Value of t_key in a parsed object, or nil. Own lookup rather than assoc: the
; comparison must be a plain string compare, whatever assoc happens to use.
procedure( s3dJsonGet( g_node t_key )
    let( ( out )
        when( g_node && listp( g_node ) && (car( g_node ) == 'jobj)
            foreach( pair cadr( g_node )
                when( car( pair ) == t_key  out = cadr( pair ) )
            )
        )
        out
    )
)

; t if the key is present, regardless of its value. Needed to tell a JSON
; false/null apart from a missing key, since both parse to nil.
procedure( s3dJsonHas( g_node t_key )
    let( ( out )
        when( g_node && listp( g_node ) && (car( g_node ) == 'jobj)
            foreach( pair cadr( g_node )
                when( car( pair ) == t_key  out = t )
            )
        )
        out
    )
)

; The elements of an array value, as a plain SKILL list.
procedure( s3dJsonList( g_node t_key )
    let( ( val )
        val = s3dJsonGet( g_node t_key )
        when( val && listp( val ) && (car( val ) == 'jarr)
            cadr( val )
        )
    )
)

;---------------------------------------------------------------------
;  Silkscreen configuration
;---------------------------------------------------------------------

; Read the config file and return
;   list( l_topLayers l_bottomLayers f_thickness g_clip s_endCap g_export )
; Any missing piece falls back to the built-in default, and a file that cannot
; be read or parsed degrades to all defaults with a message - a broken config
; must never cost the user the whole export.
procedure( s3dSilkConfig( @optional ( t_file nil ) )
    let( ( cfg silk settings top bottom thickness clip endCap doExport )
        top = S3D_SilkDefaultTop
        bottom = S3D_SilkDefaultBottom
        thickness = S3D_SilkDefaultThickness
        clip = t
        endCap = 'ROUND
        doExport = t

        unless( t_file  t_file = "simple3d_config.json" )

        if( isFile( t_file ) then
            cfg = s3dJsonRead( t_file )
            if( cfg then
                printf( "Simple 3D: silkscreen config: %s\n" t_file )
                silk = s3dJsonGet( cfg "silkscreen" )
                settings = s3dJsonGet( cfg "settings" )

                when( s3dJsonList( silk "top" )     top = s3dJsonList( silk "top" ) )
                when( s3dJsonList( silk "bottom" )  bottom = s3dJsonList( silk "bottom" ) )

                when( s3dJsonGet( settings "silkscreenThickness" )
                    thickness = s3dJsonGet( settings "silkscreenThickness" )
                )
                when( s3dJsonHas( settings "clipToBoardOutline" )
                    clip = s3dJsonGet( settings "clipToBoardOutline" )
                )
                when( s3dJsonHas( settings "exportSilkscreen" )
                    doExport = s3dJsonGet( settings "exportSilkscreen" )
                )
                when( stringp( s3dJsonGet( settings "endCapType" ) )
                    ; only the three Allegro end-cap keywords are accepted; a
                    ; typo silently becoming 'SQUARE would be hard to notice.
                    case( upperCase( s3dJsonGet( settings "endCapType" ) )
                        ( "ROUND"    endCap = 'ROUND )
                        ( "SQUARE"   endCap = 'SQUARE )
                        ( "OCTAGON"  endCap = 'OCTAGON )
                        ( t
                            printf( "Simple 3D: warning - unknown endCapType %L in %s; using ROUND.\n"
                                    s3dJsonGet( settings "endCapType" ) t_file )
                        )
                    )
                )
            else
                printf( "Simple 3D: warning - could not parse %s; using built-in silkscreen defaults.\n"
                        t_file )
            )
        else
            printf( "Simple 3D: no silkscreen config at %s; using built-in defaults.\n" t_file )
        )
        list( top bottom thickness clip endCap doExport )
    )
)

;---------------------------------------------------------------------
;  Polygon -> JSON vertices
;
;  The polygon boundary goes into the JSON as Allegro's own vertex list -
;  (x, y, signed_radius) per point - and the arcs are rebuilt on the Python
;  side. It used to be rebuilt here, into segment/arc primitives; that put the
;  one genuinely ambiguous decision in the file format, where nothing could
;  check it. See PROJECT_NOTES round 10b: the doc sentence describing the sign
;  of the radius admits two readings, and an arc built on the wrong side of its
;  chord still closes, so the mistake is invisible until someone measures area.
;
;  Python can measure area - every polygon carries Allegro's own poly->area -
;  so it resolves the reading itself, per board, and says which one won. This
;  side therefore reports what the database holds and decides nothing.
;---------------------------------------------------------------------

; Write one vertex list as  [x, y, radius]  rows, indented x_indent tabs.
procedure( s3dWriteVertexList( p_port l_vertices x_indent )
    let( ( pad ( isFirst t ) xy rad )
        pad = ""
        for( i 1 x_indent
            pad = strcat( pad "	" )
        )
        foreach( vertex l_vertices
            if( isFirst then
                isFirst = nil
            else
                fprintf( p_port ",\n" )
            )
            xy = car( vertex )
            rad = cadr( vertex )
            unless( rad  rad = 0.0 )
            fprintf( p_port "%s[%f, %f, %f]" pad xCoord( xy ) yCoord( xy ) rad )
        )
    )
)

;---------------------------------------------------------------------
;  Collecting the silkscreen
;---------------------------------------------------------------------

; Every dbid on a silkscreen layer -> filled polygons.
;
; Text is the only special case. Allegro draws text as strokes, so a text dbid
; is vectorised with axlText2Lines and each resulting r_path is widened into a
; polygon with ?line2poly (verbatim the idiom in the axlText2Lines docs).
; True-type text has no text block and is converted directly instead - that is
; how exportJson tells the two apart as well.
; A multi-segment path is converted ONE SEGMENT AT A TIME, and that is the
; whole point rather than an optimisation.
;
; axlPolyFromDB on a whole line/cline MITRES the joins between its segments: on
; a real board, a 0.15 wide line turning a right angle came back with a square
; outer corner whose diagonal offset was exactly 0.075*sqrt(2) - a textbook
; mitre - where the artwork has a round join, because a plot sweeps a round
; aperture along the path. The 3D model then showed sharp corners on some turns
; while others (junctions of two separate lines, where the round END CAPS
; overlap) came out round, which is exactly the inconsistency reported.
;
; Converting each segment separately gives each one round caps, and the union of
; those overlapping stadiums IS a round join. The documentation says the same
; thing from the other direction: of ?line2poly it notes "typically one poly is
; returned for each segment in the r_path" - which is why text, which goes
; through that path, never had the problem.
;
; They are deliberately NOT merged here. The Python side draws a compound of
; overlapping solids anyway, and when clipping is on axlPolyOperation unions
; them as a side effect of the AND.
procedure( s3dPolysFromDbid( o_dbid s_endCap )
    let( ( polys lines flat segments )
        polys = nil
        cond(
            ( o_dbid->objType == "text"
                ; Allegro draws text as strokes, so a text dbid is vectorised
                ; with axlText2Lines and each r_path widened with ?line2poly -
                ; verbatim the idiom in the axlText2Lines docs. True-type text
                ; has no text block and converts directly instead; that is how
                ; exportJson tells the two apart as well.
                if( o_dbid->textBlock then
                    errset( lines = axlText2Lines( o_dbid ) )
                    when( lines
                        flat = foreach( mapcan x lines x )
                        foreach( path flat
                            errset(
                                polys = append( polys
                                    axlPolyFromDB( path ?endCapType s_endCap ?line2poly t ) )
                            )
                        )
                    )
                    ; A font that does not vectorise still has an outline form.
                    unless( polys
                        errset( polys = axlPolyFromDB( o_dbid ?endCapType s_endCap ) )
                    )
                else
                    errset( polys = axlPolyFromDB( o_dbid ?endCapType s_endCap ) )
                )
            )
            ( o_dbid->objType == "path"
                segments = nil
                errset( segments = o_dbid->segments )
                foreach( segment segments
                    errset(
                        polys = append( polys
                            axlPolyFromDB( segment ?endCapType s_endCap ) )
                    )
                )
                ; A segment that will not convert on its own drops a piece of
                ; the line silently, and the area check downstream cannot see a
                ; missing stroke - each surviving polygon is still consistent
                ; with its own area. So say it here. One segment may yield more
                ; than one polygon, hence "fewer than".
                when( segments && (length( polys ) < length( segments ))
                    printf( "Simple 3D: warning - a silkscreen line has %d segment(s) but produced only %d polygon(s).\n"
                            length( segments ) length( polys ) )
                )
                ; Single-segment paths, or a path whose segments will not
                ; convert on their own, still have to come out somehow.
                unless( polys
                    errset( polys = axlPolyFromDB( o_dbid ?endCapType s_endCap ) )
                )
            )
            ( t
                ; shapes, rects, filled areas: a boundary already, nothing to
                ; sweep, so convert whole.
                errset( polys = axlPolyFromDB( o_dbid ?endCapType s_endCap ) )
            )
        )
        polys
    )
)

; All silkscreen polygons on the given layers, GROUPED BY LAYER.
;
; Grouping is what lets the GUI offer the layers as checkboxes: the exporter
; collects every layer the config lists, and which of them actually reach the
; model is then chosen per build, with no re-export. The config answers "what
; exists", the checkboxes answer "what to draw".
;
; One sweep covers both component legends and free board geometry: with the
; silkscreen layers as the only visible ones, axlAddSelectAll returns the
; figures owned by symbols as well as the loose ones (which is why exportJson
; has to filter on elem->parent->refdes - here both are wanted).
;
; The visibility and find-filter state is snapshotted and restored, per the
; programming model in the axlVisibleDesign documentation. Without that the
; user is left staring at a blank board after an export.
procedure( s3dCollectSilkByLayer( l_layers s_endCap )
    let( ( saveVis saveEnabled saveOn elems polys out key groups order ( nBad 0 ) )
        out = nil
        groups = makeTable( "s3dSilkGroups" nil )
        order = tconc( nil nil )
        when( l_layers
            saveVis = axlVisibleGet()
            saveEnabled = axlGetFindFilter( t )
            saveOn = axlGetFindFilter( nil )

            axlVisibleDesign( nil )
            foreach( layer l_layers
                unless( axlVisibleLayer( layer t )
                    printf( "Simple 3D: warning - no such layer: %s\n" layer )
                )
            )
            axlClearSelSet()
            axlSetFindFilter( ?enabled list( "noall" "lines" "shapes" "text" )
                              ?onButtons list( "noall" "lines" "shapes" "text" ) )
            axlAddSelectAll()
            elems = axlGetSelSet()
            axlClearSelSet()

            ; Restore before the (much slower) polygon conversion, so an error
            ; in the conversion cannot strand the session with a hidden design.
            errset( axlVisibleSet( saveVis ) )
            when( saveEnabled || saveOn
                ; axlGetFindFilter reports DYNTHEMALS among the on-buttons but
                ; refuses to take it back ("Options are ignored for onButtons"),
                ; so handing its own answer straight back produces a warning on
                ; every export. Drop it rather than leave the noise.
                errset(
                    axlSetFindFilter( ?enabled saveEnabled
                                      ?onButtons remove( "DYNTHEMALS" saveOn ) )
                )
            )

            foreach( elem elems
                ; Bucket by the SOURCE object's layer, before conversion: a
                ; polygon has no layer of its own, and text loses even the dbid
                ; once axlText2Lines has vectorised it. Still one sweep per
                ; side - sweeping once per layer would multiply the visibility
                ; churn for nothing.
                key = nil
                errset( key = elem->layer )
                unless( stringp( key )  key = sprintf( nil "%L" key ) )

                ; Per element, so one object the converter cannot handle costs
                ; that object and not the whole side. Before this, a single
                ; failure anywhere in the sweep propagated out of
                ; s3dMakeSilkscreen, was swallowed by the errset at the call
                ; site, and the export finished with no silkscreen at all and
                ; nothing on screen to say why.
                polys = nil
                unless( errset( polys = s3dPolysFromDbid( elem s_endCap ) )
                    nBad = nBad + 1
                    when( nBad == 1
                        printf( "Simple 3D: warning - a %s object on %s could not be converted; skipping it (further ones are counted only).\n"
                                elem->objType key )
                    )
                )
                foreach( poly polys
                    when( poly && !poly->isHole
                        unless( groups[key]
                            groups[key] = tconc( nil nil )
                            tconc( order key )
                        )
                        tconc( groups[key] poly )
                    )
                )
            )
        )

        when( nBad > 0
            printf( "Simple 3D: warning - %d silkscreen object(s) could not be converted and were skipped.\n" nBad )
        )

        ; -> ( (layer polys) (layer polys) ... ), layers in the order Allegro
        ; first mentioned them, which keeps the GUI's list stable between runs.
        out = tconc( nil nil )
        foreach( key cdr( car( order ) )
            tconc( out list( key cdr( car( groups[key] ) ) ) )
        )
        cdr( car( out ) )
    )
)

; Total polygon count across a side's groups, for the console summary.
procedure( s3dGroupCount( l_groups )
    let( ( ( n 0 ) )
        foreach( group l_groups
            n = n + length( cadr( group ) )
        )
        n
    )
)

;---------------------------------------------------------------------
;  Clipping to the board
;---------------------------------------------------------------------

; The board area as polygons: the design outline minus every cutout - the same
; two sources makePcbContour() uses for the solid, so the silkscreen is clipped
; to exactly the material that exists.
procedure( s3dBoardPoly()
    let( ( dsn outline polys cutouts cutPolys res )
        dsn = axlDBGetDesign()
        outline = dsn->designOutline
        if( outline then
            errset( polys = axlPolyFromDB( outline ) )
            if( polys then
                cutPolys = nil
                cutouts = axlDBGetShapes( "BOARD GEOMETRY/CUTOUT" )
                foreach( cutout cutouts
                    errset( cutPolys = append( cutPolys axlPolyFromDB( cutout ) ) )
                )
                when( cutPolys
                    res = nil
                    errset( res = axlPolyOperation( polys cutPolys 'ANDNOT ) )
                    if( res then
                        polys = remd( nil res )
                    else
                        printf( "Simple 3D: warning - could not subtract cutouts from the board outline; silkscreen is clipped to the outline only.\n" )
                    )
                )
                polys
            else
                printf( "Simple 3D: warning - could not convert the design outline to a polygon; silkscreen will not be clipped.\n" )
                nil
            )
        else
            printf( "Simple 3D: warning - no design outline; silkscreen will not be clipped.\n" )
            nil
        )
    )
)

; t if bounding box l_inner lies entirely within l_outer.
procedure( s3dBBoxInside( l_inner l_outer )
    let( ( ( eps 1.0e-9 ) )
        when( l_inner && l_outer
            (xCoord( car( l_inner ) ) >= xCoord( car( l_outer ) ) - eps) &&
            (yCoord( car( l_inner ) ) >= yCoord( car( l_outer ) ) - eps) &&
            (xCoord( cadr( l_inner ) ) <= xCoord( cadr( l_outer ) ) + eps) &&
            (yCoord( cadr( l_inner ) ) <= yCoord( cadr( l_outer ) ) + eps)
        )
    )
)

; One batch through axlPolyOperation. That API is documented as best-effort
; ("provided as-is ... may fail", returns nil on failure), so a failed batch
; keeps its geometry unclipped and says so, rather than dropping legend that
; is almost certainly on the board anyway.
procedure( s3dClipChunk( l_chunk l_board )
    let( ( res )
        res = nil
        errset( res = axlPolyOperation( l_chunk l_board 'AND ) )
        if( res then
            remd( nil res )
        else
            printf( "Simple 3D: warning - silkscreen clip failed for %d polygon(s); kept unclipped.\n"
                    length( l_chunk ) )
            l_chunk
        )
    )
)

; Clip silkscreen polygons to the board area.
;
; Two things keep this affordable. Polygons whose bounding box is inside the
; board's are passed through untouched when the board is a plain rectangle with
; no cutouts (the common case, and then correct by construction). The rest go
; through axlPolyOperation in batches: its documentation warns about time and
; memory beyond ~10000 polygons, and batching also contains a failure to the
; batch it happened in.
procedure( s3dClipPolys( l_polys l_board )
    let( ( ( batchSize 400 ) out batch ( n 0 ) fast boardBBox ( inside 0 ) )
        if( !l_board || !l_polys then
            l_polys
        else
            out = tconc( nil nil )
            batch = nil
            fast = (length( l_board ) == 1) && car( l_board )->isRect &&
                   !car( l_board )->holes
            when( fast  boardBBox = car( l_board )->bBox )

            foreach( poly l_polys
                if( fast && s3dBBoxInside( poly->bBox boardBBox ) then
                    inside = inside + 1
                    tconc( out poly )
                else
                    batch = cons( poly batch )
                    n = n + 1
                    when( n >= batchSize
                        foreach( clipped s3dClipChunk( batch l_board )
                            tconc( out clipped )
                        )
                        batch = nil
                        n = 0
                    )
                )
            )
            when( batch
                foreach( clipped s3dClipChunk( batch l_board )
                    tconc( out clipped )
                )
            )
            when( fast
                printf( "Simple 3D: %d silkscreen polygon(s) were wholly inside the board outline (clip skipped).\n"
                        inside )
            )
            cdr( car( out ) )
        )
    )
)

;---------------------------------------------------------------------
;  Top level
;---------------------------------------------------------------------

; Clip each layer's polygons separately.
;
; Clipping a whole side at once would be marginally cheaper, but axlPolyOperation
; unions overlapping polygons, so polygons from different layers would come back
; merged into single regions with no layer left to speak of. Groups that clip to
; nothing are dropped, so a layer that lies entirely off the board does not
; appear in the GUI as an empty choice.
procedure( s3dClipGroups( l_groups l_board )
    let( ( out clipped )
        out = tconc( nil nil )
        foreach( group l_groups
            clipped = s3dClipPolys( cadr( group ) l_board )
            when( clipped
                tconc( out list( car( group ) clipped ) )
            )
        )
        cdr( car( out ) )
    )
)

; Collect the whole silkscreen once for the design.
; -> list( f_thickness l_topPolys l_bottomPolys )  or nil if disabled/empty.
procedure( s3dMakeSilkscreen( l_config )
    let( ( top bottom thickness clip endCap doExport topPolys botPolys board )
        top = nth( 0 l_config )
        bottom = nth( 1 l_config )
        thickness = nth( 2 l_config )
        clip = nth( 3 l_config )
        endCap = nth( 4 l_config )
        doExport = nth( 5 l_config )

        when( doExport
            printf( "Simple 3D: collecting silkscreen...\n" )
            ; Both sides come back as ( (layer polys) ... ), so everything from
            ; here on works in groups: s3dGroupCount to count across them and
            ; s3dClipGroups to clip each layer on its own.
            topPolys = s3dCollectSilkByLayer( top endCap )
            botPolys = s3dCollectSilkByLayer( bottom endCap )
            printf( "Simple 3D: silkscreen polygons - top %d, bottom %d\n"
                    s3dGroupCount( topPolys ) s3dGroupCount( botPolys ) )
            foreach( group append( topPolys botPolys )
                printf( "Simple 3D:   %s - %d polygon(s)\n"
                        car( group ) length( cadr( group ) ) )
            )

            when( clip && (topPolys || botPolys)
                board = s3dBoardPoly()
                when( board
                    printf( "Simple 3D: clipping silkscreen to the board outline...\n" )
                    topPolys = s3dClipGroups( topPolys board )
                    botPolys = s3dClipGroups( botPolys board )
                    printf( "Simple 3D: after clipping - top %d, bottom %d\n"
                            s3dGroupCount( topPolys ) s3dGroupCount( botPolys ) )
                )
            )

            when( topPolys || botPolys
                list( thickness topPolys botPolys )
            )
        )
    )
)

; Stream one side's polygons into the open file.
;
; Streamed rather than accumulated into one string: a dense board's legend runs
; to tens of thousands of primitives, and building that with repeated strcat is
; quadratic and hits the same "insufficient memory" wall the component section
; already has a note about.
procedure( s3dWriteSilkPolys( p_port l_groups )
    let( ( ( firstPoly t ) holes ( firstHole t ) area layer )
        foreach( group l_groups
        layer = car( group )
        foreach( poly cadr( group )
            if( firstPoly then
                firstPoly = nil
            else
                fprintf( p_port ",\n" )
            )
            fprintf( p_port "\t\t\t{\n" )

            ; Which layer this polygon came from. The array stays FLAT - one
            ; object per polygon, exactly as before - so a reader that ignores
            ; this key still builds the whole legend.
            fprintf( p_port "\t\t\t\t\"layer\": \"%s\",\n" layer )

            ; Allegro's own area for this polygon, already net of its holes.
            ; This is the reference the Python side resolves the arc convention
            ; against and then verifies every polygon by, so it is not optional
            ; bookkeeping - without it the reconstruction has nothing to check
            ; itself against. Costs one float per polygon.
            area = nil
            errset( area = poly->area )
            when( area
                fprintf( p_port "\t\t\t\t\"area\": %f,\n" area )
            )

            fprintf( p_port "\t\t\t\t\"vertices\": [\n" )
            s3dWriteVertexList( p_port poly->vertices 5 )
            fprintf( p_port "\n\t\t\t\t]" )

            holes = poly->holes
            when( holes
                fprintf( p_port ",\n\t\t\t\t\"holes\": [\n" )
                firstHole = t
                foreach( hole holes
                    if( firstHole then
                        firstHole = nil
                    else
                        fprintf( p_port ",\n" )
                    )
                    fprintf( p_port "\t\t\t\t\t[\n" )
                    s3dWriteVertexList( p_port hole->vertices 6 )
                    fprintf( p_port "\n\t\t\t\t\t]" )
                )
                fprintf( p_port "\n\t\t\t\t]" )
            )
            fprintf( p_port "\n\t\t\t}" )
        )
        )
    )
)

; The whole "silkscreen" object, written straight to the open file.
procedure( s3dWriteSilkscreen( p_port l_silk )
    let( ( thickness topPolys botPolys )
        thickness = nth( 0 l_silk )
        topPolys = nth( 1 l_silk )
        botPolys = nth( 2 l_silk )

        fprintf( p_port "\t\"silkscreen\": {\n" )
        fprintf( p_port "\t\t\"thickness\": %f,\n" thickness )
        fprintf( p_port "\t\t\"top\": [\n" )
        s3dWriteSilkPolys( p_port topPolys )
        fprintf( p_port "\n\t\t],\n" )
        fprintf( p_port "\t\t\"bottom\": [\n" )
        s3dWriteSilkPolys( p_port botPolys )
        fprintf( p_port "\n\t\t]\n" )
        fprintf( p_port "\t}\n" )
    )
)

procedure( create3dIntermediateFormat( thicknesses edgeCuts pcbColor symbols variantName fileName @optional ( silk nil ) )
    let( ( ( stepModelPlacements 'unbound ) ( edges 'unbound ) ( cut 'unbound ) ( cuts 'unbound ) body )
        ; reset base board contour
        when( car( edgeCuts )
            edges = car( edgeCuts )
        )

        when( cadr( edgeCuts )
            cuts = cadr( edgeCuts )
        )

        ; export step package mapping information
        foreach( symbol symbols
            placement = symbolReturn3DElements( symbol )

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

        ; add name + a format marker so the Python side can tell a Simple 3D
        ; intermediate from any other .json that happens to sit in the folder.
        ; Files without "format": "simple3d" are ignored by the GUI.
        ; add name + a format marker so the Python side can tell a Simple 3D
        ; intermediate from any other .json that happens to sit in the folder.
        ; Files without "format": "simple3d" are ignored by the GUI.
        ; NOTE: no embedded \t here - the line writer below prefixes every line
        ; with one tab, so embedding another would double-indent these keys
        ; (still valid JSON, but inconsistent with the rest of the file).
        ; format_version 2 added the optional "silkscreen" object; 3 tags every
        ; silkscreen polygon with the layer it came from, so the layers can be
        ; switched on and off when the model is built instead of at export
        ; time. Both additions are optional to a reader - an older file simply
        ; has no layers to choose from and builds whole.
        name = strcat(
            "\"format\": \"simple3d\",\n"
            "\"format_version\": 3,\n"
            "\"name\": \"" variantName "\""
        )

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

        ; write step model placement informations
        ; FIX (simple3d): guard the unbound case. If no component has a STEP
        ; mapping, stepModelPlacements is still the 'unbound marker and car()
        ; on it faults. That used to be an odd corner; with silkscreen a bare
        ; board is a legitimate thing to export, so it has to work.
        if( boundp( 'stepModelPlacements ) then
            stepModelPlacements = buildString( car( stepModelPlacements ) ",\n" )
        else
            stepModelPlacements = nil
        )

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

        ; to prevent fprintf insufficient memory error
        body = strcat( name ",\n" pcb )
        when( stepModelPlacements
            body = strcat( body ",\n" stepModelPlacements )
        )
        ; the silkscreen object follows, so the last line needs its comma
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
    let( (  ( variantFile "Variants.lst" ) dsnName dsn thicknesses edgeCuts silk variantInformation variantSymbolList alternateParts variant variantCount symbols variantName fileName thicknesses elements placement outFile outPort pcb lines )

        ; get design and design name
        dsnName = axlCurrentDesign()
        dsn = axlDBGetDesign()

        ; create dir (recursively - createDir makes only one level at a time,
        ; so walk the path and create each missing segment).
        s3dMakeDirs( dir )

        ; calculate pcb thickness
        thicknesses = calculateBoardThickness()

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
        unless( errset( silk = s3dMakeSilkscreen( s3dSilkConfig( configFile ) ) t )
            printf( "Simple 3D: ERROR - silkscreen collection failed (message above).\n" )
            printf( "Simple 3D: the board and its components are still exported; only the legend is missing.\n" )
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
                    create3dIntermediateFormat( thicknesses edgeCuts pcbColor symbols variantName fileName silk )
                )

                print( "Export complete!" )
            else
                error( "No variant information could be read!" )
            )
        else
            ; export all symbols, if no variant.lst can be found
            warn( "No variant information present!\n Exporting all components!" )

            ; Same routine as the variant path, with no variant table: every
            ; symbol that has a refdes and is not marked NO_STEP_EXPORT.
            symbols = s3dSymbolsToExport( nil nil )

            variantName = lowerCase( dsnName )
            fileName = strcat( dir "/" variantName ".json" )
            create3dIntermediateFormat( thicknesses edgeCuts pcbColor symbols variantName fileName silk )
        )
    )
)
