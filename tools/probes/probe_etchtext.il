;=====================================================================
;  probe_etchtext.il - DIAGNOSTIC ONLY. Reads the design, changes nothing.
;
;  Copper drawn as LINES on ETCH/TOP that belong to no net - a label written
;  in copper under a mask opening - and how Allegro's selection hands them
;  over: which find-filter names pick them up inside a box, what objType and
;  ->net they carry, and whether the exporter's s3dCopperPolys converts
;  them. Written after the exporter's opening sweep found "no copper object"
;  under the 51 label strokes of my_test_board2 while the user's F4 showed
;  a LINE SEGMENT on ETCH/TOP there.
;
;  Every line is drained to the console at once; the runner writes the
;  console straight to its file.
;
;  Needs the exporter loaded:
;    python tools/run_probe.py --with-exporter tools/probes/probe_etchtext.il s3dProbeEtchText BOARD.brd
;  REQUIRES: makeVariant3dIntermediates.il
;=====================================================================

procedure( s3dProbeEtchTextSay( t_line )
    printf( "%s\n" t_line )
    drain( poport )
)

; One object, one line: what it is, where, on what net.
procedure( s3dProbeEtchTextDescribe( o_obj )
    let( ( lay net w par )
        lay = nil  errset( lay = o_obj->layer )
        net = nil  errset( net = o_obj->net->name )
        w = nil    errset( w = o_obj->width )
        par = nil  errset( par = o_obj->parent->objType )
        sprintf( nil "%L layer %L net %L width %L parent %L bBox %L"
                 o_obj->objType lay net w par o_obj->bBox )
    )
)

procedure( s3dProbeEtchText()
    let( ( saveVis saveEnabled saveOn box filters elems polys ( n 0 ) )
        ; the band the label's mask openings occupy on my_test_board2
        box = list( 0.8:19.8 11.3:21.4 )
        saveVis     = axlVisibleGet()
        saveEnabled = axlGetFindFilter( t )
        saveOn      = axlGetFindFilter( nil )
        axlVisibleDesign( nil )
        axlVisibleLayer( "ETCH/TOP" t )
        s3dProbeEtchTextSay( "probe_etchtext: ETCH/TOP visible alone; selecting the label band with each filter" )
        filters = list( list( "noall" "clines" )
                        list( "noall" "lines" )
                        list( "noall" "cline segs" )
                        list( "noall" "line segs" )
                        list( "noall" "shapes" )
                        list( "noall" "text" )
                        list( "noall" "lines" "clines" "shapes" "pins" "vias" "text" ) )
        foreach( f filters
            axlClearSelSet()
            elems = nil
            when( errset( axlSetFindFilter( ?enabled f ?onButtons f ) )
                when( errset( axlAddSelectBox( box ) t )
                    elems = axlGetSelSet()
                )
            )
            axlClearSelSet()
            s3dProbeEtchTextSay( sprintf( nil "===== filter %L: %d object(s) in the band =====" cdr( f ) length( elems ) ) )
            n = 0
            foreach( e elems
                n = n + 1
                when( n <= 6
                    polys = nil
                    errset( polys = s3dCopperPolys( e "ETCH/TOP" box 'ROUND ) )
                    s3dProbeEtchTextSay( sprintf( nil "  #%d %s -> s3dCopperPolys %d poly(s)%s"
                                                  n s3dProbeEtchTextDescribe( e ) length( remd( nil polys ) )
                                                  if( polys then sprintf( nil ", first area %L" car( polys )->area ) else "" ) ) )
                )
            )
        )
        ; the whole layer, so the count of no-net copper is known
        axlClearSelSet()
        elems = nil
        axlSetFindFilter( ?enabled list( "noall" "lines" "clines" ) ?onButtons list( "noall" "lines" "clines" ) )
        when( errset( axlAddSelectAll() t )
            elems = axlGetSelSet()
        )
        axlClearSelSet()
        n = 0
        foreach( e elems
            unless( e->net  n = n + 1 )
        )
        s3dProbeEtchTextSay( sprintf( nil "===== ETCH/TOP whole: %d line/cline object(s), %d of them on no net =====" length( elems ) n ) )
        n = 0
        foreach( e elems
            unless( e->net
                n = n + 1
                when( n <= 4
                    s3dProbeEtchTextSay( sprintf( nil "  no-net #%d %s" n s3dProbeEtchTextDescribe( e ) ) )
                )
            )
        )
        errset( axlVisibleSet( saveVis ) )
        when( saveEnabled || saveOn
            errset( axlSetFindFilter( ?enabled saveEnabled ?onButtons remove( "DYNTHEMALS" saveOn ) ) )
        )
        s3dProbeEtchTextSay( "===== done =====" )
        t
    )
)
