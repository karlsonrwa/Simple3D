;=====================================================================
;  skill/s3d_pads.il - the copper pads: padstack figures, pin placements, the writer
;
;  Part 10 of 10 of the Simple 3D exporter (round 85, 2026-09-07); the
;  loader makeVariant3dIntermediates.il loads the parts in order. Load it,
;  or simple3d.il, never a part on its own.
;=====================================================================

;=====================================================================
;  COPPER PADS  (NEW - simple3d, format_version 10)
;
;  What a pin's copper looks like on the two outer faces, so the Python side
;  can draw it there - as thin copper-coloured surfaces lying on the mask,
;  for a picture that reads as a board rather than as a green slab.
;
;  Two halves, and a LIBRARY rather than per-pin geometry:
;
;    "padstacks"  one entry per distinct padstack the pins use: its drill
;                 (at the padstack origin, unrotated) and every REGULAR pad
;                 on an ETCH layer - the copper - and, since format_version
;                 11, on a SOLDERMASK subclass - the opening the copper
;                 shows through; the reader draws copper AND opening, so a
;                 solder-mask-defined pad shows the opening's shape and a
;                 pad with no opening at all shows nothing. Each with the
;                 figure Allegro names, its bounding box and offset, and
;                 its OUTLINE - the pad's own axlPath, walked with the
;                 documented accessors, in the same segment / arc / circle
;                 vocabulary the board outline uses.
;                 Every figure kind carries such a path (measured on three
;                 boards: CIRCLE is a start point and one closing arc,
;                 OBLONG two lines and two arcs, ROUNDED_RECTANGLE eight
;                 pieces, SHAPE whatever was drawn), so no figure kind is
;                 interpreted here - the outline is the truth and figureName
;                 travels beside it as a label.
;    "pins"       one row per pin of every placed symbol - mechanical
;                 symbols included, exactly the pins symbolReturnPinHoles
;                 drills - as [x, y, rotation, mirrored, padstack, start
;                 layer, end layer]. The span is the pin's own ->startEnd:
;                 it is what says which layers the pin reaches (a surface
;                 pin on a flex connector sits on INNER1, and a through pin
;                 of a flex-mounted part spans INNER1..INNER2 - measured on
;                 Cadence's demo board, where 48 of 2720 pins are exactly
;                 that). Which of those layers is an OUTER face of the pin's
;                 zone, and which pad goes where, is decided on the Python
;                 side against the stackups; this side reports.
;
;  VARIANTS: like the silkscreen, deliberately variant-INDEPENDENT. The bare
;  board carries every pad whether or not the part is installed, so the pads
;  are collected once per design and written into every file.
;
;  Since format_version 12 the rows carry the vias as well (every VIA CLASS
;  subclass swept once, the row's kind "via"; a tented via has no mask pad
;  and draws nothing), and two more members follow the rows, both in the
;  silkscreen's vertex form with Allegro's area per polygon:
;
;    "exposed"    the copper under the openings DRAWN on the soldermask
;                 layers the config lists (a line, a shape or a text on
;                 BOARD / PACKAGE GEOMETRY / SOLDERMASK_<side> by default):
;                 opening AND copper, computed here with axlPolyOperation.
;    "bare"       the laminate those openings show where no copper is -
;                 a part number cut into the mask as strokes, the ring of an
;                 opening drawn wider than its pad: opening ANDNOT copper,
;                 the whole opening when its box holds no copper at all.
;=====================================================================

; [x, y] or null.
procedure( s3dPointJson( l_point )
    if( l_point && numberp( xCoord( l_point ) ) && numberp( yCoord( l_point ) ) then
        sprintf( nil "[%f, %f]" xCoord( l_point ) yCoord( l_point ) )
    else
        "null"
    )
)

; [[x0, y0], [x1, y1]] or null.
procedure( s3dBBoxJson( l_bbox )
    if( l_bbox && car( l_bbox ) && cadr( l_bbox ) then
        strcat( "[" s3dPointJson( car( l_bbox ) ) ", " s3dPointJson( cadr( l_bbox ) ) "]" )
    else
        "null"
    )
)

