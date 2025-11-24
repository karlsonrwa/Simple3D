when( not( isCallable( 'getVariantInfo ) )
    procedure( gdsysGetVariantInfo()
        let( (  (   variantFile "Variants.lst" ) 
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
    let( ( xy xCenter yCenter radius extents xStart yStart xEnd yEnd cw angle1 angle2 startAngle endAngle element )
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
            counterclockwise = "false"
        else
            counterclockwise = "true"
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
        
        ; map the correct angles
        if( ( angle2 - angle1 ) > 0 then
            if( cw then
                startAngle = angle1
                endAngle = angle2
            else
                startAngle = angle2
                endAngle = angle1
            )

            ; if arc is a circle, but not marked as a circle ...
            when( startAngle == endAngle
                endAngle = endAngle + 360.0
            )
        else
            if( cw then
                startAngle = angle1
                endAngle = angle2
            else
                startAngle = angle2
                endAngle = angle1
            )
            
            ; if arc is a circle, but not marked as a circle ...
            when( startAngle == endAngle
                startAngle = startAngle + 360.0
            )
        )

        element = strcat( 
            "{\n\t\"type\": \"arc\",\n"
            "\t\"center\": [" sprintf( nil "%f" xCenter ) ", " sprintf( nil "%f" yCenter ) "],\n"
            "\t\"radius\": " sprintf( nil "%f" radius ) ",\n"
            "\t\"alpha\": " sprintf( nil "%f" startAngle ) ",\n"
            "\t\"beta\": " sprintf( nil "%f" endAngle ) ",\n"
            "\t\"ccw\": " counterclockwise "\n"
            "}" 
        )
    )
)

procedure( makeCircle( x y diameter )
    let( ( element )
        element = strcat(
            "{\n\t\"type\": \"circle\",\n"
            "\t\"x\": " sprintf( nil "%f" x ) ",\n"
            "\t\"y\": " sprintf( nil "%f" y ) ",\n"
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

procedure( makeSlot( padstack x y rotation )
    let( ( drillOffset xDrillOffset yDrillOffset xy x y drillSizeWidth drillSizeHeight slot radius xCenter yCenter xyCenter alpha beta counterclockwise segment )

        drillOffset = padstack->drillOffset

        xDrillOffset = xCoord( drillOffset) + x
        yDrillOffset = yCoord( drillOffset) + y

        ; print(x)
        ; print("\n")
        ; print(y)
        
        
        ; calculate origin (drilloffset )
        xy = rotateXY( list( x y ) list( xDrillOffset yDrillOffset) rotation )
        x = xCoord( xy )
        y = yCoord( xy )

        ; print( xy )

        drillSizeWidth = padstack->drillSizeWidth
        drillSizeHeight = padstack->drillSizeHeight

        ; if slot is actually a hole
        if( drillSizeWidth == drillSizeHeight then
            slot = makeCircle( x y drillSizeWidth )
        else
            if( drillSizeWidth >= drillSizeHeight then
                ; calculate radius 
                radius = drillSizeHeight / 2

                ; make first half circle
                xCenter = x + ( drillSizeWidth - drillSizeHeight ) / 2
                yCenter = y

                ; apply rotation
                xyCenter = rotateXY( xy list( xCenter yCenter ) rotation )
                xCenter = xCoord( xyCenter )
                yCenter = yCoord( xyCenter )

                alpha = 270 + rotation
                beta = 90 + rotation
                alpha = modf( alpha 360.0 )
                beta = modf( beta 360.0 )
                counterclockwise = "true"

                segment = strcat( 
                    "{\n\t\"type\": \"arc\",\n"
                    "\t\"center\": [" sprintf( nil "%f" xCenter ) ", " sprintf( nil "%f" yCenter ) "],\n"
                    "\t\"radius\": " sprintf( nil "%f" radius ) ",\n"
                    "\t\"alpha\": " sprintf( nil "%f" alpha ) ",\n"
                    "\t\"beta\": " sprintf( nil "%f" beta ) ",\n"
                    "\t\"ccw\": " counterclockwise "\n"
                    "}" 
                )

                slot = tconc( nil segment )

                ; make first line
                xStart = x + ( drillSizeWidth - drillSizeHeight ) / 2
                yStart = y + radius

                xPoint = x - ( drillSizeWidth - drillSizeHeight ) / 2
                yPoint = yStart

                xyEnd = rotateXY( xy list( xPoint yPoint ) rotation )
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
                xCenter = x - ( drillSizeWidth - drillSizeHeight ) / 2
                yCenter = y

                ; apply rotation
                xyCenter = rotateXY( xy list( xCenter yCenter ) rotation )
                xCenter = xCoord( xyCenter )
                yCenter = yCoord( xyCenter )

                alpha = 270 + rotation
                beta = 90 + rotation
                alpha = modf( alpha 360.0 )
                beta = modf( beta 360.0 )
                counterclockwise = "true"

                segment = strcat( 
                    "{\n\t\"type\": \"arc\",\n"
                    "\t\"center\": [" sprintf( nil "%f" xCenter ) ", " sprintf( nil "%f" yCenter ) "],\n"
                    "\t\"radius\": " sprintf( nil "%f" radius ) ",\n"
                    "\t\"alpha\": " sprintf( nil "%f" alpha ) ",\n"
                    "\t\"beta\": " sprintf( nil "%f" beta ) ",\n"
                    "\t\"ccw\": " counterclockwise "\n"
                    "}" 
                )

                tconc( slot segment )

                ; make last line
                xStart = x - ( drillSizeWidth - drillSizeHeight ) / 2
                yStart = y - radius

                xPoint = x + ( drillSizeWidth - drillSizeHeight ) / 2
                yPoint = y - radius

                xyEnd = rotateXY( xy list( xPoint yPoint ) rotation )
                xEnd = xCoord( xyEnd )
                yEnd = yCoord( xyEnd )

                segment = strcat( 
                    "{\n\t\"type\": \"segment\",\n"
                    "\t\"start\": [" sprintf( nil "%f" xStart ) ", " sprintf( nil "%f" yStart ) "],\n"
                    "\t\"end\": [" sprintf( nil "%f" xEnd ) ", " sprintf( nil "%f" yEnd ) "]\n"
                    "}"
                )

                tconc( slot segment )

            else
                ; print( "nope" )
            )
        )
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
                element = makeArc( segment )
                
            )
            (
                t
                warn( "Unknown segment ...\n")
            )
        )
        element
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

procedure( symbolReturn3DElements( symbol )
    let( ( stepPackageMapping refdes mappingData stepFileName offset_x offset_y offset_z rotation_x rotation_y rotation_z isMirrored xy angle x y hole ( holes 'unbound ) )

        stepPackageMapping = nil

        refdes = axlDBFindByName( 'refdes symbol )

        ; step package mappingData
        mappingData = axlStepGet( nil nil refdes->symbol )
        stepFileName = mappingData->step_name

        offset_x = mappingData->offset_x
        offset_y = mappingData->offset_y
        offset_z = mappingData->offset_z

        rotation_x = mappingData->rotation_x
        rotation_y = mappingData->rotation_y
        rotation_z = mappingData->rotation_z

        ; symbol
        if( refdes->symbol->isMirrored then
            isMirrored = "true"
        else 

            isMirrored = "false"
        )

        xy = refdes->symbol->xy
        angle = refdes->symbol->rotation

        x = xCoord( xy )
        y = yCoord( xy )

        ; set step package mapping
        when( stepFileName
            stepPackageMapping = strcat(
                "\"" sprintf( nil "%s" refdes->symbol->refdes ) "\": {\n"
                "\t\"step_mapping\": {\n"
                "\t\t\"step_name\": \"" sprintf( nil "%s" stepFileName ) "\",\n"
                "\t\t\"rotation_x\": " sprintf( nil "%f" rotation_x ) ",\n"
                "\t\t\"rotation_y\": " sprintf( nil "%f" rotation_y ) ",\n"
                "\t\t\"rotation_z\": " sprintf( nil "%f" rotation_z ) ",\n"
                "\t\t\"offset_x\": " sprintf( nil "%f" offset_x ) ",\n"
                "\t\t\"offset_y\": " sprintf( nil "%f" offset_y ) ",\n"
                "\t\t\"offset_z\": " sprintf( nil "%f" offset_z ) "\n"
                "\t},\n"
                "\t\"is_mirrored\": " isMirrored ",\n"
                "\t\"x\": " sprintf( nil "%f" x ) ",\n"
                "\t\"y\": " sprintf( nil "%f" y ) ",\n"
                "\t\"angle\": " sprintf( nil "%f" angle ) "\n"
                "}"
            )
        )

        ; export pin holes
        foreach( pin refdes->pins
            when( pin->isThrough
                ; hole = nil
                xy = pin->xy

                ; get padstack
                padstack = axlLoadPadstack( pin->name )
                
                ; calculate position
                x = xCoord( xy )
                y = yCoord( xy )

                if( padstack->usage == "Slot" then
                    ;element = makeSlot( padstack x y pin->rotation )
                    ; print("make slot")
                    ; hole = strcat(
                    ;     "[\n"
                    ;         addIndent( buildString( element ",\n" ) )
                    ;     "\n]"
                    ; )
                    hole = nil
                else
                    hole = makeCircle( x y padstack->drillDiameter )

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

        if( boundp( 'holes ) then
            holes = car( holes )
            holes = buildString( holes ",\n" )
        else 
            holes = nil
        )

        list( stepPackageMapping holes )
    )
)

procedure( makePcb( thickness edges cuts )
    let( ()
        if( boundp( 'cuts ) then
            edges = strcat(
                "\"pcb\": {\n"
                "\t\"thickness\": " sprintf( nil "%f" thickness ) ",\n"
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
            edges = strcat(
                "\"pcb\": {\n"
                "\t\"thickness\": " sprintf( nil "%f" 1.67 ) ",\n"
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

procedure( create3dIntermediateFormat( thickness edgeCuts symbols fileName )
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
            elements = symbolReturn3DElements( symbol )
            placement = car( elements )
            cut = cadr( elements )

            when( cut
                if( boundp( 'cuts ) then
                    tconc( cuts cut )
                else
                    cuts = tconc( nil cut )
                )
            )

            when( placement
                    if( boundp( 'stepModelPlacements ) then
                    tconc( stepModelPlacements placement )
                else
                    stepModelPlacements = tconc( nil placement )
                )
            )
        )
        
        ; make pcb (including all cutouts and holes)
        pcb = makePcb( thickness edges cuts )

        ; write step model placement informations
        stepModelPlacements = buildString( car( stepModelPlacements) ",\n" )

        ; write to file
        outFile = fileName
        outPort = outfile( outFile )

        ; to prevent fprintf insufficient memory error
        lines = parseString( strcat( pcb ",\n" stepModelPlacements ) "\n" )

        fprintf( outPort "{\n")

        foreach( line lines
            fprintf( outPort strcat( "\t" line ) )
            fprintf( outPort "\n" )
        )

        fprintf( outPort "}\n")

        close( outPort )

        t
    )
)

procedure( makeVariant3dIntermediates( dir )
    let( (  ( variantFile "Variants.lst" ) dsnName dsn edgeCuts variantInformation variantSymbolList alternateParts variant symbols fileName thickness elements placement outFile outPort pcb lines )

        ; get design and design name
        dsnName = axlCurrentDesign()
        dsn = axlDBGetDesign()

        ; create dir
        unless( isDir( dir )
            createDir( dir )
        )
        
        ; remove soldermask from overall thickness tbd
        thickness = axlXSectionGet(nil 'thickness)

        ; make pcb contour
        edgeCuts = makePcbContour( dsn )

        if( isFile( variantFile ) then
            ; Read / parse variant list
            variantInformation = gdsysGetVariantInfo()

            if( variantInformation then
                variantSymbolList = car( variantInformation )
                alternateParts = cadr( variantInformation )

                foreach( variant variantSymbolList
                    printf( "Exporting .json for variant: %s\n" variant )

                    ; if variant has alternate parts, add them to the symbol list
                    if( boundp( 'alternateParts ) then
                        symbols = append( variantSymbolList[variant] alternateParts[variant]~>? )
                    else
                        symbols = variantSymbolList[variant]
                    )
                    
                    fileName = strcat( dir "/" dsnName "_" variant ".json" )
                    create3dIntermediateFormat( thickness edgeCuts symbols fileName )
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

            fileName = strcat( dir "/" dsnName "_CORE" ".json" )
            create3dIntermediateFormat( thickness edgeCuts symbols fileName )
        )
    )
)