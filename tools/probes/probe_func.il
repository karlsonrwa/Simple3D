;=====================================================================
;  probe_func.il - DIAGNOSTIC ONLY. Reads the design, changes nothing.
;
;  Which stackup layers are drawn NEGATIVE (their shapes are openings) and
;  which POSITIVE (their shapes are the material)?
;
;  negativeArtwork is NOT the answer - it came back nil on every layer of
;  the test board, because it is about film generation. The rigid-flex
;  documentation points somewhere else: the Mask Layer Site File assigns
;  each layer an "IPC Layer Function Type as defined by IPC-2581", and the
;  cross-section carries it as the layerFunction attribute.
;
;  Expected, from the user's own notes and from the geometry:
;      COVERLAY_TOP   negative - its shapes are openings
;      ADHESIVE_TOP   positive
;      STIFFENER_TOP  positive
;  If layerFunction separates those three, the build can read polarity from
;  the design instead of guessing from the layer name.
;
;  Usage:  load("<path>/probe_func.il")   then   s3dProbeFunc()
;=====================================================================

procedure( s3dProbeFunc()
    let( ( funcs types stackups layers )
        printf( "\n===== LEGAL LAYER FUNCTIONS =====\n" )
        funcs = nil
        errset( funcs = axlXSectionLayerFunctions() )
        if( funcs then
            foreach( f funcs  printf( "  %L\n" f ) )
        else
            printf( "  axlXSectionLayerFunctions() returned nothing\n" )
        )

        printf( "\n===== LEGAL LAYER TYPES =====\n" )
        types = nil
        errset( types = axlXSectionLayerTypes() )
        printf( "  %L\n" types )

        printf( "\n===== layerFunction PER LAYER =====\n" )
        stackups = nil
        errset( stackups = axlXSectionGet( nil 'stackups ) )
        unless( stackups  stackups = list( nil ) )

        foreach( s stackups
            printf( "\n--- stackup %L ---\n" s )
            printf( "  %-24s %-12s %-28s %-8s %s\n"
                    "layer" "type" "layerFunction" "neg" "material" )
            layers = nil
            errset( layers = axlXSectionGet( s 'all ) )
            foreach( lay layers
                when( lay->name
                    printf( "  %-24L %-12L %-28L %-8L %L\n"
                            lay->name lay->layerType lay->layerFunction
                            lay->negativeArtwork lay->material )
                )
            )
        )
        printf( "\n===== END =====\n" )
        t
    )
)
