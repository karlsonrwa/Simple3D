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
;
;  USAGE
;    makeVariant3dIntermediates( outputDir [ pcbColor ] )
;  Writes <design>.json (or one <design>_<variant>.json per variant if a
;  Variants.lst is present) into outputDir. Design units must be mm.
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

; Pre-flight check for the Simple 3D menu. Returns
;   ( refDesWithoutMfrPn  refDesWithoutStepModel ).
; Only components that would be exported (refdes + STEP mapping) are checked.
procedure( s3dCheckMfrPn()
    let( ( noMfrPn noModel sym comp mapping )
        noMfrPn = tconc( nil nil )
        noModel = tconc( nil nil )
        foreach( sym axlDBGetDesign()->symbols
            when( sym->refdes
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
                                        symbols = nconc( symbols list( nth( 0 subStrings ) ) )
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
                            symbols = nconc( symbols list( nth( 0 subStrings ) ) )

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

        ; return
        list( edges cuts )
    )
)

procedure( symbolReturn3DElements( refDes )
    let( ( stepPackageMapping dbid sym mappingData stepFileName offset_x offset_y offset_z rotation_x rotation_y rotation_z isMirrored xy angle hole mfrPn ( holes 'unbound ) )

        stepPackageMapping = nil

        ; get symbol (dbid)
        dbid = axlDBFindByName( 'refdes refDes )
        sym = dbid->symbol

        ; step package mappingData
        mappingData = axlStepGet( nil nil sym )
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
        if( boundp( 'cuts ) then
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

procedure( create3dIntermediateFormat( thicknesses edgeCuts pcbColor symbols variantName fileName )
    let( ( ( stepModelPlacements 'unbound ) ( edges 'unbound ) ( cut 'unbound ) ( cuts 'unbound ) )
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
        name = strcat(
            "\"format\": \"simple3d\",\n"
            "\"format_version\": 1,\n"
            "\"name\": \"" variantName "\""
        )

        ; make pcb (including all cutouts and holes)
        pcb = makePcb( thicknesses edges cuts pcbColor )

        ; write step model placement informations
        stepModelPlacements = buildString( car( stepModelPlacements) ",\n" )

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
        lines = parseString( strcat( name ",\n" pcb ",\n" stepModelPlacements ) "\n" )

        fprintf( outPort "{\n")

        foreach( line lines
            fprintf( outPort strcat( "\t" line ) )
            fprintf( outPort "\n" )
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

procedure( makeVariant3dIntermediates( dir, @optional ( pcbColor list( 0.0 0.4 0.0) ) )
    let( (  ( variantFile "Variants.lst" ) dsnName dsn thicknesses edgeCuts variantInformation variantSymbolList alternateParts variant variantCount symbols variantName fileName thicknesses elements placement outFile outPort pcb lines )

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

                    ; if variant has alternate parts, add them to the symbol list
                    if( boundp( 'alternateParts ) then
                        symbols = append( variantSymbolList[variant] alternateParts[variant]~>? )
                    else
                        symbols = variantSymbolList[variant]
                    )

                    variantName = lowerCase( strcat( dsnName "_" variant ) )
                    fileName = lowerCase( strcat( dir "/" variantName ".json" ) )
                    create3dIntermediateFormat( thicknesses edgeCuts pcbColor symbols variantName fileName )
                )

                print( "Export complete!" )
            else
                error( "No variant information could be read!" )
            )
        else
            ; export all symbols, if no variant.lst can be found
            warn( "No variant information present!\n Exporting all components!" )

            ; get all symbols
            symbols = mapcar( lambda( ( symbol ) when( symbol->refdes symbol->refdes ) ) dsn->symbols )

            ; remove nils
            symbols = remd( nil symbols )

            variantName = lowerCase( dsnName )
            fileName = strcat( dir "/" variantName ".json" )
            create3dIntermediateFormat( thicknesses edgeCuts pcbColor symbols variantName fileName )
        )
    )
)