; A pad's outline - an axlPath - as a JSON array of primitives, or nil when
; the path has fewer than two points.
;
; A path is not a dbid and has no ->segments; axlPathGetPathSegs hands its
; pieces over in order, and each piece carries only its END point, so the
; first piece is the start and every later one runs from where the last
; finished. An arc piece answers axlPathSegGetArcCenter with its centre and
; axlPathSegGetArcClockwise with its direction; a line answers nil to both.
; An arc that ends where it started is a full circle - a CIRCLE pad is
; exactly that, one start point and one closing arc - and is written as the
; circle primitive, because an arc of zero span reads as no arc at all.
procedure( s3dPathContourJson( r_path )
    let( ( segs prev e c cw r dx dy out ( n 0 ) prim )
        segs = nil
        errset( segs = axlPathGetPathSegs( r_path ) )
        out = tconc( nil nil )
        prev = nil
        foreach( sg segs
            e = nil
            errset( e = axlPathSegGetEndPoint( sg ) )
            when( e
                when( prev
                    c = nil
                    cw = nil
                    errset( c = axlPathSegGetArcCenter( sg ) )
                    errset( cw = axlPathSegGetArcClockwise( sg ) )
                    if( c then
                        dx = xCoord( prev ) - xCoord( c )
                        dy = yCoord( prev ) - yCoord( c )
                        r = sqrt( dx * dx + dy * dy )
                        dx = xCoord( e ) - xCoord( prev )
                        dy = yCoord( e ) - yCoord( prev )
                        if( sqrt( dx * dx + dy * dy ) < 1.0e-9 then
                            prim = makeCircle( c 2 * r )
                        else
                            prim = s3dArcPrimJson( xCoord( c ) yCoord( c ) r
                                                   xCoord( prev ) yCoord( prev )
                                                   xCoord( e ) yCoord( e ) cw )
                        )
                    else
                        prim = s3dSegmentPrimJson( xCoord( prev ) yCoord( prev )
                                                   xCoord( e ) yCoord( e ) )
                    )
                    tconc( out prim )
                    n = n + 1
                )
                prev = e
            )
        )
        when( n > 0
            strcat( "[\n" s3dAddIndent( buildString( cdr( car( out ) ) ",\n" ) ) "\n]" )
        )
    )
)

; One pad of a padstack: what Allegro says about it, and its outline.
;
; "inside" is the hole of a DONUT (0 otherwise) - the one thing the outline
; cannot carry, since a path is one loop. "offset" and "bbox" travel beside
; the outline so the reader can tell whether the path already includes the
; offset (the three boards measured all have offsets of 0, so that could not
; be settled here) and check itself against the box.
procedure( s3dPadFigureJson( o_pad )
    let( ( bb off inside outline figure )
        bb = nil
        errset( bb = o_pad->bBox )
        off = nil
        errset( off = o_pad->offset )
        inside = nil
        errset( inside = o_pad->inside )
        unless( numberp( inside )  inside = 0.0 )
        outline = nil
        figure = nil
        errset( figure = o_pad->figure )
        when( figure
            errset( outline = s3dPathContourJson( car( figure ) ) )
        )
        strcat( "{\n"
                "\t\"figure\": " s3dJsonQuote( o_pad->figureName ) ",\n"
                "\t\"bbox\": " s3dBBoxJson( bb ) ",\n"
                "\t\"offset\": " s3dPointJson( off ) ",\n"
                "\t\"inside\": " sprintf( nil "%f" inside ) ",\n"
                "\t\"outline\": " if( outline then s3dAddIndent( outline ) else "null" ) "\n"
                "}" )
    )
)

