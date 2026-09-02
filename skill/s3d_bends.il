;=====================================================================
;  skill/s3d_bends.il - bend lines and bend areas
;
;  Part 7 of 9 of the Simple 3D exporter, cut from
;  makeVariant3dIntermediates.il in round 76 (plan D6) with every procedure
;  and comment as it was; that file loads the parts in order. Load it, or
;  simple3d.il, never a part on its own.
;=====================================================================


;=====================================================================
;  Bends
;
;  A bend is not geometry in Allegro. It is a line, an area and a property,
;  and all three are needed to fold anything:
;
;    axlGetBends()                the names
;    axlGetBendInnerRadius(name)  the radius - the only bend parameter with
;                                 an API of its own
;    RIGID FLEX/BEND_LINE         the axis. The documentation is explicit
;                                 that the line "represents the midpoint of
;                                 the bend", so the strip that curls is
;                                 centred on it rather than starting there.
;    RIGID FLEX/BEND_AREA         the extent of that strip. Measured ACROSS
;                                 the line it is the developed length of the
;                                 arc: how much flat material the fold eats.
;                                 Trimmed to the design outline, so it is
;                                 measured rather than derived.
;    IDX_BEND_TYPE_INFO           angle, inner side, order, type.
;
;  That last one is UNDOCUMENTED - it appears in neither the SKILL API index
;  nor the DB attribute reference - so it is emitted RAW and parsed on the
;  Python side. A field spelled differently by another Allegro version can
;  then be handled without a re-export, and the string itself is in the
;  intermediate where it can be read.
;
;  Line and area are associated through their GROUP: "All of the Bend Area
;  objects are also collected together to form a single group. The group name
;  is defined by the Bend Area Name" (Defining a Bend Area). That is also how
;  zones had to be read - a zone outline's ->group is nil - so the group is
;  tried first here too, with a subclass sweep as the fallback.
;=====================================================================


; Bend lines swept off their subclass. nil until asked for; only ever asked
; for on a design that HAS bends, so an ordinary board pays no visibility
; churn for a feature it does not use.
S3D_BendLines = nil

procedure( s3dSweepBendLines()
    s3dSelectVisibleOn( list( "RIGID FLEX/BEND_LINE" ) list( "noall" "lines" )
                        "Simple 3D: no %s subclass in this design." )
)

; The members of the group named t_name, or nil.
procedure( s3dGroupNamed( t_name )
    let( ( ( found nil ) )
        errset(
            foreach( g axlDBGetDesign()->groups
                when( g && !found && stringp( g->name ) && (g->name == t_name)
                    found = g->groupMembers
                )
            )
        )
        found
    )
)

; ( lineDbid areaDbid ) for one bend, from its group. Either may be nil.
procedure( s3dBendParts( t_name )
    let( ( ( line nil ) ( area nil ) lay )
        foreach( m s3dGroupNamed( t_name )
            lay = nil
            errset( lay = m->layer )
            when( stringp( lay )
                lay = upperCase( lay )
                when( !line && s3dContains( lay "BEND_LINE" )  line = m )
                when( !area && s3dContains( lay "BEND_AREA" )  area = m )
            )
        )
        list( line area )
    )
)

; The two endpoints of a path, as ( (x y) (x y) ).
;
; A bend line's own ->startEnd is nil - it is a path, not a segment - and the
; endpoints live on its segments. Taking the first segment's start and the
; last one's end also reads a bend line drawn as several collinear pieces.
procedure( s3dPathEnds( o_dbid )
    let( ( segs ( lastSeg nil ) a b )
        segs = nil
        errset( segs = o_dbid->segments )
        when( segs
            foreach( s segs  lastSeg = s )
            a = nil
            b = nil
            errset( a = car( car( segs )->startEnd ) )
            errset( b = cadr( lastSeg->startEnd ) )
            when( a && b  list( a b ) )
        )
    )
)

; t if a point is inside a bBox given as ( (xl yl) (xh yh) ).
procedure( s3dBBoxHas( l_bBox l_pt )
    let( ( lo hi )
        lo = car( l_bBox )
        hi = cadr( l_bBox )
        (xCoord( l_pt ) >= xCoord( lo )) && (xCoord( l_pt ) <= xCoord( hi )) &&
        (yCoord( l_pt ) >= yCoord( lo )) && (yCoord( l_pt ) <= yCoord( hi ))
    )
)

