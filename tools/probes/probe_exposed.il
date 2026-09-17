;=====================================================================
;  probe_exposed.il - DIAGNOSTIC ONLY. Reads the design, changes nothing.
;
;  s3dCollectExposed's own sweep, opening by opening and object by object,
;  with the exporter's find filter and visibility - what was selected in
;  each opening's box, what s3dCopperPolys made of each object, and the
;  area the AND and the ANDNOT leave. probe_openings answers "did the
;  sweep see anything"; this answers "which object's copper went missing",
;  which is the question a pour that vanished asks.
;
;  Needs the exporter loaded:
;    python tools/run_probe.py --with-exporter tools/probes/probe_exposed.il s3dProbeExposed BOARD.brd
;  REQUIRES: makeVariant3dIntermediates.il
;=====================================================================

procedure( s3dProbeExposedSay( t_line )
    printf( "%s\n" t_line )
    drain( poport )
)

; Total area of the non-hole polygons of a list, as a number.
procedure( s3dProbeExposedArea( l_polys )
    let( ( ( total 0.0 ) )
        foreach( p remd( nil l_polys )
            when( p && !p->isHole
                total = total + p->area
            )
        )
        total
    )
)

; One object in a sentence: what it is, what net it is on, how big it is.
procedure( s3dProbeExposedWhat( o_obj )
    let( ( ty net lay dyn area )
        ty = nil
        errset( ty = o_obj->objType )
        net = nil
        errset( net = o_obj->net->name )
        lay = nil
        errset( lay = o_obj->layer )
        dyn = nil
        errset( dyn = o_obj->isDynamic )
        area = nil
        errset( area = o_obj->area )
        sprintf( nil "%L net=%L layer=%L dynamic=%L area=%L" ty net lay dyn area )
    )
)

