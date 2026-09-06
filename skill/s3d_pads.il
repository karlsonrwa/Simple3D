;=====================================================================
;  skill/s3d_pads.il - the copper pads: padstack figures, pin placements, the writer
;
;  Part 10 of 10 of the Simple 3D exporter (round 85, 2026-09-07); the
;  loader makeVariant3dIntermediates.il loads the parts in order. Load it,
;  or simple3d.il, never a part on its own.
;=====================================================================

;=====================================================================
;  COPPER PADS  (NEW - simple3d, format_version 10)
;
;  What a pin's copper looks like on the two outer faces, so the Python side
;  can draw it there - as thin copper-coloured surfaces lying on the mask,
;  for a picture that reads as a board rather than as a green slab.
;
;  Two halves, and a LIBRARY rather than per-pin geometry:
;
;    "padstacks"  one entry per distinct padstack the pins use: its drill
;                 (at the padstack origin, unrotated) and every REGULAR pad
;                 on an ETCH layer, each with the figure Allegro names, its
;                 bounding box and offset, and its OUTLINE - the pad's own
;                 axlPath, walked with the documented accessors, in the same
;                 segment / arc / circle vocabulary the board outline uses.
;                 Every figure kind carries such a path (measured on three
;                 boards: CIRCLE is a start point and one closing arc,
;                 OBLONG two lines and two arcs, ROUNDED_RECTANGLE eight
;                 pieces, SHAPE whatever was drawn), so no figure kind is
;                 interpreted here - the outline is the truth and figureName
;                 travels beside it as a label.
;    "pins"       one row per pin of every placed symbol - mechanical
;                 symbols included, exactly the pins symbolReturnPinHoles
;                 drills - as [x, y, rotation, mirrored, padstack, start
;                 layer, end layer]. The span is the pin's own ->startEnd:
;                 it is what says which layers the pin reaches (a surface
;                 pin on a flex connector sits on INNER1, and a through pin
;                 of a flex-mounted part spans INNER1..INNER2 - measured on
;                 Cadence's demo board, where 48 of 2720 pins are exactly
;                 that). Which of those layers is an OUTER face of the pin's
;                 zone, and which pad goes where, is decided on the Python
;                 side against the stackups; this side reports.
;
;  VARIANTS: like the silkscreen, deliberately variant-INDEPENDENT. The bare
;  board carries every pad whether or not the part is installed, so the pads
;  are collected once per design and written into every file.
;
;  Vias are not written. They are tented under the mask on almost every
;  board, and a picture is what this is for; ask when a board needs them.
;=====================================================================

; [x, y] or null.
procedure( s3dPointJson( l_point )
    if( l_point && numberp( xCoord( l_point ) ) && numberp( yCoord( l_point ) ) then
        sprintf( nil "[%f, %f]" xCoord( l_point ) yCoord( l_point ) )
    else
        "null"
    )
)

; [[x0, y0], [x1, y1]] or null.
procedure( s3dBBoxJson( l_bbox )
    if( l_bbox && car( l_bbox ) && cadr( l_bbox ) then
        strcat( "[" s3dPointJson( car( l_bbox ) ) ", " s3dPointJson( cadr( l_bbox ) ) "]" )
    else
        "null"
    )
)

; A pad's outline - an axlPath - as a JSON array of primitives, or nil when
; the path has fewer than two points.
;
; A path is not a dbid and has no ->segments; axlPathGetPathSegs hands its
; pieces over in order, and each piece carries only its END point, so the
; first piece is the start and every later one runs from where the last
; finished. An arc piece answers axlPathSegGetArcCenter with its centre and
; axlPathSegGetArcClockwise with its direction; a line answers nil to both.
; An arc that ends where it started is a full circle - a CIRCLE pad is
; exactly that, one start point and one closing arc - and is written as the
; circle primitive, because an arc of zero span reads as no arc at all.
procedure( s3dPathContourJson( r_path )
    let( ( segs prev e c cw r dx dy out ( n 0 ) prim )
        segs = nil
        errset( segs = axlPathGetPathSegs( r_path ) )
        out = tconc( nil nil )
        prev = nil
        foreach( sg segs
            e = nil
            errset( e = axlPathSegGetEndPoint( sg ) )
            when( e
                when( prev
                    c = nil
                    cw = nil
                    errset( c = axlPathSegGetArcCenter( sg ) )
                    errset( cw = axlPathSegGetArcClockwise( sg ) )
                    if( c then
                        dx = xCoord( prev ) - xCoord( c )
                        dy = yCoord( prev ) - yCoord( c )
                        r = sqrt( dx * dx + dy * dy )
                        dx = xCoord( e ) - xCoord( prev )
                        dy = yCoord( e ) - yCoord( prev )
                        if( sqrt( dx * dx + dy * dy ) < 1.0e-9 then
                            prim = makeCircle( c 2 * r )
                        else
                            prim = s3dArcPrimJson( xCoord( c ) yCoord( c ) r
                                                   xCoord( prev ) yCoord( prev )
                                                   xCoord( e ) yCoord( e ) cw )
                        )
                    else
                        prim = s3dSegmentPrimJson( xCoord( prev ) yCoord( prev )
                                                   xCoord( e ) yCoord( e ) )
                    )
                    tconc( out prim )
                    n = n + 1
                )
                prev = e
            )
        )
        when( n > 0
            strcat( "[\n" s3dAddIndent( buildString( cdr( car( out ) ) ",\n" ) ) "\n]" )
        )
    )
)