; A REGULAR pad with a figure on an ETCH layer (the copper) or on a
; SOLDERMASK subclass (the opening the copper shows through - format_version
; 11). Paste, thermals and antipads are neither. Written under the pad's own
; layer name, "PIN/SOLDERMASK_TOP" and the like; the reader goes by the
; subclass, so a padstack used by a via ("VIA CLASS/...") reads the same.
procedure( s3dIsPadCopperOrMask( o_pad )
    let( ( lay type name up )
        lay = nil
        errset( lay = o_pad->layer )
        type = nil
        errset( type = o_pad->type )
        name = nil
        errset( name = o_pad->figureName )
        up = if( stringp( lay ) then upperCase( lay ) else "" )
        stringp( lay )
            && ( ((strlen( up ) > 5) && (substring( up 1 5 ) == "ETCH/"))
                 || s3dContains( up "/SOLDERMASK_" ) )
            && stringp( type ) && (upperCase( type ) == "REGULAR")
            && stringp( name ) && !(upperCase( name ) == "NULL")
    )
)

; The drill of a padstack as a contour at the padstack's ORIGIN, unrotated:
; the same circle or slot symbolReturnPinHoles cuts through the board, at
; the drill offset the padstack carries (an edge connector's half-holes sit
; off the pad - see s3dDrillXY). nil when there is no hole. The pin's
; rotation is applied on the Python side with the rest of the figure.
procedure( s3dHoleAtOrigin( o_padstack )
    let( ( offset dx dy d w h element )
        offset = nil
        errset( offset = o_padstack->drillOffset )
        dx = 0.0
        dy = 0.0
        when( offset
            when( numberp( xCoord( offset ) )  dx = xCoord( offset ) )
            when( numberp( yCoord( offset ) )  dy = yCoord( offset ) )
        )
        d = nil
        errset( d = o_padstack->drillDiameter )
        w = nil
        errset( w = o_padstack->drillSizeWidth )
        h = nil
        errset( h = o_padstack->drillSizeHeight )
        cond(
            ( numberp( w ) && numberp( h ) && (w > 0.0) && (h > 0.0) && !(w == h)
                element = makeSlotAt( list( dx dy ) 0.0 o_padstack )
                strcat( "[\n" s3dAddIndent( buildString( element ",\n" ) ) "\n]" )
            )
            ( numberp( d ) && (d > 0.0)
                strcat( "[\n" s3dAddIndent( makeCircle( list( dx dy ) d ) ) "\n]" )
            )
            ( t nil )
        )
    )
)

; One padstack of the library, as  "NAME": { usage, drill, pads }, or nil
; when Allegro cannot load it by that name.
procedure( s3dPadstackJson( t_name )
    let( ( ps pads out ( first t ) hole usage lay body )
        ps = nil
        errset( ps = axlLoadPadstack( t_name ) )
        when( ps
            usage = nil
            errset( usage = ps->usage )
            hole = nil
            errset( hole = s3dHoleAtOrigin( ps ) )
            out = strcat( s3dJsonQuote( t_name ) ": {\n"
                          "\t\"usage\": " s3dJsonQuote( usage ) ",\n"
                          "\t\"drill\": " if( hole then s3dAddIndent( hole ) else "null" ) ",\n"
                          "\t\"pads\": {" )
            pads = nil
            errset( pads = ps->pads )
            foreach( pd pads
                when( s3dIsPadCopperOrMask( pd )
                    lay = pd->layer
                    body = strcat( s3dJsonQuote( lay ) ": " s3dPadFigureJson( pd ) )
                    out = strcat( out if( first then "\n" else ",\n" ) s3dAddIndent( body 2 ) )
                    first = nil
                )
            )
            strcat( out if( first then "}\n}" else "\n\t}\n}" ) )
        )
    )
)