procedure( s3dProbeExposed( @optional ( t_side "TOP" ) )
    let( ( etch pinLayer viaLayer maskLayers elems openings polys zero key
           saveVis saveEnabled saveOn filter found copper one res bare
           ( n 0 ) line )
        etch     = strcat( "ETCH/" t_side )
        pinLayer = strcat( "PIN/" t_side )
        viaLayer = strcat( "VIA CLASS/" t_side )
        maskLayers = list( strcat( "BOARD GEOMETRY/SOLDERMASK_" t_side )
                           strcat( "PACKAGE GEOMETRY/SOLDERMASK_" t_side ) )
        s3dProbeExposedSay( sprintf( nil "probe_exposed: %s, mask layers %L" t_side maskLayers ) )

        ; Everything on the side's etch, before any of the sweep runs: the
        ; inventory the sweep has to find, so a missing object can be told
        ; from a missing conversion.
        elems = s3dSelectVisibleOn( list( etch ) list( "noall" "lines" "clines" "shapes" )
                                    "probe: no such layer: %s" )
        s3dProbeExposedSay( sprintf( nil "===== %d object(s) on %s =====" length( elems ) etch ) )
        foreach( e elems
            n = n + 1
            when( n <= 40
                polys = nil
                errset( polys = s3dPolysFromDbid( e 'ROUND ) )
                s3dProbeExposedSay( sprintf( nil "  obj #%d %s bBox %L -> %d poly(s), area %L"
                                             n s3dProbeExposedWhat( e ) e->bBox
                                             length( remd( nil polys ) )
                                             s3dProbeExposedArea( polys ) ) )
            )
        )

        ; The openings, exactly as s3dCollectExposed builds them.
        elems = s3dSelectVisibleOn( maskLayers list( "noall" "lines" "shapes" "text" )
                                    "probe: no such layer: %s" )
        openings = nil
        foreach( elem elems
            key = nil
            errset( key = elem->layer )
            zero = nil
            errset( zero = s3dZeroWidth( elem ) )
            polys = nil
            unless( zero  errset( polys = s3dPolysFromDbid( elem 'ROUND ) ) )
            foreach( poly polys
                when( poly && !poly->isHole
                    openings = cons( list( key poly ) openings )
                )
            )
        )
        openings = reverse( openings )
        s3dProbeExposedSay( sprintf( nil "===== %d opening polygon(s) on the %s mask ====="
                                     length( openings ) t_side ) )

        saveVis     = axlVisibleGet()
        saveEnabled = axlGetFindFilter( t )
        saveOn      = axlGetFindFilter( nil )
        filter = list( "noall" "lines" "clines" "shapes" "pins" "vias" )
        axlVisibleDesign( nil )
        axlVisibleLayer( etch t )
        errset( axlVisibleLayer( pinLayer t ) )
        errset( axlVisibleLayer( viaLayer t ) )
        axlSetFindFilter( ?enabled filter ?onButtons filter )

        n = 0
        foreach( entry openings
            n = n + 1
            when( n <= 30
                found = s3dSelectInBox( cadr( entry )->bBox )
                s3dProbeExposedSay( sprintf( nil "  opening #%d area %L bBox %L: %d object(s) in box"
                                             n cadr( entry )->area cadr( entry )->bBox
                                             length( found ) ) )
                copper = nil
                foreach( o found
                    one = s3dCopperPolys( o etch cadr( entry )->bBox 'ROUND )
                    copper = append( copper one )
                    s3dProbeExposedSay( sprintf( nil "      %s -> %d poly(s), area %L"
                                                 s3dProbeExposedWhat( o )
                                                 length( remd( nil one ) )
                                                 s3dProbeExposedArea( one ) ) )
                )
                res = nil
                bare = nil
                when( copper
                    errset( res = axlPolyOperation( list( cadr( entry ) ) copper 'AND ) )
                    errset( bare = axlPolyOperation( list( cadr( entry ) ) copper 'ANDNOT ) )
                )
                line = sprintf( nil "    => copper polys %d area %L | AND %d poly(s) area %L | ANDNOT %d poly(s) area %L"
                                length( remd( nil copper ) ) s3dProbeExposedArea( copper )
                                length( remd( nil res ) ) s3dProbeExposedArea( res )
                                length( remd( nil bare ) ) s3dProbeExposedArea( bare ) )
                s3dProbeExposedSay( line )
            )
        )

        errset( axlVisibleSet( saveVis ) )
        when( saveEnabled || saveOn
            errset( axlSetFindFilter( ?enabled saveEnabled
                                      ?onButtons remove( "DYNTHEMALS" saveOn ) ) )
        )
        s3dProbeExposedSay( "===== done =====" )
        t
    )
)

; s3dCollectExposed itself, not a copy of its steps: what the exporter is
; actually handed to write. A polygon that the sweep computes and the file
; does not carry has to be lost in one of the two, and this says which.
procedure( s3dProbeExposedReal( @optional ( t_side "TOP" ) )
    let( ( maskLayers res ( n 0 ) vtx holes )
        maskLayers = list( strcat( "BOARD GEOMETRY/SOLDERMASK_" t_side )
                           strcat( "PACKAGE GEOMETRY/SOLDERMASK_" t_side ) )
        s3dProbeExposedSay( sprintf( nil "probe_exposed: s3dCollectExposed( %L %L )" maskLayers t_side ) )
        res = s3dCollectExposed( maskLayers t_side 'ROUND )
        foreach( half list( list( "copper" car( res ) ) list( "bare" cadr( res ) ) )
            foreach( group cadr( half )
                s3dProbeExposedSay( sprintf( nil "===== %s group %L: %d polygon(s) ====="
                                             car( half ) car( group )
                                             length( cadr( group ) ) ) )
                n = 0
                foreach( p cadr( group )
                    n = n + 1
                    when( n <= 40
                        vtx = nil
                        errset( vtx = length( p->points ) )
                        holes = nil
                        errset( holes = length( p->holes ) )
                        s3dProbeExposedSay(
                            sprintf( nil "   #%d area %L isHole %L points %L holes %L bBox %L"
                                     n p->area p->isHole vtx holes p->bBox ) )
                    )
                )
            )
        )
        s3dProbeExposedSay( "===== done =====" )
        t
    )
)

; The sweep's polygons through the WRITER, into a file of their own: what
; s3dCollectExposed found on one line each, then the JSON s3dWriteSilkPolys
; makes of the same list. A polygon the sweep has and the file has not is
; then a fault of the writer and of nothing else.
procedure( s3dProbeExposedWrite( @optional ( t_side "TOP" ) )
    let( ( maskLayers res port ( n 0 ) path )
        maskLayers = list( strcat( "BOARD GEOMETRY/SOLDERMASK_" t_side )
                           strcat( "PACKAGE GEOMETRY/SOLDERMASK_" t_side ) )
        res = s3dCollectExposed( maskLayers t_side 'ROUND )
        foreach( group car( res )
            n = 0
            foreach( p cadr( group )
                n = n + 1
                s3dProbeExposedSay( sprintf( nil "sweep #%d area %L holes %L"
                                             n p->area length( p->holes ) ) )
            )
        )
        ; A plain relative name: the runner works in a scratch folder of its
        ; own, and ALLEGRO_TEMP reads nil in a headless session - strcat on
        ; which is an error BEFORE any fallback below it can run.
        path = "./probe_exposed_write.json"
        port = outfile( path "w" )
        when( port
            fprintf( port "[\n" )
            s3dWriteSilkPolys( port car( res ) )
            fprintf( port "\n]\n" )
            close( port )
            s3dProbeExposedSay( sprintf( nil "wrote %s" path ) )
            foreach( line parseString( s3dProbeExposedSlurp( path ) "\n" )
                s3dProbeExposedSay( strcat( "JSON| " line ) )
            )
        )
        s3dProbeExposedSay( "===== done =====" )
        t
    )
)

; A whole text file as one string - only so the written JSON reaches the
; probe's own console, which is the only thing the runner keeps.
procedure( s3dProbeExposedSlurp( t_path )
    let( ( port ( out "" ) line )
        port = infile( t_path )
        when( port
            while( gets( line port )
                out = strcat( out line )
            )
            close( port )
        )
        out
    )
)

; The same sweep, but reached the way the export reaches it - through
; s3dCollectPads, after the pin and via walk. The sweep on its own finds
; the pour; if this one does not, what changed it is upstream, in the
; padstack collection, and not in the sweep at all.
procedure( s3dProbeExposedViaPads()
    let( ( res exposedTop ( n 0 ) )
        s3dProbeExposedSay( "probe_exposed: s3dCollectPads( maskTop maskBottom 'ROUND )" )
        res = s3dCollectPads( list( "BOARD GEOMETRY/SOLDERMASK_TOP" "PACKAGE GEOMETRY/SOLDERMASK_TOP" )
                              list( "BOARD GEOMETRY/SOLDERMASK_BOTTOM" "PACKAGE GEOMETRY/SOLDERMASK_BOTTOM" )
                              'ROUND )
        exposedTop = nth( 3 res )
        foreach( group car( exposedTop )
            s3dProbeExposedSay( sprintf( nil "===== copper group %L: %d polygon(s) ====="
                                         car( group ) length( cadr( group ) ) ) )
            n = 0
            foreach( p cadr( group )
                n = n + 1
                s3dProbeExposedSay( sprintf( nil "   #%d area %L holes %L bBox %L"
                                             n p->area length( p->holes ) p->bBox ) )
            )
        )
        s3dProbeExposedSay( "===== done =====" )
        t
    )
)

; The sweep after each stage of the export that runs BEFORE it, so the one
; that changes what it sees can be named. Stage: 0 nothing, 1 the board
; thickness, 2 the contour, 3 the silkscreen. Same call at the end every
; time - the pour's 67.5 mm2 polygon is either there or it is not.
procedure( s3dProbeExposedAfter( @optional ( x_stage 3 ) )
    let( ( cfg silk state res exposedTop ( n 0 ) )
        state = makeTable( "s3dProbeState" nil )
        state['shapes] = nil
        state['bendLines] = nil
        state['silkWarnings] = nil
        state['warnings] = nil
        state['mechSeq] = 0
        cfg = s3dSilkConfig( nil )
        s3dProbeExposedSay( sprintf( nil "probe_exposed: stage %d; maskTop from the config = %L"
                                     x_stage nth( 7 cfg ) ) )
        when( x_stage >= 1
            s3dProbeExposedSay( sprintf( nil "  thickness -> %L" s3dBoardThickness() ) )
        )
        when( x_stage >= 2
            s3dProbeExposedSay( sprintf( nil "  contour -> %d loop(s)"
                                         length( makePcbContour( axlDBGetDesign() ) ) ) )
        )
        when( x_stage >= 3
            silk = nil
            errset( silk = s3dMakeSilkscreen( cfg state ) t )
            s3dProbeExposedSay( sprintf( nil "  silkscreen -> %L" if( silk then "built" else "nil" ) ) )
        )
        res = s3dCollectPads( nth( 7 cfg ) nth( 8 cfg ) nth( 4 cfg ) )
        exposedTop = nth( 3 res )
        foreach( group car( exposedTop )
            s3dProbeExposedSay( sprintf( nil "===== copper group %L: %d polygon(s) ====="
                                         car( group ) length( cadr( group ) ) ) )
            n = 0
            foreach( p cadr( group )
                n = n + 1
                when( n <= 6
                    s3dProbeExposedSay( sprintf( nil "   #%d area %L holes %L bBox %L"
                                                 n p->area length( p->holes ) p->bBox ) )
                )
            )
        )
        s3dProbeExposedSay( "===== done =====" )
        t
    )
)

; The sweep and the FILE, in one session and in the export's own order:
; makeVariant3dIntermediates writes the JSON exactly as the corpus does,
; then the same sweep is run by hand and its areas printed. A polygon the
; sweep has and the file has not can then be blamed on nothing but what
; happens between them.
procedure( s3dProbeExposedBoth( @optional ( t_config "D:/Projects/AI/Claude/Simple3D/simple3d_config.json" ) )
    let( ( dir cfg res ( n 0 ) line )
        dir = "./probe_export_out"
        s3dProbeExposedSay( sprintf( nil "probe_exposed: makeVariant3dIntermediates( %L nil %L )" dir t_config ) )
        errset( makeVariant3dIntermediates( dir list( 0.0 0.4 0.0 ) t_config ) t )
        s3dProbeExposedSay( "----- the exposed areas the FILE carries -----" )
        foreach( line parseString( s3dProbeExposedSlurp( strcat( dir "/circle-a0.json" ) ) "\n" )
            when( rexMatchp( "\"area\"" line )
                n = n + 1
                when( n <= 6  s3dProbeExposedSay( strcat( "FILE| " line ) ) )
            )
        )
        s3dProbeExposedSay( "----- the areas the SWEEP finds, same session -----" )
        cfg = s3dSilkConfig( t_config )
        res = s3dCollectExposed( nth( 7 cfg ) "TOP" nth( 4 cfg ) )
        n = 0
        foreach( group car( res )
            foreach( p cadr( group )
                n = n + 1
                when( n <= 6
                    s3dProbeExposedSay( sprintf( nil "SWEEP| #%d area %L holes %L" n p->area length( p->holes ) ) )
                )
            )
        )
        s3dProbeExposedSay( "===== done =====" )
        t
    )
)

; axlPolyFromDB's ?window, which s3dCopperPolys passes for a shape and the
; function's own documentation does not list. Asked three ways on the same
; shape: plain, with ?window over a small corner of it, and with a keyword
; that is certainly not a keyword - so "?window clips", "?window is ignored"
; and "?window is an error this session happens to survive" can be told
; apart. A shape that errors here is a pour that vanishes from the sweep.
procedure( s3dProbeExposedWindow()
    let( ( elems shape small plain windowed bogus ok )
        elems = s3dSelectVisibleOn( list( "ETCH/TOP" ) list( "noall" "shapes" )
                                    "probe: no such layer: %s" )
        shape = nil
        foreach( e elems
            when( !shape && (e->objType == "shape")  shape = e )
        )
        unless( shape
            s3dProbeExposedSay( "probe_exposed: no shape on ETCH/TOP" )
            return( nil )
        )
        s3dProbeExposedSay( sprintf( nil "shape %s bBox %L" s3dProbeExposedWhat( shape ) shape->bBox ) )

        plain = nil
        ok = errset( plain = axlPolyFromDB( shape ) )
        s3dProbeExposedSay( sprintf( nil "  plain            : errset %L -> %d poly(s) area %L"
                                     if( ok then "ok" else "FAILED" )
                                     length( remd( nil plain ) )
                                     s3dProbeExposedArea( plain ) ) )

        ; a window over one quarter of the shape's own box
        small = list( car( shape->bBox )
                      list( (caar( shape->bBox ) + caadr( shape->bBox )) / 2.0
                            (cadar( shape->bBox ) + cadadr( shape->bBox )) / 2.0 ) )
        windowed = nil
        ok = errset( windowed = axlPolyFromDB( shape ?window small ) )
        s3dProbeExposedSay( sprintf( nil "  ?window %L: errset %L -> %d poly(s) area %L"
                                     small
                                     if( ok then "ok" else "FAILED" )
                                     length( remd( nil windowed ) )
                                     s3dProbeExposedArea( windowed ) ) )

        bogus = nil
        ok = errset( bogus = axlPolyFromDB( shape ?notAKeywordAtAll small ) )
        s3dProbeExposedSay( sprintf( nil "  ?notAKeywordAtAll: errset %L -> %d poly(s) area %L"
                                     if( ok then "ok" else "FAILED" )
                                     length( remd( nil bogus ) )
                                     s3dProbeExposedArea( bogus ) ) )
        s3dProbeExposedSay( "===== done =====" )
        t
    )
)
