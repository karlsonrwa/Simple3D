;=====================================================================
;  probe_flex.il - DIAGNOSTIC ONLY. Reads the design, changes nothing.
;
;  Dumps everything Allegro exposes about multi-stackup and rigid-flex, so
;  the real shape of the data decides the design instead of the reference:
;
;    1. stackups            axlXSectionGet( nil 'stackups )
;    2. per-stackup layers  axlXSectionGet( <name> 'all ) + 'thickness
;    3. zones               design->groups where type == "ZONE_GROUP"
;                           -> name, stackup, boundary geometry
;    4. bends               axlGetBends() + axlGetBendInnerRadius()
;    5. bend lines          swept off RIGID FLEX/BEND_LINE, with EVERY
;                           property dumped raw - IDX_BEND_TYPE_INFO is
;                           where the real bend parameters live and the
;                           reference says nothing about it
;
;  Visibility and the find filter are saved and restored, same as the
;  silkscreen collector.
;
;  Usage:  load("<path>/probe_flex.il")   then   s3dProbeFlex()
;=====================================================================

; ---- 1 + 2: stackups -------------------------------------------------
procedure( s3dProbeStackups()
    let( ( stackups layers th n )
        printf( "\n===== STACKUPS =====\n" )

        stackups = nil
        errset( stackups = axlXSectionGet( nil 'stackups ) )
        if( stackups then
            printf( "axlXSectionGet(nil 'stackups) -> %L\n" stackups )
        else
            printf( "no stackup list returned (single-stackup design?)\n" )
        )

        ; nil = the standard stackup on a plain board, "All Stackups" on rigid-flex
        th = nil
        errset( th = axlXSectionGet( nil 'thickness ) )
        printf( "thickness(nil) = %L\n" th )

        foreach( s stackups
            when( stringp( s )
                printf( "\n--- stackup %L ---\n" s )
                th = nil
                errset( th = axlXSectionGet( s 'thickness ) )
                printf( "  thickness : %L\n" th )
                n = nil
                errset( n = axlXSectionGet( s 'count ) )
                printf( "  entries   : %L\n" n )

                layers = nil
                errset( layers = axlXSectionGet( s 'all ) )
                foreach( lay layers
                    printf( "    %-28L %-12L %L\n"
                            lay->name lay->layerType lay->thickness )
                )
            )
        )
    )
)

; ---- 3: zones --------------------------------------------------------
procedure( s3dProbeZoneBoundary( o_zone )
    let( ( b )
        b = nil
        errset( b = o_zone->shapeBoundary )
        if( b then
            printf( "    boundary dbid : %L\n" b->objType )
            ; A zone outline is an ordinary shape, so the same segment
            ; vocabulary the board outline already uses should apply.
            errset( printf( "    bBox          : %L\n" b->bBox ) )
            errset( printf( "    segment count : %L\n" length( b->segments ) ) )
        else
            printf( "    no shapeBoundary\n" )
        )
    )
)

procedure( s3dProbeZones()
    let( ( groups ( n 0 ) )
        printf( "\n===== ZONES =====\n" )
        groups = nil
        errset( groups = axlDBGetDesign()->groups )

        foreach( g groups
            when( g && (g->type == "ZONE_GROUP")
                n = n + 1
                printf( "\n[zone %d] name %L\n" n g->name )
                errset( printf( "    stackup   : %L\n" g->stackup ) )
                errset( printf( "    region    : %L\n" g->region ) )
                errset( printf( "    room      : %L\n" g->room ) )
                errset( printf( "    members   : %L\n" length( g->groupMembers ) ) )
                s3dProbeZoneBoundary( g )
            )
        )
        when( n == 0
            printf( "no ZONE_GROUP found - this design is single-stackup.\n" )
        )
    )
)

; ---- 4: bends via the dedicated API ----------------------------------
procedure( s3dProbeBends()
    let( ( names r )
        printf( "\n===== BENDS (axlGetBends) =====\n" )
        names = nil
        errset( names = axlGetBends() )
        if( names then
            foreach( b names
                r = nil
                errset( r = axlGetBendInnerRadius( b ) )
                printf( "  %-24L inner radius %L\n" b r )
            )
        else
            printf( "axlGetBends() returned nil - no bends defined.\n" )
        )
    )
)

; ---- 5: bend lines and their properties ------------------------------
; The dedicated API gives only the inner radius. The F4 dump shows the rest
; (TYPE, INNER_SIDE, INNER_ANGLE, ORDER, ...) lives in a property called
; IDX_BEND_TYPE_INFO, which no reference page describes - so dump it raw.
procedure( s3dProbeBendLines( t_layer )
    let( ( saveVis saveEnabled saveOn elems props ( n 0 ) )
        printf( "\n===== BEND LINES on %s =====\n" t_layer )

        saveVis     = axlVisibleGet()
        saveEnabled = axlGetFindFilter( t )
        saveOn      = axlGetFindFilter( nil )

        axlVisibleDesign( nil )
        unless( axlVisibleLayer( t_layer t )
            printf( "  no such layer: %s\n" t_layer )
        )
        axlClearSelSet()
        axlSetFindFilter( ?enabled list( "noall" "lines" "shapes" "text" )
                          ?onButtons list( "noall" "lines" "shapes" "text" ) )
        axlAddSelectAll()
        elems = axlGetSelSet()
        axlClearSelSet()

        errset( axlVisibleSet( saveVis ) )
        when( saveEnabled || saveOn
            errset( axlSetFindFilter( ?enabled saveEnabled
                                      ?onButtons remove( "DYNTHEMALS" saveOn ) ) )
        )

        foreach( e elems
            n = n + 1
            printf( "\n[line %d] objType %L\n" n e->objType )
            errset( printf( "    layer      : %L\n" e->layer ) )
            errset( printf( "    startEnd   : %L\n" e->startEnd ) )
            errset( printf( "    bBox       : %L\n" e->bBox ) )
            props = nil
            errset( props = axlDBGetProperties( e ) )
            printf( "    properties : %L\n" props )
        )
        when( n == 0
            printf( "  nothing found on this layer.\n" )
        )
    )
)

procedure( s3dProbeFlex()
    s3dProbeStackups()
    s3dProbeZones()
    s3dProbeBends()
    s3dProbeBendLines( "RIGID FLEX/BEND_LINE" )
    printf( "\n===== END =====\n" )
    t
)
