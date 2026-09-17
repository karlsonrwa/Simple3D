;=====================================================================
;  probe_openings.il - DIAGNOSTIC ONLY. Reads the design, changes nothing.
;
;  The drawn mask openings of the TOP side one by one - what each is (its
;  objType, width, box), what the exporter's own pieces make of it
;  (s3dPolysFromDbid, s3dSelectInBox with the exporter's visibility set-up,
;  s3dCopperPolys) and what the AND leaves - so an opening that exposes no
;  copper can be told apart from one the sweep missed.
;
;  Every line is drained to the console at once, and the runner writes the
;  console straight to its file: a session that hangs still says where.
;  s3dProbeOpenings0 prints one line and returns - the load and the
;  session on their own, when the real probe is suspected of hanging.
;
;  Needs the exporter loaded:
;    python tools/run_probe.py --with-exporter tools/probes/probe_openings.il s3dProbeOpenings BOARD.brd
;  REQUIRES: makeVariant3dIntermediates.il
;=====================================================================

procedure( s3dProbeOpeningsSay( t_line )
    printf( "%s\n" t_line )
    drain( poport )
)

procedure( s3dProbeOpenings0()
    s3dProbeOpeningsSay( sprintf( nil "probe_openings: hello from %L" axlCurrentDesign() ) )
    t
)

procedure( s3dProbeOpenings()
    let( ( elems polys found copper res saveVis saveEnabled saveOn filter w lay ( n 0 ) line )
        s3dProbeOpeningsSay( "probe_openings: sweeping the mask layers" )
        elems = s3dSelectVisibleOn( list( "BOARD GEOMETRY/SOLDERMASK_TOP" "PACKAGE GEOMETRY/SOLDERMASK_TOP" )
                                    list( "noall" "lines" "shapes" ) "probe: no such layer: %s" )
        s3dProbeOpeningsSay( sprintf( nil "===== %d drawn opening object(s) on TOP =====" length( elems ) ) )
        saveVis     = axlVisibleGet()
        saveEnabled = axlGetFindFilter( t )
        saveOn      = axlGetFindFilter( nil )
        filter = list( "noall" "clines" "shapes" "pins" "vias" )
        axlVisibleDesign( nil )
        axlVisibleLayer( "ETCH/TOP" t )
        errset( axlVisibleLayer( "PIN/TOP" t ) )
        errset( axlVisibleLayer( "VIA CLASS/TOP" t ) )
        axlSetFindFilter( ?enabled filter ?onButtons filter )
        s3dProbeOpeningsSay( "probe_openings: visibility set, walking the openings" )
        foreach( e elems
            n = n + 1
            when( n <= 60
                w = nil
                errset( w = e->width )
                lay = nil
                errset( lay = e->layer )
                polys = nil
                errset( polys = s3dPolysFromDbid( e 'ROUND ) )
                polys = remd( nil polys )
                line = sprintf( nil "  #%d %L on %L width %L bBox %L -> %d poly(s)" n e->objType lay w e->bBox length( polys ) )
                foreach( p polys
                    found = s3dSelectInBox( p->bBox )
                    copper = nil
                    foreach( o found
                        copper = append( copper s3dCopperPolys( o "ETCH/TOP" p->bBox 'ROUND ) )
                    )
                    res = nil
                    when( copper
                        errset( res = axlPolyOperation( list( p ) copper 'AND ) )
                    )
                    line = strcat( line sprintf( nil " | opening area %L: %d object(s) in box (%s), %d copper poly(s), AND -> %d"
                                                 p->area length( found )
                                                 buildString( mapcar( lambda( (o) o->objType ) found ) "," )
                                                 length( copper ) length( remd( nil res ) ) ) )
                )
                s3dProbeOpeningsSay( line )
            )
        )
        errset( axlVisibleSet( saveVis ) )
        when( saveEnabled || saveOn
            errset( axlSetFindFilter( ?enabled saveEnabled ?onButtons remove( "DYNTHEMALS" saveOn ) ) )
        )
        s3dProbeOpeningsSay( "===== done =====" )
        t
    )
)