; Every pin of every placed symbol, and the padstacks they use.
; -> list( l_padstackJsonStrings l_pinJsonStrings x_pins )  or nil when the
;    design has no pins.
;
; The pins are walked the way symbolReturnPinHoles walks them - the design's
; symbols, mechanical ones included - so a mounting hole with a pad is a pad.
; Padstack names are collected in a table and the library built once per
; name, sorted, so two exports of one board write the same file.
; One pin or via as a row: [x, y, rotation, mirrored, padstack, start, end, kind].
procedure( s3dPadRowJson( o_obj t_kind )
    let( ( se rot )
        se = nil
        errset( se = o_obj->startEnd )
        rot = o_obj->rotation
        unless( numberp( rot )  rot = 0.0 )
        sprintf( nil "[%f, %f, %f, %s, %s, %s, %s, %s]"
                 xCoord( o_obj->xy ) yCoord( o_obj->xy ) rot
                 if( o_obj->isMirrored then "true" else "false" )
                 s3dJsonQuote( o_obj->name )
                 s3dJsonQuote( when( se car( se ) ) )
                 s3dJsonQuote( when( se cadr( se ) ) )
                 s3dJsonQuote( t_kind ) )
    )
)

; Every VIA CLASS subclass of the design, as "VIA CLASS/<sub>" - the layers
; a one-pass via sweep needs visible at once. axlSubclasses is the
; documented question; AllegroBaseStructure's dump settled that a sweep with
; all of them on returns each via ONCE, where asking layer by layer returned
; a through via on every layer it crosses (34 000 vias became 510 343).
procedure( s3dViaLayers()
    let( ( subs out )
        subs = nil
        errset( subs = axlSubclasses( "VIA CLASS" ) )
        out = nil
        foreach( sub subs
            when( stringp( sub )
                out = cons( strcat( "VIA CLASS/" sub ) out )
            )
        )
        reverse( out )
    )
)

