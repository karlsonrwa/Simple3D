;=====================================================================
;  probe_order.il - DIAGNOSTIC ONLY. Reads the design, changes nothing.
;
;  Settles the layer ORDER, which the per-layer build depends on and which
;  the previous probe could not show: it printed only NAMED layers, and the
;  dielectric has no name (0.125 mm in every stackup, by subtraction).
;
;  The open question: on STIFFENER2 the previous run reported
;      ADHESIVE_TOP    thk 0.05   position 4
;      SOLDERMASK_TOP  thk 0.025  position 6
;      TOP (CONDUCTOR) thk 0.045  position 5
;  i.e. the soldermask numbered BELOW the top conductor, which cannot be
;  physically true. And FLEX starts at position 3, so position looks like a
;  global index across "All Stackups" rather than an index within one.
;
;  This prints EVERY entry - unnamed ones included - for every stackup and
;  for the combined view, so the real ordering is visible.
;
;  Usage:  load("<path>/probe_order.il")   then   s3dProbeOrder()
;=====================================================================

procedure( s3dDumpStack( g_stackup t_label )
    let( ( layers ( sum 0.0 ) th thk )
        printf( "\n--- %s ---\n" t_label )
        layers = nil
        errset( layers = axlXSectionGet( g_stackup 'all ) )
        unless( layers
            printf( "  (nothing returned)\n" )
        )

        printf( "  %4s %-24s %-12s %10s %8s %8s\n"
                "pos" "name" "type" "thickness" "cond" "neg" )
        foreach( lay layers
            thk = lay->thickness
            unless( thk  thk = 0.0 )
            sum = sum + thk
            printf( "  %4L %-24L %-12L %10L %8L %8L\n"
                    lay->position
                    if( lay->name then lay->name else "(unnamed)" )
                    lay->layerType
                    thk
                    lay->conductor
                    lay->negativeArtwork )
        )

        th = nil
        errset( th = axlXSectionGet( g_stackup 'thickness ) )
        printf( "  sum of entries : %L\n" sum )
        printf( "  API 'thickness : %L\n" th )
        when( th && numberp( th ) && (abs( sum - th ) > 0.0001)
            printf( "  ^^^ THEY DISAGREE - the entry list is not the whole stackup\n" )
        )
    )
)

procedure( s3dProbeOrder()
    let( ( stackups )
        printf( "\n===== LAYER ORDER, EVERY ENTRY =====\n" )

        ; the combined view first - this is what "position" indexes
        s3dDumpStack( nil "nil  (single stackup, or ALL STACKUPS on rigid-flex)" )

        stackups = nil
        errset( stackups = axlXSectionGet( nil 'stackups ) )
        foreach( s stackups
            s3dDumpStack( s sprintf( nil "stackup %L" s ) )
        )
        printf( "\n===== END =====\n" )
        t
    )
)