; How wide a shape is measured ACROSS the line a-b. On a bend area that is
; the developed length of the arc, which is the one number that says how much
; flat board the fold consumes - and it is a measurement, not a derivation
; from radius and angle, so it stays right when the two disagree.
procedure( s3dSpanAcross( o_shape l_a l_b )
    let( ( dx dy len nx ny ( lo nil ) ( hi nil ) w )
        dx = xCoord( l_b ) - xCoord( l_a )
        dy = yCoord( l_b ) - yCoord( l_a )
        len = sqrt( dx * dx + dy * dy )
        when( len > 0.0
            nx = dy / len
            ny = - dx / len
            errset(
                foreach( seg o_shape->segments
                    foreach( p seg->startEnd
                        w = nx * (xCoord( p ) - xCoord( l_a )) +
                            ny * (yCoord( p ) - yCoord( l_a ))
                        when( !lo || (w < lo)  lo = w )
                        when( !hi || (w > hi)  hi = w )
                    )
                )
            )
            when( lo && hi  hi - lo )
        )
    )
)

; The bend area whose bBox contains a point. Bend areas "cannot overlap"
; (Defining a Bend Area), so containment picks exactly one.
procedure( s3dBendAreaAt( l_pt )
    let( ( ( found nil ) )
        unless( S3D_RigidFlexShapes  s3dCollectRigidFlexShapes() )
        foreach( s S3D_RigidFlexShapes["BEND_AREA"]
            when( !found && errset( s3dBBoxHas( s->bBox l_pt ) ) &&
                  s3dBBoxHas( s->bBox l_pt )
                found = s
            )
        )
        found
    )
)

; The whole bend array. "bends": [] on any board without them, which is
; every board this tool has exported until now.
procedure( s3dBendsJson()
    let( ( names parts line area ends mid radius width info body out
           ( first t ) ( n 0 ) ( made 0 ) ( swept nil ) ( warned nil ) )
        names = nil
        errset( names = axlGetBends() )

        if( !names then
            "\"bends\": []"
        else
            out = "\"bends\": [\n"
            foreach( b names
                when( stringp( b )
                    n = n + 1
                    parts = s3dBendParts( b )
                    line  = car( parts )
                    area  = cadr( parts )

                    ; Fallback: the group route found no line. Sweep the
                    ; subclass and pair by order, which is only defensible
                    ; because it is announced.
                    unless( line
                        unless( swept
                            S3D_BendLines = s3dSweepBendLines()
                            swept = t
                        )
                        when( length( S3D_BendLines ) == length( names )
                            line = nth( n - 1 S3D_BendLines )
                            unless( warned
                                warned = t
                                s3dWarn( "Simple 3D: bend lines are not in their bend groups; pairing them with the bend names IN ORDER. Check the folded model." )
                            )
                        )
                    )

                    ends = if( line then s3dPathEnds( line ) else nil )
                    if( !ends then
                        s3dWarn( sprintf( nil "Simple 3D: bend %s has no readable bend line; it will not be folded." b ) )
                    else
                        mid = list( (xCoord( car( ends ) ) + xCoord( cadr( ends ) )) / 2.0
                                    (yCoord( car( ends ) ) + yCoord( cadr( ends ) )) / 2.0 )
                        unless( area  area = s3dBendAreaAt( mid ) )

                        radius = nil
                        errset( radius = axlGetBendInnerRadius( b ) )
                        width = if( area then s3dSpanAcross( area car( ends ) cadr( ends ) ) else nil )

                        info = s3dPropValue( line "IDX_BEND_TYPE_INFO" )
                        unless( stringp( info )
                            s3dWarn( sprintf( nil "Simple 3D: bend %s carries no IDX_BEND_TYPE_INFO, so its angle is unknown; it will not be folded." b ) )
                        )

                        body = strcat(
                            "{\n"
                            "\t\"name\": " s3dJsonQuote( b ) ",\n"
                            "\t\"line\": { \"start\": ["
                            sprintf( nil "%f" xCoord( car( ends ) ) ) ", "
                            sprintf( nil "%f" yCoord( car( ends ) ) ) "], \"end\": ["
                            sprintf( nil "%f" xCoord( cadr( ends ) ) ) ", "
                            sprintf( nil "%f" yCoord( cadr( ends ) ) ) "] },\n"
                            "\t\"inner_radius\": "
                            if( radius then sprintf( nil "%f" radius ) else "null" ) ",\n"
                            "\t\"width\": "
                            if( width then sprintf( nil "%f" width ) else "null" ) ",\n"
                            "\t\"info\": " s3dJsonQuote( info ) "\n"
                            "}"
                        )
                        unless( first  out = strcat( out ",\n" ) )
                        first = nil
                        made = made + 1
                        out = strcat( out s3dAddIndent( body ) )
                    )
                )
            )
            printf( "Simple 3D: %d of %d bend(s) exported.\n" made n )
            strcat( out "\n]" )
        )
    )
)