; Every pin of every placed symbol, every via, and the padstacks they use;
; and the copper the drawn mask openings expose (s3dCollectExposed).
; -> list( l_padstackJsonStrings l_rowJsonStrings x_rows l_exposedTop l_exposedBottom )
;    or nil when the design has no pins.
;
; The pins are walked the way symbolReturnPinHoles walks them - the design's
; symbols, mechanical ones included - so a mounting hole with a pad is a pad.
; The vias come from one sweep with every VIA CLASS subclass visible (format
; 12); a tented via has no mask pad in its padstack and the reader draws
; nothing for it, so a board that tents its vias pays one row per via and
; no geometry. Padstack names are collected in a table and the library
; built once per name, sorted, so two exports of one board write the same
; file.
procedure( s3dCollectPads( @optional ( l_maskTop nil ) ( l_maskBottom nil ) ( s_endCap 'ROUND ) )
    let( ( dsn table names stacks rows ( n 0 ) ( nVias 0 ) ( nMissing 0 ) one vias exposedTop exposedBottom )
        dsn = axlDBGetDesign()
        table = makeTable( "s3dPadstackNames" nil )
        rows = tconc( nil nil )
        foreach( sym dsn->symbols
            foreach( pin sym->pins
                when( stringp( pin->name ) && pin->xy
                    n = n + 1
                    table[pin->name] = t
                    tconc( rows s3dPadRowJson( pin "pin" ) )
                )
            )
        )
        vias = nil
        errset( vias = s3dSelectVisibleOn( s3dViaLayers() list( "noall" "vias" )
                                           "Simple 3D: no such layer: %s" ) )
        foreach( v vias
            when( stringp( v->name ) && v->xy
                nVias = nVias + 1
                table[v->name] = t
                tconc( rows s3dPadRowJson( v "via" ) )
            )
        )
        when( n + nVias > 0
            names = sort( table->? 'alphalessp )
            stacks = tconc( nil nil )
            foreach( name names
                one = nil
                errset( one = s3dPadstackJson( name ) )
                if( one then
                    tconc( stacks one )
                else
                    nMissing = nMissing + 1
                    s3dWarn( sprintf( nil "Simple 3D: padstack %s could not be loaded; its pins get no copper." name ) )
                )
            )
            printf( "Simple 3D: copper pads - %d pin(s) and %d via(s) on %d padstack(s)%s\n"
                    n nVias length( names )
                    if( nMissing > 0 then sprintf( nil " (%d not loadable)" nMissing ) else "" ) )
            exposedTop = nil
            exposedBottom = nil
            when( l_maskTop
                exposedTop = s3dCollectExposed( l_maskTop "TOP" s_endCap )
            )
            when( l_maskBottom
                exposedBottom = s3dCollectExposed( l_maskBottom "BOTTOM" s_endCap )
            )
            list( cdr( car( stacks ) ) cdr( car( rows ) ) n + nVias exposedTop exposedBottom )
        )
    )
)

;---------------------------------------------------------------------
;  The copper under the DRAWN mask openings (format_version 12)
;
;  A pin's or via's opening is in its padstack and the reader clips the pad
;  to it. An opening drawn in the footprint or on the board - a line or a
;  shape on PACKAGE GEOMETRY / BOARD GEOMETRY / SOLDERMASK_<side> - exposes
;  whatever copper lies under it: a thermal pad drawn as a shape, a row of
;  fingers, a test area, a pour. That copper is computed HERE, where the
;  polygon engine is: every opening becomes polygons (s3dPolysFromDbid, the
;  silkscreen's converter, so a line opening is the line widened with round
;  caps), the copper on the side's outer ETCH layer inside the opening's
;  box is selected and converted - a pour only through its window, which is
;  what ?window is for - and axlPolyOperation AND keeps what is under the
;  opening. Written in the silkscreen's vertex form so the reader builds it
;  with the legend's own machinery, area-checked. Measured on the user's
;  board: two shapes expose 1.03 and 1.01 mm2 of 1.18 and 1.16 mm2 openings,
;  in well under a second each.
;
;  Where an opening lies over a pin's pad, that pad is written twice - once
;  here, once through its padstack. The reader lifts the exposed copper a
;  micron above the pads, so the two never fight.
;---------------------------------------------------------------------

; The copper objects on the side's outer copper whose box meets l_bbox, with
; the design's visibility set to exactly that layer (and the PIN / VIA CLASS
; subclass of the same side, so pins and vias are found by the box too).
; The caller sets and restores the visibility ONCE per side - see
; s3dCollectExposed - because toggling it per opening is what made the
; silkscreen's per-layer sweep expensive.
procedure( s3dSelectInBox( l_bbox )
    let( ( elems )
        axlClearSelSet()
        elems = nil
        when( l_bbox && car( l_bbox ) && cadr( l_bbox )
            ; BOTH corners, always: given one or none, axlAddSelectBox asks
            ; the user to pick - and there is no user in a headless session.
            when( errset( axlAddSelectBox( list( car( l_bbox ) cadr( l_bbox ) ) ) t )
                elems = axlGetSelSet()
            )
        )
        axlClearSelSet()
        elems
    )
)

; The polygons of one copper object, for the AND: a pin or via's pad on the
; side's etch layer, a shape only inside the window, a cline - or a no-net
; line on the etch layer, a label in copper - widened with round caps,
; anything else whole.
procedure( s3dCopperPolys( o_obj t_etch l_window s_endCap )
    let( ( polys )
        polys = nil
        cond(
            ( (o_obj->objType == "pin") || (o_obj->objType == "via")
                errset( polys = axlPolyFromDB( o_obj ?layer t_etch ?padType 'REGULAR ) )
            )
            ( o_obj->objType == "shape"
                errset( polys = axlPolyFromDB( o_obj ?window l_window ) )
            )
            ( t
                errset( polys = s3dPolysFromDbid( o_obj s_endCap ) )
            )
        )
        remd( nil polys )
    )
)

; The copper the drawn openings of one side expose, grouped by the opening's
; layer: ( (layer polys) ... ), the silkscreen's group form.
procedure( s3dCollectExposed( l_layers t_side s_endCap )
    let( ( elems openings key polys etch pinLayer viaLayer saveVis saveEnabled saveOn
           found copper res groups order out ( nOpen 0 ) ( nOut 0 ) ( nBad 0 ) filter zero
           bareGroups bareOrder bare ( nBare 0 ) bareOut )
        etch = strcat( "ETCH/" t_side )
        pinLayer = strcat( "PIN/" t_side )
        viaLayer = strcat( "VIA CLASS/" t_side )
        groups = makeTable( "s3dExposedGroups" nil )
        order = tconc( nil nil )
        ; What an opening shows where there is NO copper under it: the bare
        ; laminate - a part number cut into the mask, the ring of a drawn
        ; opening wider than its pad. Opening ANDNOT copper, or the whole
        ; opening when nothing lies under it; the reader draws it in the
        ; dielectric's colour.
        bareGroups = makeTable( "s3dBareGroups" nil )
        bareOrder = tconc( nil nil )

        ; 1. the openings, as polygons, before any visibility is touched.
        ; Lines, shapes AND text: a string on a mask layer is an opening in
        ; the shape of its letters (a part number showing the laminate), and
        ; the silkscreen's converter already vectorises text. A zero-width
        ; object cannot be plotted and is skipped with a word, as the legend
        ; does it, rather than handed to the converter to fail on.
        elems = s3dSelectVisibleOn( l_layers list( "noall" "lines" "shapes" "text" )
                                    "Simple 3D: no such layer: %s" )
        openings = nil
        foreach( elem elems
            key = nil
            errset( key = elem->layer )
            unless( stringp( key )  key = sprintf( nil "%L" key ) )
            polys = nil
            zero = nil
            errset( zero = s3dZeroWidth( elem ) )
            when( zero
                s3dWarn( sprintf( nil "Simple 3D: zero width: %s - skipped, it opens nothing."
                                  s3dDescribeObject( elem key ) ) )
            )
            unless( zero || errset( polys = s3dPolysFromDbid( elem s_endCap ) )
                nBad = nBad + 1
            )
            foreach( poly polys
                when( poly && !poly->isHole
                    nOpen = nOpen + 1
                    openings = cons( list( key poly ) openings )
                )
            )
        )
        openings = reverse( openings )

        when( openings
            ; 2. the copper, with the visibility set once for the whole side
            saveVis     = axlVisibleGet()
            saveEnabled = axlGetFindFilter( t )
            saveOn      = axlGetFindFilter( nil )
            ; "lines" AND "clines": copper drawn with Add Line on an ETCH
            ; subclass belongs to no net and is a "line" to the find filter,
            ; not a "cline" - the user's label in copper on my_test_board2 is
            ; 51 such paths, and "clines" alone selected none of them
            ; (tools/probes/probe_etchtext.il: "lines" 38 in the band,
            ; "clines" 0; 52 no-net paths on ETCH/TOP in all).
            filter = list( "noall" "lines" "clines" "shapes" "pins" "vias" )
            axlVisibleDesign( nil )
            axlVisibleLayer( etch t )
            errset( axlVisibleLayer( pinLayer t ) )
            errset( axlVisibleLayer( viaLayer t ) )
            axlSetFindFilter( ?enabled filter ?onButtons filter )

            foreach( entry openings
                key = car( entry )
                found = s3dSelectInBox( cadr( entry )->bBox )
                copper = nil
                foreach( o found
                    copper = append( copper s3dCopperPolys( o etch cadr( entry )->bBox s_endCap ) )
                )
                bare = list( cadr( entry ) )
                when( copper
                    res = nil
                    errset( res = axlPolyOperation( list( cadr( entry ) ) copper 'AND ) )
                    foreach( p remd( nil res )
                        when( p && !p->isHole
                            nOut = nOut + 1
                            unless( groups[key]
                                groups[key] = tconc( nil nil )
                                tconc( order key )
                            )
                            tconc( groups[key] p )
                        )
                    )
                    bare = nil
                    errset( bare = axlPolyOperation( list( cadr( entry ) ) copper 'ANDNOT ) )
                )
                foreach( p remd( nil bare )
                    when( p && !p->isHole
                        nBare = nBare + 1
                        unless( bareGroups[key]
                            bareGroups[key] = tconc( nil nil )
                            tconc( bareOrder key )
                        )
                        tconc( bareGroups[key] p )
                    )
                )
            )

            errset( axlVisibleSet( saveVis ) )
            when( saveEnabled || saveOn
                errset( axlSetFindFilter( ?enabled saveEnabled
                                          ?onButtons remove( "DYNTHEMALS" saveOn ) ) )
            )
        )

        when( nBad > 0
            s3dWarn( sprintf( nil "Simple 3D: %d mask opening(s) on the %s could not be converted and were skipped."
                              nBad t_side ) )
        )
        printf( "Simple 3D: exposed copper %s - %d drawn opening(s), %d polygon(s) of copper under them, %d of bare laminate\n"
                t_side nOpen nOut nBare )
        out = tconc( nil nil )
        foreach( key cdr( car( order ) )
            tconc( out list( key cdr( car( groups[key] ) ) ) )
        )
        bareOut = tconc( nil nil )
        foreach( key cdr( car( bareOrder ) )
            tconc( bareOut list( key cdr( car( bareGroups[key] ) ) ) )
        )
        ; -> ( copperGroups bareGroups ), each ( (layer polys) ... )
        list( cdr( car( out ) ) cdr( car( bareOut ) ) )
    )
)

; The whole "pads" object, streamed straight to the open file like the
; silkscreen: a dense board has tens of thousands of pins, and one row per
; pin in a string built by repeated strcat is quadratic. g_more says whether
; another member (the silkscreen) follows, and so whether the closing brace
; takes a comma.
procedure( s3dWritePads( p_port l_pads g_more )
    let( ( stacks pins ( first t ) exposedTop exposedBottom )
        stacks = nth( 0 l_pads )
        pins = nth( 1 l_pads )
        exposedTop = nth( 3 l_pads )
        exposedBottom = nth( 4 l_pads )
        fprintf( p_port "\t\"pads\": {\n" )
        fprintf( p_port "\t\t\"padstacks\": {\n" )
        foreach( s stacks
            unless( first  fprintf( p_port ",\n" ) )
            first = nil
            fprintf( p_port "%s" s3dAddIndent( s 3 ) )
        )
        fprintf( p_port "\n\t\t},\n" )
        fprintf( p_port "\t\t\"pins\": [\n" )
        first = t
        foreach( p pins
            unless( first  fprintf( p_port ",\n" ) )
            first = nil
            fprintf( p_port "\t\t\t%s" p )
        )
        fprintf( p_port "\n\t\t],\n" )
        ; The copper under the drawn openings, and the bare laminate the
        ; openings show where there is none, both in the silkscreen's polygon
        ; form (format_version 12) - the legend's writer, the legend's reader.
        ; Each side is ( copperGroups bareGroups ), or nil.
        fprintf( p_port "\t\t\"exposed\": {\n" )
        fprintf( p_port "\t\t\t\"top\": [\n" )
        s3dWriteSilkPolys( p_port car( exposedTop ) )
        fprintf( p_port "\n\t\t\t],\n" )
        fprintf( p_port "\t\t\t\"bottom\": [\n" )
        s3dWriteSilkPolys( p_port car( exposedBottom ) )
        fprintf( p_port "\n\t\t\t]\n" )
        fprintf( p_port "\t\t},\n" )
        fprintf( p_port "\t\t\"bare\": {\n" )
        fprintf( p_port "\t\t\t\"top\": [\n" )
        s3dWriteSilkPolys( p_port cadr( exposedTop ) )
        fprintf( p_port "\n\t\t\t],\n" )
        fprintf( p_port "\t\t\t\"bottom\": [\n" )
        s3dWriteSilkPolys( p_port cadr( exposedBottom ) )
        fprintf( p_port "\n\t\t\t]\n" )
        fprintf( p_port "\t\t}\n" )
        fprintf( p_port if( g_more then "\t},\n" else "\t}\n" ) )
    )
)
