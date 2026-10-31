;=====================================================================
;  probe_silkfill.il - DIAGNOSTIC for R2-13 of the 28.10.2026 review
;  (round 111), and for R2-5 of the 23.10.2026 one (round 117, below the
;  first two): what becomes of a shape's `fill` - nil an unfilled shape,
;  t a solid one, a list a cross-hatch (axlDbidDoc, SHAPE attributes) - in
;  the exporter and in Allegro's own artwork.
;
;  s3dProbeSilkFill - read-only. Per layer and kind, what the exporter's own
;      sweep returns on the silkscreen and soldermask layers, and every shape
;      axlDBGetShapes( nil ) reports on any layer; every artwork film with
;      its undefined line width and layers. The survey of the nine boards in
;      input/.
;
;  s3dProbeSilkCases - changes the SCRATCH COPY it runs on. Draws the cases
;      on BOARD GEOMETRY/SILKSCREEN_BOTTOM, empty on my_test_board2 (a board
;      of 29.5 x 23 mm), in 4 mm squares:
;
;        A  unfilled rectangle (axlDBCreateRectangle)        at  2, 2
;        B  unfilled shape, boundary width 0.2               at  8, 2
;        C  unfilled shape, boundary width 0                 at 14, 2
;        D  unfilled circle r 2, boundary width 0.15         at 20, 2
;        B2 B again, through axlDBCreateOpenShape            at  8, 15
;        E  cross-hatch 45 deg, line 0.1 / spacing 0.5,
;           boundary 0.15                                    at  2, 9
;        F  cross-hatch 45 + 135 deg, the same lines         at  8, 9
;        G  solid shape, the reference                       at 14, 9
;        H  cross-hatch 0 + 90 deg, a round void r 0.8       at 20, 9
;
;      then two films holding that layer alone - S3D_SILKB with an
;      undefined line width of 0.05, S3D_SILKB0 with the default 0 - saves
;      the copy as <out>/silkcases.brd for the artwork batch and runs the
;      exporter into <out>. tools/silk_artwork.py runs all of it and
;      compares the films' Gerber with the intermediate; its CASES list
;      repeats the corners above.
;
;  Both write their progress, line by line, to <out>/<design>.silkfill.txt,
;  each line closed as it is written: the console reaches the runner's file
;  in blocks, and a session that stops shows nothing of where it stopped.
;
;  And for R2-5 of the 23.10.2026 review (round 117), objects the legend
;  converts to nothing or to less than they are:
;
;  s3dProbeSilkLost - read-only. The exporter's sweep of the silkscreen
;      layers and its converter on each object: one line per object with no
;      polygon or fewer polygons than strokes, a count per layer, into
;      <out>/<design>.silklost.txt.
;
;  s3dProbeStrokes - read-only. The exact form of that: every stroke of every
;      line and vectorised text converted on its own, over the silkscreen, the
;      drawn mask openings and the copper paths on ETCH (which share the
;      converter), one line per stroke that gives nothing, with what it is,
;      into <out>/<design>.strokes.txt.
;
;  s3dProbeLostCases - changes the SCRATCH COPY it runs on (my_test_board2):
;      draws one-arc paths, L's with such a corner and true-type texts, says
;      how each converts, saves <out>/lostcases.brd and exports it into <out>.
;
;    set S3D_PROBE_OUT=<folder>
;    python tools/run_probe.py --with-exporter tools/probes/probe_silkfill.il s3dProbeSilkFill input/<board>.brd
;    python tools/silk_artwork.py
;  REQUIRES: makeVariant3dIntermediates.il
;=====================================================================

S3D_ProbeCaseLayer = "BOARD GEOMETRY/SILKSCREEN_BOTTOM"
S3D_ProbeLog = nil

; The folder the results go to: S3D_PROBE_OUT, or the design's own.
procedure( s3dProbeOut()
    let( ( out )
        out = nil
        errset( out = getShellEnvVar( "S3D_PROBE_OUT" ) )
        unless( stringp( out ) && (out != "")  out = s3dDesignFolder() )
        out
    )
)

