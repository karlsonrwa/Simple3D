;=====================================================================
;  skill/s3d_geometry.il - segments, arcs, circles, slots, the board contour, pin holes
;
;  Part 5 of 9 of the Simple 3D exporter, cut from
;  makeVariant3dIntermediates.il in round 76 (plan D6) with every procedure
;  and comment as it was; that file loads the parts in order. Load it, or
;  simple3d.il, never a part on its own.
;=====================================================================


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

; Where the DRILL is, which is not always where the pad is.
;
; A padstack may carry an offset from its origin to the hole - Allegro's
; Padstack Editor calls it "Offset from padstack origin to hole", on the Drill
; Offset tab - and an edge connector is exactly what it is for: the pads sit on
; the board while the holes straddle the edge as half-holes. The offset is
; expressed in the PADSTACK's own frame, so it must be rotated by the pin's
; rotation before it is added to the pin's location.
;
; This lived inside makeSlot and nowhere else, so the round-hole branch of
; symbolReturnPinHoles cut at the PAD centre. On the user's bone-a2 the four
; PLS-4 holes carry offset x = 0.375 with the padstack turned to face the board
; edge: the drill belongs on y = 0 and we were putting it 0.375 mm higher, which
; is why Allegro's own 3D showed half-circles on the edge where our STEP showed
; keyholes. One procedure now, called from both branches, so they cannot drift
; apart again.
;
; nil-safe on both counts: a padstack with no offset and a pin with no rotation
; are the ordinary case, and both mean "the drill is where the pad is".
procedure( s3dDrillXY( pin padstack )
    let( ( xy offset rotation dx dy )
        xy       = pin->xy
        offset   = padstack->drillOffset
        rotation = pin->rotation
        dx = 0.0
        dy = 0.0
        when( offset
            when( numberp( xCoord( offset ) )  dx = xCoord( offset ) )
            when( numberp( yCoord( offset ) )  dy = yCoord( offset ) )
        )
        unless( numberp( rotation )  rotation = 0.0 )
        if( (dx == 0.0) && (dy == 0.0) then
            ; Nothing to apply. Returned as-is rather than rotated by zero, so
            ; the overwhelmingly common padstack is not put through a sin/cos
            ; that can only add noise to a coordinate that was exact.
            xy
        else
            rotateXY( xy list( xCoord( xy ) + dx  yCoord( xy ) + dy ) rotation )
        )
    )
)

procedure( makeSlot( pin padstack )
    let( ( xy x y rotation drillSizeWidth drillSizeHeight slot radius xCenter yCenter xyCenter alpha beta ccw segment
           tmp xStart yStart xEnd yEnd xyStart xyEnd )   ; declared, round 75 (D2)
        ; get coordinates - the DRILL's, not the pad's
        rotation = pin->rotation

        xy = s3dDrillXY( pin padstack )
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

; The contour of one shape or polygon, as a JSON array of primitives.
; Same parser the board outline uses - a zone outline, a stiffener shape and
; the board edge all carry the same line/arc segments.
procedure( s3dContourJson( o_dbid )
    let( ( contour element )
        contour = nil
        errset(
            foreach( segment o_dbid->segments
                element = boardGeometryParseSegment( segment )
                when( element
                    if( contour then
                        tconc( contour element )
                    else
                        contour = tconc( nil element )
                    )
                )
            )
        )
        when( contour
            strcat( "[\n" s3dAddIndent( buildString( car( contour ) ",\n" ) ) "\n]" )
        )
    )
)

procedure( makePcbContour( dsn )
    let( ( outline segments ( edges 'unbound ) ( cut 'unbound ) ( cuts 'unbound ) element cutouts )
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
                    s3dAddIndent( cut )
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
            s3dWarn( "Simple 3D: the design outline produced no segments." )
            edges = nil
        )

        ; return
        list( edges cuts )
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

                    ; get position - the DRILL's. It is the pad's only when the
                    ; padstack carries no drill offset; see s3dDrillXY.
                    xy = s3dDrillXY( pin padstack )

                    if( padstack->usage == "Slot" then
                        element = makeSlot( pin padstack )

                        hole = strcat(
                            "[\n"
                                s3dAddIndent( buildString( element ",\n" ) )
                            "\n]"
                        )
                    else
                        ; make a simple drill hole
                        hole = makeCircle( xy padstack->drillDiameter )

                        hole = strcat(
                            "[\n"
                                s3dAddIndent( hole )
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
