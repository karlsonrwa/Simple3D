;=====================================================================
;  probe_neg.il - DIAGNOSTIC ONLY. Reads the design, changes nothing.
;
;  Two facts the per-layer zone model depends on:
;
;   1. Is negativeArtwork actually set the way the layers behave?
;      COVERLAY_TOP has 8 shapes where STIFFENER has 1, which only makes
;      sense if coverlay is a NEGATIVE layer and those 8 are openings.
;      If negativeArtwork says so, the model can read it instead of
;      guessing from shape counts.
;
;   2. Do those shapes read like the zone outlines do - segments in the
;      same line/arc vocabulary - and do they carry inner voids
;      (islands), which have to become holes rather than material?
;
;  Note: shape->area came back nil for all 272 shapes of this design, so
;  it is NOT used here. Extent is reported from bBox instead.
;
;  Usage:  load("<path>/probe_neg.il")   then   s3dProbeNeg()
;=====================================================================

procedure( s3dProbeNegLayers()
    let( ( stackups layers )
        printf( "\n===== negativeArtwork PER STACKUP LAYER =====\n" )
        stackups = nil
        errset( stackups = axlXSectionGet( nil 'stackups ) )
        unless( stackups  stackups = list( nil ) )

        foreach( s stackups
            printf( "\n--- stackup %L ---\n" s )
            printf( "  %-22s %-11s %8s %6s %10s\n"
                    "layer" "type" "thk" "pos" "negative" )
            layers = nil
            errset( layers = axlXSectionGet( s 'all ) )
            foreach( lay layers
                when( lay->name
                    printf( "  %-22L %-11L %8L %6L %10L\n"
                            lay->name lay->layerType lay->thickness
                            lay->position lay->negativeArtwork )
                )
            )
        )
    )
)

; One shape: how its outline reads, and whether it has inner voids.
procedure( s3dProbeOneShape( o_shape t_indent )
    let( ( segs voids ( nArc 0 ) ( nLine 0 ) )
        errset( printf( "%sbBox    : %L\n" t_indent o_shape->bBox ) )
        errset( printf( "%sisVoid  : %L\n" t_indent o_shape->isVoid ) )

        segs = nil
        errset( segs = o_shape->segments )
        if( segs then
            foreach( sg segs
                if( sg->objType == "arc" then
                    nArc = nArc + 1
                else
                    nLine = nLine + 1
                )
            )
            printf( "%ssegments: %d  (%d line, %d arc)\n"
                    t_indent length( segs ) nLine nArc )
        else
            printf( "%ssegments: none\n" t_indent )
        )

        ; Inner voids / islands become holes in the face, not material.
        ; The attribute name is not documented for shapes, so try the
        ; plausible ones and report whichever answers.
        voids = nil
        errset( voids = o_shape->voids )
        when( voids
            printf( "%svoids   : %L\n" t_indent length( voids ) )
        )
        errset( when( o_shape->islands
            printf( "%sislands : %L\n" t_indent length( o_shape->islands ) ) ) )
        errset( when( o_shape->holes
            printf( "%sholes   : %L\n" t_indent length( o_shape->holes ) ) ) )
        unless( voids
            printf( "%svoids   : none reported\n" t_indent )
        )
    )
)

procedure( s3dProbeNegShapes()
    let( ( shapes ( n 0 ) )
        printf( "\n===== SHAPES ON THE RIGID FLEX CLASS =====\n" )
        shapes = nil
        errset( shapes = axlDBGetShapes( "RIGID FLEX" ) )
        unless( shapes
            printf( "  none\n" )
        )
        foreach( s shapes
            n = n + 1
            printf( "\n[%d] layer %L   objType %L\n" n s->layer s->objType )
            s3dProbeOneShape( s "      " )
        )
        printf( "\n%d shape(s) on RIGID FLEX in total.\n" n )
    )
)

procedure( s3dProbeNeg()
    s3dProbeNegLayers()
    s3dProbeNegShapes()
    printf( "\n===== END =====\n" )
    t
)
