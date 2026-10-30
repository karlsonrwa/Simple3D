;=====================================================================
;  probe_silkfill.il - DIAGNOSTIC for R2-13 of the 28.10.2026 review
;  (round 111): what becomes of a shape's `fill` - nil an unfilled shape,
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
