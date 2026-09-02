;=====================================================================
;  probe_flex2.il - DIAGNOSTIC ONLY. Reads the design, changes nothing.
;
;  REQUIRES: makeVariant3dIntermediates.il  (s3dSelectVisibleOn, s3dWarn)
;  Load the exporter first: the subclass sweep is its s3dSelectVisibleOn
;  since round 76 (D3) instead of a copy kept here.
;
;  Fills the two gaps probe_flex.il left:
;
;    1. The zone outline is NOT in zone->shapeBoundary (nil on every zone
;       of the test board) but in zone->groupMembers, which came back with
;       one entry each. Dump that member: what it is, and whether its
;       geometry reads with the same segment/arc vocabulary the board
;       outline already uses.
;
;    2. A bend line is objType "path" and startEnd is nil, so bBox was the
;       only geometry printed. That is enough only while the line is axis
;       aligned - a diagonal bend needs the real endpoints. Dump the path
;       segments.
;
;  Usage:  load("<path>/probe_flex2.il")   then   s3dProbeFlex2()
;=====================================================================

; Everything worth knowing about one geometric object, without assuming
; which attributes it happens to carry.
procedure( s3dProbeShape( o_dbid t_indent )
    let( ( segs ( n 0 ) )
        printf( "%sobjType   : %L\n" t_indent o_dbid->objType )
        errset( printf( "%slayer     : %L\n" t_indent o_dbid->layer ) )
        errset( printf( "%sbBox      : %L\n" t_indent o_dbid->bBox ) )
        errset( printf( "%sisVoid    : %L\n" t_indent o_dbid->isVoid ) )
        errset( printf( "%sarea      : %L\n" t_indent o_dbid->area ) )

        segs = nil
        errset( segs = o_dbid->segments )
        if( segs then
            printf( "%ssegments  : %d\n" t_indent length( segs ) )
            foreach( s segs
                n = n + 1
                when( n <= 6
                    printf( "%s  [%d] %L  start %L  end %L\n"
                            t_indent n s->objType s->startEnd s->end )
                    errset( printf( "%s      center %L radius %L\n"
                                    t_indent s->xy s->radius ) )
                )
            )
            when( n > 6  printf( "%s  ... %d more\n" t_indent n - 6 ) )
        else
            printf( "%ssegments  : none\n" t_indent )
        )
        ; A shape's outline may live behind a different attribute again.
        errset( printf( "%svertices  : %L\n" t_indent
                        if( o_dbid->vertices then length( o_dbid->vertices ) else nil ) ) )
    )
)

; ---- 1: where the zone outline actually is ---------------------------
procedure( s3dProbeZoneMembers()
    let( ( groups ( n 0 ) members )
        printf( "\n===== ZONE MEMBERS =====\n" )
        groups = nil
        errset( groups = axlDBGetDesign()->groups )

        foreach( g groups
            when( g && (g->type == "ZONE_GROUP")
                n = n + 1
                printf( "\n[zone %d] %L   stackup %L\n" n g->name g->stackup )
                members = nil
                errset( members = g->groupMembers )
                if( members then
                    foreach( m members
                        printf( "  --- member ---\n" )
                        s3dProbeShape( m "      " )
                        errset( printf( "      properties: %L\n"
                                        axlDBGetProperties( m ) ) )
                    )
                else
                    printf( "  no groupMembers\n" )
                )
            )
        )
        when( n == 0  printf( "no ZONE_GROUP found.\n" ) )
    )
)

; ---- 2: real bend line geometry --------------------------------------
procedure( s3dProbeBendGeometry()
    let( ( elems ( n 0 ) )
        printf( "\n===== BEND LINE GEOMETRY =====\n" )

        elems = s3dSelectVisibleOn( list( "RIGID FLEX/BEND_LINE" ) list( "noall" "lines" "shapes" "text" )
                                    "  no such layer: %s" )

        foreach( e elems
            n = n + 1
            printf( "\n[bend line %d]\n" n )
            s3dProbeShape( e "    " )
        )
        when( n == 0  printf( "  nothing found.\n" ) )
    )
)

; ---- 3: is the zone outline reachable as a plain subclass sweep? -----
; Fallback route, in case groupMembers turns out not to hold the geometry.
procedure( s3dProbeZoneOutlineLayer()
    let( ( elems ( n 0 ) )
        printf( "\n===== RIGID FLEX/ZONE_OUTLINE sweep =====\n" )

        elems = s3dSelectVisibleOn( list( "RIGID FLEX/ZONE_OUTLINE" ) list( "noall" "lines" "shapes" "text" )
                                    "  no such layer: %s" )

        foreach( e elems
            n = n + 1
            printf( "\n[outline %d]\n" n )
            s3dProbeShape( e "    " )
            errset( printf( "    group     : %L\n" e->group ) )
            errset( printf( "    groups    : %L\n" e->groups ) )
        )
        when( n == 0  printf( "  nothing found.\n" ) )
    )
)

procedure( s3dProbeFlex2()
    s3dProbeZoneMembers()
    s3dProbeBendGeometry()
    s3dProbeZoneOutlineLayer()
    printf( "\n===== END =====\n" )
    t
)