; One pad of a padstack: what Allegro says about it, and its outline.
;
; "inside" is the hole of a DONUT (0 otherwise) - the one thing the outline
; cannot carry, since a path is one loop. "offset" and "bbox" travel beside
; the outline so the reader can tell whether the path already includes the
; offset (the three boards measured all have offsets of 0, so that could not
; be settled here) and check itself against the box.
procedure( s3dPadFigureJson( o_pad )
    let( ( bb off inside outline figure )
        bb = nil
        errset( bb = o_pad->bBox )
        off = nil
        errset( off = o_pad->offset )
        inside = nil
        errset( inside = o_pad->inside )
        unless( numberp( inside )  inside = 0.0 )
        outline = nil
        figure = nil
        errset( figure = o_pad->figure )
        when( figure
            errset( outline = s3dPathContourJson( car( figure ) ) )
        )
        strcat( "{\n"
                "\t\"figure\": " s3dJsonQuote( o_pad->figureName ) ",\n"
                "\t\"bbox\": " s3dBBoxJson( bb ) ",\n"
                "\t\"offset\": " s3dPointJson( off ) ",\n"
                "\t\"inside\": " sprintf( nil "%f" inside ) ",\n"
                "\t\"outline\": " if( outline then s3dAddIndent( outline ) else "null" ) "\n"
                "}" )
    )
)

; A REGULAR pad on an ETCH layer, with a figure. Masks, paste, thermals and
; antipads are not copper.
procedure( s3dIsEtchCopper( o_pad )
    let( ( lay type name )
        lay = nil
        errset( lay = o_pad->layer )
        type = nil
        errset( type = o_pad->type )
        name = nil
        errset( name = o_pad->figureName )
        stringp( lay ) && (strlen( lay ) > 5) && (upperCase( substring( lay 1 5 ) ) == "ETCH/")
            && stringp( type ) && (upperCase( type ) == "REGULAR")
            && stringp( name ) && !(upperCase( name ) == "NULL")
    )
)

; The drill of a padstack as a contour at the padstack's ORIGIN, unrotated:
; the same circle or slot symbolReturnPinHoles cuts through the board, at
; the drill offset the padstack carries (an edge connector's half-holes sit
; off the pad - see s3dDrillXY). nil when there is no hole. The pin's
; rotation is applied on the Python side with the rest of the figure.
procedure( s3dHoleAtOrigin( o_padstack )
    let( ( offset dx dy d w h element )
        offset = nil
        errset( offset = o_padstack->drillOffset )
        dx = 0.0
        dy = 0.0
        when( offset
            when( numberp( xCoord( offset ) )  dx = xCoord( offset ) )
            when( numberp( yCoord( offset ) )  dy = yCoord( offset ) )
        )
        d = nil
        errset( d = o_padstack->drillDiameter )
        w = nil
        errset( w = o_padstack->drillSizeWidth )
        h = nil
        errset( h = o_padstack->drillSizeHeight )
        cond(
            ( numberp( w ) && numberp( h ) && (w > 0.0) && (h > 0.0) && !(w == h)
                element = makeSlotAt( list( dx dy ) 0.0 o_padstack )
                strcat( "[\n" s3dAddIndent( buildString( element ",\n" ) ) "\n]" )
            )
            ( numberp( d ) && (d > 0.0)
                strcat( "[\n" s3dAddIndent( makeCircle( list( dx dy ) d ) ) "\n]" )
            )
            ( t nil )
        )
    )
)

