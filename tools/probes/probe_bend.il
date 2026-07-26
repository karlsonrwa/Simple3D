;=====================================================================
;  probe_bend.il - DIAGNOSTIC ONLY. Reads the design, changes nothing.
;
;  Everything Allegro exposes about BENDS, so folding is designed from the
;  data rather than from the reference - which describes almost none of it.
;
;    1. axlGetBends() + axlGetBendInnerRadius() - the only two documented
;       calls. They give a name and a radius and nothing else.
;    2. Groups. The bend documentation says "All of the Bend Area objects
;       are also collected together to form a single group. The group name
;       is defined by the Bend Area Name." Zones were reachable ONLY
;       through their group (round 26), so the group is the first place to
;       look for the line-to-area association. Every group is listed with
;       its type, and any group whose name is a bend name - or whose type
;       mentions BEND - is dumped member by member.
;    3. The RIGID FLEX class subclass inventory: what is actually drawn,
;       with counts. BEND_AREA and any keepout subclasses show up here.
;    4. Bend lines off RIGID FLEX/BEND_LINE with EVERY property printed
;       WHOLE, one per line. IDX_BEND_TYPE_INFO is where the angle, the
;       inner side and the bend order live and it appears in no reference;
;       the memo's copy of it is elided at "ORDER=0, ..." and the rest of
;       that string decides how much of the fold can be read rather than
;       guessed.
;    5. Bend areas with full geometry, so the strip the board curls in is
;       measured rather than derived from the radius and the angle.
;
;  Visibility and the find filter are saved and restored, same as every
;  other probe here.
;
;  Usage:  load("<path>/probe_bend.il")   then   s3dProbeBend()
;=====================================================================

; ---- shared: one object, dumped without assuming what it carries ------
procedure( s3dBendDumpGeom( o_dbid t_indent )
    let( ( segs ( n 0 ) )
        printf( "%sobjType   : %L\n" t_indent o_dbid->objType )
        errset( printf( "%slayer     : %L\n" t_indent o_dbid->layer ) )
        errset( printf( "%sbBox      : %L\n" t_indent o_dbid->bBox ) )
        errset( printf( "%sarea      : %L\n" t_indent o_dbid->area ) )
        errset( printf( "%sisVoid    : %L\n" t_indent o_dbid->isVoid ) )
        errset( printf( "%swidth     : %L\n" t_indent o_dbid->width ) )

        segs = nil
        errset( segs = o_dbid->segments )
        if( segs then
            printf( "%ssegments  : %d\n" t_indent length( segs ) )
            foreach( s segs
                n = n + 1
                when( n <= 40
                    printf( "%s  [%d] %L  startEnd %L\n"
                            t_indent n s->objType s->startEnd )
                    errset( printf( "%s      center %L radius %L\n"
                                    t_indent s->xy s->radius ) )
                )
            )
            when( n > 40  printf( "%s  ... %d more\n" t_indent n - 40 ) )
        else
            printf( "%ssegments  : none\n" t_indent )
        )
    )
)

; Properties printed WHOLE, one per line. %L on the whole list is what
; truncated IDX_BEND_TYPE_INFO in the notes; the tail of that string is the
; point of this probe.
procedure( s3dBendDumpProps( o_dbid t_indent )
    let( ( props nm val )
        props = nil
        errset( props = axlDBGetProperties( o_dbid ) )
        if( props then
            foreach( p props
                nm  = nil
                val = nil
                errset( nm = car( p ) )
                ; entries are (name value) - a two-element list, settled in
                ; round 26 - but a dotted pair is still handled.
                errset( val = if( listp( cdr( p ) ) then cadr( p ) else cdr( p ) ) )
                if( stringp( val ) then
                    printf( "%s  %L = %s\n" t_indent nm val )
                else
                    printf( "%s  %L = %L\n" t_indent nm val )
                )
            )
        else
            printf( "%s  (no properties)\n" t_indent )
        )
    )
)

; ---- 1: the documented API -------------------------------------------
procedure( s3dProbeBendApi()
    let( ( names r )
        printf( "\n===== BENDS (axlGetBends) =====\n" )
        names = nil
        errset( names = axlGetBends() )
        if( names then
            printf( "axlGetBends() -> %L\n" names )
            foreach( b names
                r = nil
                errset( r = axlGetBendInnerRadius( b ) )
                printf( "  %-24L inner radius %L\n" b r )
            )
        else
            printf( "axlGetBends() returned nil - no bends defined in this design.\n" )
        )
        names
    )
)

