;=====================================================================
;  probe_layers.il - DIAGNOSTIC ONLY. Reads the design, changes nothing.
;
;  Why: the zone outline is NOT the shape of a stackup layer. Measured on
;  flex-b2, Allegro's own export has 86.763 mm2 at the stiffener height
;  while our zone prism puts 171.761 mm2 there - because each outer layer
;  (stiffener, coverlay, adhesive, mask) is drawn as its OWN shape, smaller
;  than the zone and with its own cutouts, and only the core spans the
;  whole zone.
;
;  So: which stackup layers actually have a drawn shape, and which do not?
;  That decides how the zone body has to be built.
;
;    A. every shape in the design, grouped by layer (count, total area)
;    B. every stackup layer, matched against those groups
;
;  axlDBGetShapes( "<class>" ) returns all subclasses of a class, and each
;  shape's ->layer says which one, so no subclass name has to be guessed.
;
;  Usage:  load("<path>/probe_layers.il")   then   s3dProbeLayers()
;=====================================================================

; Total area of a shape list, and how many reported no area at all.
procedure( s3dAreaSum( l_shapes )
    let( ( ( total 0.0 ) ( noArea 0 ) a )
        foreach( s l_shapes
            a = nil
            errset( a = s->area )
            if( a && numberp( a ) then
                total = total + a
            else
                noArea = noArea + 1
            )
        )
        list( total noArea )
    )
)

; ---- A: every shape in the design, grouped by layer ------------------
procedure( s3dProbeShapeLayers()
    let( ( shapes tbl keys key info ( n 0 ) )
        printf( "\n===== EVERY SHAPE, BY LAYER =====\n" )
        shapes = nil
        errset( shapes = axlDBGetShapes( nil ) )
        unless( shapes
            printf( "axlDBGetShapes(nil) returned nothing.\n" )
        )

        tbl = makeTable( "s3dLayerShapes" nil )
        keys = tconc( nil nil )

        foreach( s shapes
            n = n + 1
            key = nil
            errset( key = s->layer )
            unless( stringp( key )  key = sprintf( nil "%L" key ) )
            unless( tbl[key]
                tbl[key] = nil
                tconc( keys key )
            )
            tbl[key] = cons( s tbl[key] )
        )

        printf( "%d shape(s) on the design.\n\n" n )
        printf( "%-42s %6s %12s %8s\n" "layer" "count" "area mm2" "no-area" )
        foreach( k cdr( car( keys ) )
            info = s3dAreaSum( tbl[k] )
            printf( "%-42s %6d %12.3f %8d\n"
                    k length( tbl[k] ) car( info ) cadr( info ) )
        )
    )
)

; ---- B: stackup layers vs drawn shapes -------------------------------
; For every layer of every stackup, does a shape layer exist for it?
; Tries the RIGID FLEX class first (that is where the stiffener lives),
; then the layer name as a class of its own (soldermask usually is).
procedure( s3dProbeLayerShapes( t_name )
    let( ( shapes info tried )
        tried = strcat( "RIGID FLEX/" t_name )
        shapes = nil
        errset( shapes = axlDBGetShapes( tried ) )
        unless( shapes
            tried = t_name
            errset( shapes = axlDBGetShapes( tried ) )
        )
        if( shapes then
            info = s3dAreaSum( shapes )
            printf( "      %-34s %3d shape(s) %10.3f mm2  [%s]\n"
                    "-> found" length( shapes ) car( info ) tried )
        else
            printf( "      %-34s none found\n" "-> no drawn shape" )
        )
    )
)

procedure( s3dProbeStackupLayers()
    let( ( stackups layers nm )
        printf( "\n===== STACKUP LAYERS vs DRAWN SHAPES =====\n" )
        stackups = nil
        errset( stackups = axlXSectionGet( nil 'stackups ) )
        unless( stackups  stackups = list( nil ) )

        foreach( s stackups
            printf( "\n--- stackup %L ---\n" s )
            layers = nil
            errset( layers = axlXSectionGet( s 'all ) )
            foreach( lay layers
                nm = lay->name
                when( nm
                    printf( "  %-30L %-12L thk %L\n"
                            nm lay->layerType lay->thickness )
                    s3dProbeLayerShapes( nm )
                )
            )
        )
    )
)

procedure( s3dProbeLayers()
    s3dProbeShapeLayers()
    s3dProbeStackupLayers()
    printf( "\n===== END =====\n" )
    t
)