; One padstack of the library, as  "NAME": { usage, drill, pads }, or nil
; when Allegro cannot load it by that name.
procedure( s3dPadstackJson( t_name )
    let( ( ps pads out ( first t ) hole usage lay body )
        ps = nil
        errset( ps = axlLoadPadstack( t_name ) )
        when( ps
            usage = nil
            errset( usage = ps->usage )
            hole = nil
            errset( hole = s3dHoleAtOrigin( ps ) )
            out = strcat( s3dJsonQuote( t_name ) ": {\n"
                          "\t\"usage\": " s3dJsonQuote( usage ) ",\n"
                          "\t\"drill\": " if( hole then s3dAddIndent( hole ) else "null" ) ",\n"
                          "\t\"pads\": {" )
            pads = nil
            errset( pads = ps->pads )
            foreach( pd pads
                when( s3dIsEtchCopper( pd )
                    lay = pd->layer
                    body = strcat( s3dJsonQuote( lay ) ": " s3dPadFigureJson( pd ) )
                    out = strcat( out if( first then "\n" else ",\n" ) s3dAddIndent( body 2 ) )
                    first = nil
                )
            )
            strcat( out if( first then "}\n}" else "\n\t}\n}" ) )
        )
    )
)

; Every pin of every placed symbol, and the padstacks they use.
; -> list( l_padstackJsonStrings l_pinJsonStrings x_pins )  or nil when the
;    design has no pins.
;
; The pins are walked the way symbolReturnPinHoles walks them - the design's
; symbols, mechanical ones included - so a mounting hole with a pad is a pad.
; Padstack names are collected in a table and the library built once per
; name, sorted, so two exports of one board write the same file.
procedure( s3dCollectPads()
    let( ( dsn table names stacks pins ( n 0 ) ( nMissing 0 ) se rot one )
        dsn = axlDBGetDesign()
        table = makeTable( "s3dPadstackNames" nil )
        pins = tconc( nil nil )
        foreach( sym dsn->symbols
            foreach( pin sym->pins
                when( stringp( pin->name ) && pin->xy
                    n = n + 1
                    table[pin->name] = t
                    se = nil
                    errset( se = pin->startEnd )
                    rot = pin->rotation
                    unless( numberp( rot )  rot = 0.0 )
                    tconc( pins sprintf( nil "[%f, %f, %f, %s, %s, %s, %s]"
                                         xCoord( pin->xy ) yCoord( pin->xy ) rot
                                         if( pin->isMirrored then "true" else "false" )
                                         s3dJsonQuote( pin->name )
                                         s3dJsonQuote( when( se car( se ) ) )
                                         s3dJsonQuote( when( se cadr( se ) ) ) ) )
                )
            )
        )
        when( n > 0
            names = sort( table->? 'alphalessp )
            stacks = tconc( nil nil )
            foreach( name names
                one = nil
                errset( one = s3dPadstackJson( name ) )
                if( one then
                    tconc( stacks one )
                else
                    nMissing = nMissing + 1
                    s3dWarn( sprintf( nil "Simple 3D: padstack %s could not be loaded; its pins get no copper." name ) )
                )
            )
            printf( "Simple 3D: copper pads - %d pin(s) on %d padstack(s)%s\n"
                    n length( names )
                    if( nMissing > 0 then sprintf( nil " (%d not loadable)" nMissing ) else "" ) )
            list( cdr( car( stacks ) ) cdr( car( pins ) ) n )
        )
    )
)

; The whole "pads" object, streamed straight to the open file like the
; silkscreen: a dense board has tens of thousands of pins, and one row per
; pin in a string built by repeated strcat is quadratic. g_more says whether
; another member (the silkscreen) follows, and so whether the closing brace
; takes a comma.
procedure( s3dWritePads( p_port l_pads g_more )
    let( ( stacks pins ( first t ) )
        stacks = nth( 0 l_pads )
        pins = nth( 1 l_pads )
        fprintf( p_port "\t\"pads\": {\n" )
        fprintf( p_port "\t\t\"padstacks\": {\n" )
        foreach( s stacks
            unless( first  fprintf( p_port ",\n" ) )
            first = nil
            fprintf( p_port "%s" s3dAddIndent( s 3 ) )
        )
        fprintf( p_port "\n\t\t},\n" )
        fprintf( p_port "\t\t\"pins\": [\n" )
        first = t
        foreach( p pins
            unless( first  fprintf( p_port ",\n" ) )
            first = nil
            fprintf( p_port "\t\t\t%s" p )
        )
        fprintf( p_port "\n\t\t]\n" )
        fprintf( p_port if( g_more then "\t},\n" else "\t}\n" ) )
    )
)