; ---- 2: groups -------------------------------------------------------
; Every group, so the bend group's TYPE is read rather than guessed - the
; zone group turned out to be "ZONE_GROUP" and nothing said so in advance.
procedure( s3dProbeBendGroups( l_bendNames )
    let( ( groups ( n 0 ) members nm interesting )
        printf( "\n===== GROUPS (all types) =====\n" )
        groups = nil
        errset( groups = axlDBGetDesign()->groups )

        foreach( g groups
            when( g
                n = n + 1
                nm = nil
                errset( nm = g->name )
                printf( "[group %d] name %L  type %L  members %L\n"
                        n nm
                        if( errset( g->type ) then g->type else nil )
                        if( errset( length( g->groupMembers ) ) then
                            length( g->groupMembers ) else nil ) )
            )
        )
        when( n == 0  printf( "no groups in this design.\n" ) )

        printf( "\n===== BEND GROUP MEMBERS =====\n" )
        foreach( g groups
            when( g
                nm = nil
                errset( nm = g->name )
                interesting = nil
                when( stringp( nm ) && member( nm l_bendNames )  interesting = t )
                when( errset( g->type ) && stringp( g->type ) &&
                      s3dBendContains( upperCase( g->type ) "BEND" )
                    interesting = t )
                when( interesting
                    printf( "\n--- group %L (type %L) ---\n"
                            nm if( errset( g->type ) then g->type else nil ) )
                    errset( printf( "    properties of the group itself:\n" ) )
                    s3dBendDumpProps( g "    " )
                    members = nil
                    errset( members = g->groupMembers )
                    if( members then
                        foreach( m members
                            printf( "  --- member ---\n" )
                            s3dBendDumpGeom( m "      " )
                            s3dBendDumpProps( m "      " )
                        )
                    else
                        printf( "  no groupMembers\n" )
                    )
                )
            )
        )
    )
)

; t if t_hay contains t_needle. Local copy - a probe must not depend on
; the exporter being loaded.
procedure( s3dBendContains( t_hay t_needle )
    let( ( ( n 0 ) ( found nil ) )
        n = strlen( t_needle )
        when( n > 0
            for( i 1 strlen( t_hay ) - n + 1
                when( substring( t_hay i n ) == t_needle  found = t )
            )
        )
        found
    )
)

; ---- 3: what is drawn on the RIGID FLEX class ------------------------
; Plain lists rather than a table: whether foreach iterates a SKILL table's
; keys is not stated anywhere in the reference on disk, and a probe that
; faults costs a round trip in a live session. There are tens of shapes.
procedure( s3dBendTally( l_items t_key )
    let( ( ( n 0 ) )
        foreach( x l_items  when( x == t_key  n = n + 1 ) )
        n
    )
)

procedure( s3dProbeRigidFlexSubclasses()
    let( ( shapes key pos ( seen nil ) ( keys nil ) )
        printf( "\n===== RIGID FLEX SUBCLASS INVENTORY (shapes) =====\n" )
        shapes = nil
        errset( shapes = axlDBGetShapes( "RIGID FLEX" ) )

        foreach( s shapes
            key = nil
            errset( key = s->layer )
            when( stringp( key )
                ; "RIGID FLEX/BEND_AREA" -> "BEND_AREA"
                pos = nil
                for( i 1 strlen( key )
                    when( substring( key i 1 ) == "/"  pos = i )
                )
                when( pos  key = substring( key pos + 1 strlen( key ) - pos ) )
                keys = cons( key keys )
                unless( member( key seen )  seen = cons( key seen ) )
            )
        )
        foreach( k seen
            printf( "  %-28s %d shape(s)\n" k s3dBendTally( keys k ) )
        )
        unless( shapes  printf( "  nothing on the RIGID FLEX class.\n" ) )
    )
)

; ---- 4 + 5: the geometry, swept off a subclass -----------------------
; Lines, shapes and text in one sweep: a bend line is a path and a bend
; area is a shape, and both have to be caught by whatever filter is set.
procedure( s3dProbeBendSubclass( t_layer )
    let( ( saveVis saveEnabled saveOn elems ( n 0 ) )
        printf( "\n===== %s =====\n" t_layer )

        saveVis     = axlVisibleGet()
        saveEnabled = axlGetFindFilter( t )
        saveOn      = axlGetFindFilter( nil )

        axlVisibleDesign( nil )
        unless( axlVisibleLayer( t_layer t )
            printf( "  no such layer in this design\n" )
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
            printf( "\n[%s #%d]\n" t_layer n )
            s3dBendDumpGeom( e "    " )
            printf( "    properties:\n" )
            s3dBendDumpProps( e "    " )
            ; does the object know its own group? The zone outlines did not,
            ; which is why zones have to be read through the group - worth
            ; knowing whether a bend line is the same.
            errset( printf( "    group     : %L\n" e->group ) )
            errset( printf( "    groups    : %L\n" e->groups ) )
        )
        when( n == 0  printf( "  nothing found on this subclass.\n" ) )
    )
)

; ---- context: where the board is, so coordinates can be read ---------
procedure( s3dProbeBendContext()
    let( ( dsn )
        printf( "\n===== CONTEXT =====\n" )
        dsn = nil
        errset( dsn = axlDBGetDesign() )
        errset( printf( "design      : %L\n" axlCurrentDesign() ) )
        errset( printf( "units       : %L\n" axlDBGetDesignUnits() ) )
        errset( printf( "design bBox : %L\n" dsn->bBox ) )
        errset( printf( "outline bBox: %L\n" dsn->designOutline->bBox ) )
        errset( printf( "stackups    : %L\n" axlXSectionGet( nil 'stackups ) ) )
    )
)

procedure( s3dProbeBend()
    let( ( names )
        s3dProbeBendContext()
        names = s3dProbeBendApi()
        s3dProbeBendGroups( names )
        s3dProbeRigidFlexSubclasses()
        s3dProbeBendSubclass( "RIGID FLEX/BEND_LINE" )
        s3dProbeBendSubclass( "RIGID FLEX/BEND_AREA" )
        printf( "\n===== END =====\n" )
        t
    )
)