; One line to the console and to the progress file, which is opened and
; closed for it.
procedure( s3dProbeSay( t_line )
    let( ( port )
        printf( "%s\n" t_line )
        drain( poport )
        when( S3D_ProbeLog
            port = nil
            errset( port = outfile( S3D_ProbeLog "a" ) )
            when( port
                fprintf( port "%s\n" t_line )
                close( port )
            )
        )
        t
    )
)

; "path", "text", or the object type and its fill: "shape solid",
; "polygon unfilled" (an unfilled shape is objType "polygon": measured on
; my_test_board2's outline and keepins), "shape xhatch".
procedure( s3dProbeFillKind( o_dbid )
    let( ( f type )
        type = o_dbid->objType
        if( member( type list( "shape" "polygon" "rect" "frect" ) ) then
            f = nil
            errset( f = o_dbid->fill )
            strcat( type " "
                    cond(
                        ( f == t  "solid" )
                        ( null( f )  "unfilled" )
                        ( listp( f )  "xhatch" )
                        ( t  sprintf( nil "fill %L" f ) )
                    ) )
        else
            type
        )
    )
)

procedure( s3dProbeCount( g_table t_layer t_kind )
    let( ( key )
        key = strcat( t_layer " | " t_kind )
        g_table[key] = ( g_table[key] || 0 ) + 1
    )
)

procedure( s3dProbePrintTable( t_title g_table )
    let( ( keys )
        keys = sort( g_table->? 'alphalessp )
        s3dProbeSay( sprintf( nil "%s: %d key(s)" t_title length( keys ) ) )
        foreach( key keys
            s3dProbeSay( sprintf( nil "  %-60s %d" key g_table[key] ) )
        )
    )
)

procedure( s3dProbeDescribePolys( t_label l_polys )
    let( ( ( total 0.0 ) )
        foreach( p l_polys
            total = total + p->area
        )
        s3dProbeSay( sprintf( nil "    %s: %d poly(s), holes %d, area sum %.6f"
                              t_label length( l_polys )
                              length( setof( p l_polys p->isHole ) ) total ) )
        foreach( p l_polys
            s3dProbeSay( sprintf( nil "      area %.6f isHole %L nVert %d holes %d bBox %L"
                                  p->area p->isHole length( p->vertices ) length( p->holes ) p->bBox ) )
        )
    )
)

; What the exporter's own sweep returns on l_layers, counted by layer and
; kind; for each object that is not a path, a text or a solid shape, its
; attributes, what axlPolyFromDB makes of it whole, with ?xhatch t and
; segment by segment, and what s3dPolysFromDbid and s3dZeroWidth say.
procedure( s3dProbeSilkFillOn( l_layers )
    let( ( sweep elems layer kind widths plain hatched bySegment exporter zero ( nShown 0 ) )
        sweep = makeTable( "sweep" nil )
        elems = s3dSelectVisibleOn( l_layers list( "noall" "lines" "shapes" "text" )
                                    "probe_silkfill: no such layer: %s" )
        s3dProbeSay( sprintf( nil "sweep: %d object(s) on %d layer(s)" length( elems ) length( l_layers ) ) )
        foreach( elem elems
            layer = nil
            errset( layer = elem->layer )
            unless( stringp( layer )  layer = sprintf( nil "%L" layer ) )
            kind = s3dProbeFillKind( elem )
            s3dProbeCount( sweep layer kind )
            when( !member( kind list( "path" "text" "shape solid" ) ) && ( nShown < 40 )
                nShown = nShown + 1
                widths = nil
                errset( widths = foreach( mapcar seg elem->segments seg->width ) )
                s3dProbeSay( sprintf( nil "  %s %s isRect %L bBox %L fill %L" kind layer
                                      elem->isRect elem->bBox elem->fill ) )
                s3dProbeSay( sprintf( nil "    segments %d %L, widths %L, voids %d"
                                      length( elem->segments )
                                      foreach( mapcar seg elem->segments seg->objType )
                                      widths length( elem->voids ) ) )
                plain = nil
                hatched = nil
                bySegment = nil
                exporter = nil
                zero = 'unset
                errset( plain = axlPolyFromDB( elem ?endCapType 'ROUND ) )
                errset( hatched = axlPolyFromDB( elem ?endCapType 'ROUND ?xhatch t ) )
                foreach( seg elem->segments
                    errset( bySegment = append( bySegment axlPolyFromDB( seg ?endCapType 'ROUND ) ) )
                )
                errset( exporter = s3dPolysFromDbid( elem 'ROUND ) )
                errset( zero = s3dZeroWidth( elem ) )
                s3dProbeDescribePolys( "axlPolyFromDB" plain )
                s3dProbeDescribePolys( "axlPolyFromDB ?xhatch t" hatched )
                s3dProbeDescribePolys( "axlPolyFromDB per boundary segment" bySegment )
                s3dProbeDescribePolys( "s3dPolysFromDbid (the exporter)" exporter )
                s3dProbeSay( sprintf( nil "    s3dZeroWidth: %L" zero ) )
            )
        )
        s3dProbePrintTable( sprintf( nil "sweep (%d layer(s), the exporter's filter)" length( l_layers ) ) sweep )
        t
    )
)

; Every artwork film: its undefined line width - what the artwork draws a
; zero-width figure with - and its layers.
procedure( s3dProbeFilms()
    let( ( art film )
        art = nil
        errset( art = axlGetParam( "artwork" ) )
        s3dProbeSay( sprintf( nil "films: %L" when( art  art->groupMembers ) ) )
        when( art
            foreach( name art->groupMembers
                s3dProbeSay( sprintf( nil "  film %s ..." name ) )
                film = nil
                errset( film = axlGetParam( strcat( "artwork:" name ) ) )
                when( film
                    s3dProbeSay( sprintf( nil "  film %s: undefineLineWidth %L layers %L"
                                          name film->undefineLineWidth film->groupMembers ) )
                )
            )
        )
        s3dProbeSay( "films: done" )
    )
)

procedure( s3dProbeSilkFill()
    let( ( db layer kind w )
        S3D_ProbeLog = strcat( s3dProbeOut() "/" axlCurrentDesign() ".silkfill.txt" )
        s3dProbeSay( sprintf( nil "probe_silkfill on %s" axlCurrentDesign() ) )
        s3dProbeSilkFillOn( append( append( S3D_SilkDefaultTop S3D_SilkDefaultBottom )
                                    append( S3D_MaskDefaultTop S3D_MaskDefaultBottom ) ) )
        db = makeTable( "db" nil )
        foreach( shape axlDBGetShapes( nil )
            layer = nil
            errset( layer = shape->layer )
            unless( stringp( layer )  layer = sprintf( nil "%L" layer ) )
            kind = s3dProbeFillKind( shape )
            ; an unfilled shape's boundary width: 0 on every one made in round
            ; 111, and axlChangeWidth "does not support" changing it
            when( kind == "polygon unfilled"
                w = 0.0
                errset( foreach( seg shape->segments
                            when( seg->width > w  w = seg->width ) ) )
                when( w > 0.0  kind = sprintf( nil "%s, boundary up to %g" kind w ) )
            )
            s3dProbeCount( db layer kind )
        )
        s3dProbePrintTable( "db (axlDBGetShapes nil, every layer)" db )
        s3dProbeFilms()
        s3dProbeSay( "probe_silkfill: done" )
        t
    )
)

; R2-5 of the 23.10.2026 review (round 117): which silkscreen objects the
; exporter's own sweep finds and its own converter turns into no polygon, or
; into fewer than the object has strokes - read-only, the export's layers
; (S3D_SilkDefaultTop / Bottom, the shipped config's), one line per such
; object and a count per layer:
;   LOST     <layer> | <where> | <kind> | polys N | strokes S | error E
;   PARTIAL  the same, for a line with fewer polygons than segments or a text
;            with fewer than its vectorised strokes
;   LAYER    <layer> | objects N | zero width N | converted N | none N |
;            partial N | errors N | polygons N
procedure( s3dProbeSilkLostOn( l_layers )
    let( ( elems layer kind polys ok strokes lines nPolys counts row where zero )
        counts = makeTable( "lost" nil )
        elems = s3dSelectVisibleOn( l_layers list( "noall" "lines" "shapes" "text" )
                                    "probe_silkfill: no such layer: %s" )
        s3dProbeSay( sprintf( nil "lost: %d object(s) on %d layer(s)" length( elems ) length( l_layers ) ) )
        foreach( elem elems
            layer = nil
            errset( layer = elem->layer )
            unless( stringp( layer )  layer = sprintf( nil "%L" layer ) )
            unless( counts[layer]  counts[layer] = list( 0 0 0 0 0 0 0 ) )
            row = counts[layer]
            setcar( row car( row ) + 1 )
            kind = s3dProbeFillKind( elem )
            where = "?"
            errset( where = s3dDescribeObject( elem layer ) )
            zero = nil
            errset( zero = s3dZeroWidth( elem ) )
            if( zero then
                setcar( cdr( row ) cadr( row ) + 1 )
            else
                polys = nil
                ok = errset( polys = s3dPolysFromDbid( elem 'ROUND ) )
                nPolys = length( polys )
                ; what the object has to be drawn from: a line's segments, a
                ; vectorised text's strokes, else one
                strokes = 1
                cond(
                    ( elem->objType == "path"
                        errset( strokes = length( elem->segments ) ) )
                    ( (elem->objType == "text") && elem->textBlock
                        lines = nil
                        errset( lines = axlText2Lines( elem ) )
                        strokes = length( foreach( mapcan x lines x ) ) )
                )
                cond(
                    ( !ok
                        setcar( nthcdr( 5 row ) nth( 5 row ) + 1 )
                        s3dProbeSay( sprintf( nil "LOST %s | %s | %s | polys 0 | strokes %d | error t"
                                              layer where kind strokes ) ) )
                    ( nPolys == 0
                        setcar( nthcdr( 3 row ) nth( 3 row ) + 1 )
                        s3dProbeSay( sprintf( nil "LOST %s | %s | %s | polys 0 | strokes %d | error nil"
                                              layer where kind strokes ) ) )
                    ( nPolys < strokes
                        setcar( nthcdr( 4 row ) nth( 4 row ) + 1 )
                        setcar( nthcdr( 2 row ) nth( 2 row ) + 1 )
                        s3dProbeSay( sprintf( nil "PARTIAL %s | %s | %s | polys %d | strokes %d | error nil"
                                              layer where kind nPolys strokes ) ) )
                    ( t
                        setcar( nthcdr( 2 row ) nth( 2 row ) + 1 ) )
                )
                setcar( nthcdr( 6 row ) nth( 6 row ) + nPolys )
            )
        )
        foreach( key counts
            row = counts[key]
            s3dProbeSay( sprintf( nil "LAYER %s | objects %d | zero width %d | converted %d | none %d | partial %d | errors %d | polygons %d"
                                  key nth( 0 row ) nth( 1 row ) nth( 2 row ) nth( 3 row )
                                  nth( 4 row ) nth( 5 row ) nth( 6 row ) ) )
        )
        t
    )
)

procedure( s3dProbeSilkLost()
    S3D_ProbeLog = strcat( s3dProbeOut() "/" axlCurrentDesign() ".silklost.txt" )
    s3dProbeSay( sprintf( nil "probe_silkfill/lost on %s" axlCurrentDesign() ) )
    s3dProbeSilkLostOn( append( S3D_SilkDefaultTop S3D_SilkDefaultBottom ) )
    s3dProbeSay( "probe_silkfill/lost: done" )
    t
)

; What a stroke is, enough to see why it gives nothing: a database segment's
; kind, ends, width and chord, and an arc's centre, radius and sweep - a short
; chord is a tiny arc or an all but full circle; a text stroke's width and the
; end points of its pieces (an r_path keeps no start point to read).
procedure( s3dProbeStrokeText( g_stroke g_isText )
    let( ( se a b w segs pts dx dy text c r a1 a2 sweep cw ( pi 3.14159265358979 ) )
        if( g_isText then
            w = nil
            segs = nil
            errset( w = axlPathGetWidth( g_stroke ) )
            errset( segs = axlPathGetPathSegs( g_stroke ) )
            pts = nil
            foreach( p segs
                errset( pts = cons( axlPathSegGetEndPoint( p ) pts ) )
            )
            sprintf( nil "text stroke, %d piece(s) to %L | width %L" length( segs ) reverse( pts ) w )
        else
            se = nil
            w = nil
            errset( se = g_stroke->startEnd )
            errset( w = g_stroke->width )
            a = car( se )
            b = cadr( se )
            if( a && b then
                dx = xCoord( b ) - xCoord( a )
                dy = yCoord( b ) - yCoord( a )
                text = sprintf( nil "%s (%.4f, %.4f) -> (%.4f, %.4f) | width %L | chord %.6f"
                                g_stroke->objType xCoord( a ) yCoord( a ) xCoord( b ) yCoord( b ) w
                                sqrt( dx * dx + dy * dy ) )
                c = nil
                errset( c = g_stroke->xy )
                when( (g_stroke->objType == "arc") && c
                    cw = nil
                    errset( cw = g_stroke->isClockwise )
                    r = sqrt( (xCoord( a ) - xCoord( c )) * (xCoord( a ) - xCoord( c ))
                              + (yCoord( a ) - yCoord( c )) * (yCoord( a ) - yCoord( c )) )
                    a1 = atan2( yCoord( a ) - yCoord( c ) xCoord( a ) - xCoord( c ) )
                    a2 = atan2( yCoord( b ) - yCoord( c ) xCoord( b ) - xCoord( c ) )
                    sweep = if( cw  a1 - a2  a2 - a1 )
                    while( sweep < 0.0  sweep = sweep + 2.0 * pi )
                    text = sprintf( nil "%s | centre (%.4f, %.4f) | radius %.6f | clockwise %L | sweep %.4f deg | circle %L"
                                    text xCoord( c ) yCoord( c ) r cw sweep * 180.0 / pi
                                    g_stroke->isCircle )
                )
                text
            else
                sprintf( nil "%L, no ends | width %L" g_stroke->objType w )
            )
        )
    )
)

; Round 117, the exact form of the count above: stroke by stroke, as
; s3dPolysFromDbid converts them - a line's segments one at a time, a
; vectorised text's strokes with ?line2poly - since one stroke may give
; several polygons, and a count can then hide one that gave none. Over the
; silkscreen, the soldermask (the drawn openings' sweep) and the copper paths
; on ETCH, which reach s3dPolysFromDbid through s3dCopperPolys:
;   EMPTY    <layer> | <where> | stroke i of n | <what it is> | error t/nil
;   STROKES  <layer> | paths and texts N | strokes S | empty E | objects with one K
procedure( s3dProbeStrokesOn( l_layers l_filter )
    let( ( elems layer counts row strokes lines isText n res ok where hit )
        counts = makeTable( "strokes" nil )
        elems = s3dSelectVisibleOn( l_layers l_filter "probe_silkfill: no such layer: %s" )
        foreach( elem elems
            isText = (elem->objType == "text") && elem->textBlock
            when( isText || (elem->objType == "path")
                layer = nil
                errset( layer = elem->layer )
                unless( stringp( layer )  layer = sprintf( nil "%L" layer ) )
                unless( counts[layer]  counts[layer] = list( 0 0 0 0 ) )
                row = counts[layer]
                setcar( row car( row ) + 1 )
                strokes = nil
                if( isText then
                    lines = nil
                    errset( lines = axlText2Lines( elem ) )
                    strokes = foreach( mapcan x lines x )
                else
                    errset( strokes = elem->segments )
                )
                where = "?"
                errset( where = s3dDescribeObject( elem layer ) )
                n = 0
                hit = nil
                foreach( s strokes
                    n = n + 1
                    res = nil
                    ok = errset( res = if( isText
                                           axlPolyFromDB( s ?endCapType 'ROUND ?line2poly t )
                                           axlPolyFromDB( s ?endCapType 'ROUND ) ) )
                    unless( ok && res
                        hit = t
                        setcar( nthcdr( 2 row ) nth( 2 row ) + 1 )
                        s3dProbeSay( sprintf( nil "EMPTY %s | %s | stroke %d of %d | %s | error %L"
                                              layer where n length( strokes )
                                              s3dProbeStrokeText( s isText ) !ok ) )
                    )
                )
                setcar( cdr( row ) cadr( row ) + n )
                when( hit  setcar( nthcdr( 3 row ) nth( 3 row ) + 1 ) )
            )
        )
        foreach( key counts
            row = counts[key]
            s3dProbeSay( sprintf( nil "STROKES %s | paths and texts %d | strokes %d | empty %d | objects with one %d"
                                  key nth( 0 row ) nth( 1 row ) nth( 2 row ) nth( 3 row ) ) )
        )
        t
    )
)

procedure( s3dProbeStrokes()
    S3D_ProbeLog = strcat( s3dProbeOut() "/" axlCurrentDesign() ".strokes.txt" )
    s3dProbeSay( sprintf( nil "probe_silkfill/strokes on %s" axlCurrentDesign() ) )
    s3dProbeSay( "-- silkscreen" )
    s3dProbeStrokesOn( append( S3D_SilkDefaultTop S3D_SilkDefaultBottom )
                       list( "noall" "lines" "shapes" "text" ) )
    s3dProbeSay( "-- soldermask, the drawn openings" )
    s3dProbeStrokesOn( append( S3D_MaskDefaultTop S3D_MaskDefaultBottom )
                       list( "noall" "lines" "shapes" "text" ) )
    s3dProbeSay( "-- copper paths" )
    s3dProbeStrokesOn( list( "ETCH/TOP" "ETCH/BOTTOM" ) list( "noall" "lines" "clines" ) )
    s3dProbeSay( "probe_silkfill/strokes: done" )
    t
)

;---------------------------------------------------------------------
;  The cases
;---------------------------------------------------------------------

procedure( s3dProbeSquare( x0 y0 f_width )
    axlPathStart( list( x0:y0 ( x0 + 4.0 ):y0 ( x0 + 4.0 ):( y0 + 4.0 ) x0:( y0 + 4.0 ) x0:y0 ) f_width )
)

procedure( s3dProbeMade( t_name g_result )
    let( ( dbid )
        dbid = if( listp( g_result ) car( g_result ) g_result )
        s3dProbeSay( sprintf( nil "case %s: %L objType %L fill %L" t_name dbid
                              when( dbid  dbid->objType ) when( dbid  dbid->fill ) ) )
        dbid
    )
)

procedure( s3dProbeSilkCases()
    let( ( out layer shape made saved hatch45 hatch135 hatch0 hatch90 )
        out = s3dProbeOut()
        S3D_ProbeLog = strcat( out "/silkcases.silkfill.txt" )
        layer = S3D_ProbeCaseLayer
        hatch45  = make_axlFill( ?origin 0.0:0.0 ?angle 45.0  ?width 0.1 ?spacing 0.5 )
        hatch135 = make_axlFill( ?origin 0.0:0.0 ?angle 135.0 ?width 0.1 ?spacing 0.5 )
        hatch0   = make_axlFill( ?origin 0.0:0.0 ?angle 0.0   ?width 0.1 ?spacing 0.5 )
        hatch90  = make_axlFill( ?origin 0.0:0.0 ?angle 90.0  ?width 0.1 ?spacing 0.5 )

        made = nil
        errset( made = axlDBCreateRectangle( list( 2.0:2.0 6.0:6.0 ) nil layer ) )
        s3dProbeMade( "A unfilled rectangle" made )
        made = nil
        errset( made = axlDBCreateShape( s3dProbeSquare( 8.0 2.0 0.2 ) nil layer ) )
        s3dProbeMade( "B unfilled, width 0.2" made )
        made = nil
        errset( made = axlDBCreateShape( s3dProbeSquare( 14.0 2.0 0.0 ) nil layer ) )
        s3dProbeMade( "C unfilled, width 0" made )
        made = nil
        errset( made = axlDBCreateShape( axlPathStartCircle( list( 22.0:4.0 2.0 ) 0.15 ) nil layer ) )
        s3dProbeMade( "D unfilled circle, width 0.15" made )
        shape = nil
        errset( shape = axlDBCreateOpenShape( s3dProbeSquare( 8.0 15.0 0.2 ) nil layer ) )
        when( shape  errset( axlDBCreateCloseShape( shape ) ) )
        s3dProbeMade( "B2 unfilled, width 0.2, open and close" shape )
        made = nil
        errset( made = axlDBCreateShape( s3dProbeSquare( 2.0 9.0 0.15 ) list( hatch45 ) layer ) )
        s3dProbeMade( "E cross-hatch 45" made )
        made = nil
        errset( made = axlDBCreateShape( s3dProbeSquare( 8.0 9.0 0.15 ) list( hatch45 hatch135 ) layer ) )
        s3dProbeMade( "F cross-hatch 45+135" made )
        made = nil
        errset( made = axlDBCreateShape( s3dProbeSquare( 14.0 9.0 0.0 ) t layer ) )
        s3dProbeMade( "G solid" made )
        shape = nil
        errset( shape = axlDBCreateOpenShape( s3dProbeSquare( 20.0 9.0 0.15 ) list( hatch0 hatch90 ) layer ) )
        when( shape
            errset( axlDBCreateVoidCircle( shape list( 22.0:11.0 0.8 ) 0.15 ) )
            errset( axlDBCreateCloseShape( shape ) )
        )
        s3dProbeMade( "H cross-hatch 0+90, void" shape )

        s3dProbeSay( sprintf( nil "film S3D_SILKB: %L"
                              axlFilmCreate( "S3D_SILKB" ?undefineLineWidth 0.05 ?layers list( layer ) ) ) )
        s3dProbeSay( sprintf( nil "film S3D_SILKB0: %L"
                              axlFilmCreate( "S3D_SILKB0" ?layers list( layer ) ) ) )

        s3dProbeSilkFillOn( list( layer ) )

        saved = axlSaveDesign( ?design strcat( out "/silkcases" ) ?mode "nocheck" ?noMru t ?noConfirm t )
        s3dProbeSay( sprintf( nil "saved: %L" saved ) )
        makeVariant3dIntermediates( out nil )
        s3dProbeSay( "probe_silkcases: done" )
        t
    )
)

; One made object: what it is, and how axlPolyFromDB whole and the exporter's
; converter answer for it. axlDBCreatePath and axlDBCreateText answer
; ( l_dbids g_drc ): the dbid is the first of the first.
procedure( s3dProbeLostMade( t_name g_result )
    let( ( dbid whole conv ok attrs )
        dbid = if( listp( g_result ) car( g_result ) g_result )
        when( listp( dbid )  dbid = car( dbid ) )
        if( dbid then
            whole = nil
            conv = nil
            attrs = nil
            errset( whole = axlPolyFromDB( dbid ?endCapType 'ROUND ) )
            ok = errset( conv = s3dPolysFromDbid( dbid 'ROUND ) )
            errset( attrs = dbid->?? )
            s3dProbeSay( sprintf( nil "case %s: %s | axlPolyFromDB whole %d | s3dPolysFromDbid %s %d"
                                  t_name s3dDescribeObject( dbid dbid->layer ) length( whole )
                                  if( ok "ok" "error" ) length( conv ) ) )
            s3dProbeSay( sprintf( nil "  attributes %L" attrs ) )
        else
            s3dProbeSay( sprintf( nil "case %s: not made (%L)" t_name g_result ) )
        )
        dbid
    )
)

; A text in a true-type style, each way the reference offers to make one: the
; style named as the third argument, on the bottom and the top, or in an
; axlTextOrientation, and a vector text beside them as the control. The
; style's height is in USER units, whatever its page says ("in database
; units"): at 15000 for 1.5 mm, Allegro 25.1 made the style and refused the
; text, "Text line is outside of the extents" (round 117).
procedure( s3dProbeTrueType( t_layer )
    let( ( made orient top )
        top = "BOARD GEOMETRY/SILKSCREEN_TOP"
        ; nil for the list of them: the page's "no arguments" is refused,
        ; "too few arguments (1 expected, 0 given)"
        s3dProbeSay( sprintf( nil "text styles: %L" axlDBGetTextStyle( nil ) ) )
        made = nil
        errset( made = axlDBCreateText( "VF 18" 12.0:20.0 "1" t_layer nil ) )
        s3dProbeLostMade( "M0 vector text, block 1 (the control)" made )
        foreach( style list( "S3D_TT" )
            made = nil
            errset( made = axlDBCreateText( "TT 18" 3.0:20.0 style t_layer nil ) )
            s3dProbeLostMade( sprintf( nil "M1 %s by name, bottom" style ) made )
            made = nil
            errset( made = axlDBCreateText( "TT 18" 3.0:21.5 style top nil ) )
            s3dProbeLostMade( sprintf( nil "M2 %s by name, top" style ) made )
            orient = nil
            errset( orient = make_axlTextOrientation( ?textBlock "1" ?rotation 0.0 ?mirrored nil
                                                      ?justify "left" ?textStyle style ) )
            made = nil
            when( orient  errset( made = axlDBCreateText( "TT 18" 20.0:20.0 orient t_layer nil ) ) )
            s3dProbeLostMade( sprintf( nil "M3 %s in an orientation, bottom" style ) made )
        )
    )
)

; R2-5 of the 23.10.2026 review (round 117): objects the legend cannot
; convert, made on a scratch copy, since none of the nine boards has one
; (s3dProbeSilkLost, s3dProbeStrokes). On S3D_ProbeCaseLayer, empty on
; my_test_board2, 0.3 wide:
;   K1 K2 K5  a path that is one quarter arc of radius 1, 2, 5 database
;             units, alone - the stroke flex3-a0 has in its copper
;             (ETCH/BOTTOM at 4.960, 3.830)            at 3, 6, 9 / 17
;   L1 L2 L5  the same arc as the corner of an L, 2 along and 2 up
;                                                      at 12, 16, 20 / 16
;   M         a text in a true-type text style, Arial  at 3 / 20
; then the exporter's own sweep over the layer, stroke by stroke too, saves
; the copy as <out>/lostcases.brd and runs the exporter into <out>.
procedure( s3dProbeLostCases()
    let( ( out layer units u x r path made style saved )
        out = s3dProbeOut()
        S3D_ProbeLog = strcat( out "/lostcases.lost.txt" )
        layer = S3D_ProbeCaseLayer
        units = axlDBGetDesignUnits()
        u = 1.0 / float( caddr( units ) )
        s3dProbeSay( sprintf( nil "design units %L: one database unit is %g" units u ) )

        x = 3.0
        foreach( n list( 1 2 5 )
            r = n * u
            path = axlPathStart( list( ( x + r ):17.0 ) 0.3 )
            when( path  path = axlPathArcCenter( path 0.3 x:( 17.0 + r ) nil x:17.0 ) )
            made = nil
            when( path  errset( made = axlDBCreatePath( path layer ) ) )
            s3dProbeLostMade( sprintf( nil "K%d lone arc, radius %g" n r ) made )
            x = x + 3.0
        )

        x = 12.0
        foreach( n list( 1 2 5 )
            r = n * u
            path = axlPathStart( list( x:16.0 ( x + 2.0 ):16.0 ) 0.3 )
            when( path
                path = axlPathArcCenter( path 0.3 ( x + 2.0 + r ):( 16.0 + r ) nil ( x + 2.0 ):( 16.0 + r ) )
            )
            when( path  path = axlPathLine( path 0.3 ( x + 2.0 + r ):18.0 ) )
            made = nil
            when( path  errset( made = axlDBCreatePath( path layer ) ) )
            s3dProbeLostMade( sprintf( nil "L%d corner arc, radius %g" n r ) made )
            x = x + 4.0
        )

        style = nil
        errset( style = axlDBCreateTextStyle( "S3D_TT" "Arial" 1.5 2.0 100 ) )
        s3dProbeSay( sprintf( nil "style S3D_TT: %L | %L" style
                              when( style  axlDBGetTextStyleCharacteristics( style ) ) ) )
        when( style  s3dProbeTrueType( layer ) )

        s3dProbeSay( "-- the exporter's sweep" )
        s3dProbeSilkLostOn( list( layer ) )
        s3dProbeSay( "-- stroke by stroke" )
        s3dProbeStrokesOn( list( layer ) list( "noall" "lines" "shapes" "text" ) )

        saved = axlSaveDesign( ?design strcat( out "/lostcases" ) ?mode "nocheck" ?noMru t ?noConfirm t )
        s3dProbeSay( sprintf( nil "saved: %L" saved ) )
        makeVariant3dIntermediates( out nil )
        s3dProbeSay( "probe_lostcases: done" )
        t
    )
)
