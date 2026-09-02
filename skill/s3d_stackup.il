;=====================================================================
;  skill/s3d_stackup.il - board thickness, stackups, zones, per-layer shapes
;
;  Part 6 of 9 of the Simple 3D exporter, cut from
;  makeVariant3dIntermediates.il in round 76 (plan D6) with every procedure
;  and comment as it was; that file loads the parts in order. Load it, or
;  simple3d.il, never a part on its own.
;=====================================================================


procedure( calculateBoardThickness()
    ; FIX (simple3d): SILKSCREEN_* and PASTEMASK_* are ALSO layerType "MASK"
    ; (verified on a real board), so the original
    ;     if name == "SOLDERMASK_TOP" then top else bottom
    ; put silkscreen into the bottom mask and, using plain "=", let each later
    ; MASK layer overwrite the previous one. Now: only SOLDERMASK layers count,
    ; classified top/bottom by cross-section position relative to the outermost
    ; conductor (so a renamed mask still lands correctly). Dielectric pseudo-
    ; layers have name = nil, hence the guard.
    ;
    ; NOTE (simple3d): this sums a SINGLE stackup. Multi-stackup / rigid-flex
    ; designs (more than one stackup zone) are NOT supported - the whole board
    ; is exported with this one averaged thickness. See the README limitation.
    let( ( stackup padToPadThickness topSoldermaskThickness bottomSoldermaskThickness
           topCondPos nm thk )
        stackup = axlXSectionGet( nil 'all )
        padToPadThickness = 0.0
        topSoldermaskThickness = 0.0
        bottomSoldermaskThickness = 0.0
        topCondPos = nil

        ; first conductor/plane from the top gives the reference position
        foreach( layer stackup
            case( layer->layerType
                ( ( "CONDUCTOR" "PLANE" )
                    unless( topCondPos  topCondPos = layer->position )
                )
                ( t nil )
            )
        )

        foreach( layer stackup
            thk = layer->thickness
            unless( thk  thk = 0.0 )
            case( layer->layerType
                ( ( "CONDUCTOR" "DIELECTRIC" "PLANE" )
                    padToPadThickness = padToPadThickness + thk
                )
                ( ( "MASK" )
                    nm = if( layer->name then upperCase( layer->name ) else "" )
                    when( substring( nm 1 10 ) == "SOLDERMASK"
                        if( topCondPos && layer->position && (layer->position < topCondPos) then
                            topSoldermaskThickness = topSoldermaskThickness + thk
                        else
                            bottomSoldermaskThickness = bottomSoldermaskThickness + thk
                        )
                    )
                )
                ( t nil )
            )
        )
        list( topSoldermaskThickness padToPadThickness bottomSoldermaskThickness )
    )
)

;=====================================================================
;  (top core bottom) of the board for pcb.thickness - requirement #1, one rule
;
;  Until round 76 (D5) this was calculateBoardThickness alone: the cross
;  section from axlXSectionGet( nil 'all ) summed by layer TYPE, with the
;  masks picked out by NAME ("SOLDERMASK..."), while every named stackup was
;  measured by POSITION in s3dStackupJson. Two rules for one number - and the
;  first was never right on a rigid-flex design (nil 'all is the combined
;  "All Stackups" view, not any real stackup - round 27) nor on a stack whose
;  outer layers are not called SOLDERMASK.
;
;  Now: the stackup the board IS - PRIMARY when the design names its
;  stackups, the cross section itself when it does not - measured the way
;  s3dStackupJson measures every stackup: the layers that are body material
;  (s3dLayerInBody), split at the outermost conductors (s3dConductorSpan).
;  On every plain board of the corpus the three numbers are exactly what
;  calculateBoardThickness gave; on a rigid-flex design with a PRIMARY they
;  are that stackup's own numbers instead of the combined view's. A design
;  whose named stackups hold no PRIMARY keeps calculateBoardThickness: there
;  is no one stackup that is "the board".
;=====================================================================
procedure( s3dBoardThickness()
    let( ( names query all layers span ( above 0.0 ) ( core 0.0 ) ( below 0.0 ) ( i 0 ) )
        names = nil
        errset( names = axlXSectionGet( nil 'stackups ) )
        query = cond(
            ( !names                      nil )        ; a plain board: the cross section itself
            ( member( "PRIMARY" names )   "PRIMARY" )
            ( t                           'none ) )
        all = nil
        unless( query == 'none
            errset( all = axlXSectionGet( query 'all ) )
        )
        layers = nil
        foreach( layer all
            when( s3dLayerInBody( layer )  layers = cons( layer layers ) )
        )
        layers = reverse( layers )
        span = s3dConductorSpan( layers )
        if( (query == 'none) || !span then
            calculateBoardThickness()
        else
            foreach( layer layers
                cond(
                    ( i < car( span )    above = above + s3dLayerThk( layer ) )
                    ( i > cadr( span )   below = below + s3dLayerThk( layer ) )
                    ( t                  core  = core  + s3dLayerThk( layer ) ) )
                i = i + 1
            )
            list( above core below )
        )
    )
)

;=====================================================================
;  MULTI-STACKUP / RIGID-FLEX
;
;  A rigid-flex board is several zones, each with its own stackup and its
;  own thickness. Everything needed is in the database:
;
;    axlXSectionGet( nil 'stackups )   -> the stackup names
;    axlXSectionGet( <name> 'all )     -> that stackup's layers
;    design->groups, type "ZONE_GROUP" -> the zones
;    zone->stackup                     -> which stackup a zone uses
;    zone->groupMembers                -> the zone outline polygon
;
;  Measured on a real rigid-flex board, and the reason this is not simply
;  "one thickness per zone": FLEX, STIFFENER1 and STIFFENER2 total 0.365,
;  0.49 and 2.44 but their conductor cores are all 0.215. The zones butt
;  against each other at the COPPER, not at their outer faces - a 2.44 mm
;  stiffener grows 2.125 up and 0.1 down from the same core. So each zone
;  is emitted as (above, core, below), not as one number.
;=====================================================================

; (above core below) for one stackup, in design units. g_stackup may be nil
; for a single-stackup design.
;
; Split by POSITION relative to the outermost conductors, never by layer
; name. A flex stackup has no SOLDERMASK layer at all - coverlay, adhesive
; and stiffener sit there instead - so the name gate calculateBoardThickness
; uses reports 0.0 for both sides of it. Verified against the API's own
; axlXSectionGet(<name> 'thickness): above+core+below reproduces it exactly
; on every stackup of the test board.
; Thickness of one cross-section entry, 0.0 when it has none (the two
; surface entries).
procedure( s3dLayerThk( o_layer )
    let( ( thk )
        thk = nil
        errset( thk = o_layer->thickness )
        if( thk && numberp( thk ) then thk else 0.0 )
    )
)

; Index (0-based) of the first and last conductor in the entry list, as
; ( firstIdx lastIdx ), or nil if the stackup has no conductor at all.
;
; **LIST ORDER, never layer->position.** Measured on a real rigid-flex
; board: position DUPLICATES (6 is both SOLDERMASK_TOP and the dielectric,
; 10 is both SOLDERMASK_BOTTOM and the bottom surface) and is not monotonic,
; because it indexes the combined "All Stackups" view rather than this
; stackup. The order axlXSectionGet( <name> 'all ) returns IS the physical
; order - checked line by line against Allegro's own cross-section editor,
; top surface first.
;
; The earlier version of this code compared positions and put SOLDERMASK_TOP
; inside the core instead of above it: the total still came out right, so
; nothing looked wrong, but the core - which is the datum every zone is
; aligned on - sat 0.025 mm low on one stackup.
procedure( s3dConductorSpan( l_layers )
    let( ( ( i 0 ) first last )
        foreach( layer l_layers
            case( layer->layerType
                ( ( "CONDUCTOR" "PLANE" )
                    unless( first  first = i )
                    last = i
                )
                ( t nil )
            )
            i = i + 1
        )
        when( first  list( first last ) )
    )
)

; Layer-name prefixes whose drawn shapes are OPENINGS, not material.
; Overridden from settings.negativeLayers in simple3d_config.json.
;
; Kept as a named default as well, because the override is a GLOBAL and these
; files load once per Allegro session: without something to restore, the list
; one board's config set outlives that board. See s3dSilkConfig, and the
; round-42 note on S3D_ExportFullBoard just below.
S3D_NegativeLayersDefault = list( "COVERLAY" "SOLDERMASK" "PASTEMASK" )
S3D_NegativeLayers = S3D_NegativeLayersDefault

; Write <design>.json - the WHOLE board, variants ignored - beside the
; per-variant files. Overridden from settings.exportFullBoard.
;
; Why it is wanted: the variant list decides what is INSTALLED, and a drawing
; sometimes has to show what is on the bare board regardless - the same reason
; ALWAYS_STEP_EXPORT exists, but for the whole board at once rather than part by
; part. NO_STEP_EXPORT still applies: it is tested before any variant question.
;
; The file has the name the no-variant export already uses, which cannot collide
; with <design>_<variant>.json, and it carries "full_board": true so the window
; can name it in the queue rather than showing one nameless extra file.
S3D_ExportFullBoard = t

; t if this layer's shapes are openings rather than material.
;
; Determined by IPC-2581 layer FUNCTION where the design carries one -
; layerFunction is what the Mask Layer Site File assigns, per the rigid-flex
; documentation - and by name prefix otherwise.
;
; NOT by negativeArtwork: that flag is about film generation and reads nil on
; every layer of a real rigid-flex board, including the coverlay, which is
; unambiguously drawn as openings. Believing it produced a board with the
; coverlay inverted - material where the windows should be.
procedure( s3dLayerIsNegative( o_layer )
    let( ( nm fn ( neg nil ) probe )
        nm = nil
        errset( nm = o_layer->name )
        fn = nil
        errset( fn = o_layer->layerFunction )

        ; the function name, when there is one, carries the same words
        probe = ""
        when( stringp( fn )  probe = upperCase( fn ) )
        when( stringp( nm )  probe = strcat( probe " " upperCase( nm ) ) )

        foreach( key S3D_NegativeLayers
            when( stringp( key ) && (strlen( key ) > 0)
                ; substring search, so COVERLAY matches COVERLAY_TOP and a
                ; function spelled "Coverlay" alike
                for( i 1 (strlen( probe ) - strlen( key ) + 1)
                    when( substring( probe i strlen( key ) ) == upperCase( key )
                        neg = t
                    )
                )
            )
        )
        neg
    )
)

; One drawn shape as { "outline": [...], "voids": [ [...], ... ] }.
;
; Voids are the holes punched in a layer - ADHESIVE_TOP has 7 of them on the
; test board, STIFFENER_TOP and ADHESIVE_TOP2 six each, and the six small
; COVERLAY_TOP patches sit exactly in those holes. They have to become holes
; in the face, not material.
procedure( s3dShapeJson( o_shape )
    let( ( outline voids body ( firstVoid t ) )
        outline = s3dContourJson( o_shape )
        when( outline
            body = strcat( "{\n\t\"outline\": " s3dAddIndent( outline ) )

            voids = nil
            errset( voids = o_shape->voids )
            if( voids then
                body = strcat( body ",\n\t\"voids\": [\n" )
                foreach( v voids
                    when( s3dContourJson( v )
                        unless( firstVoid  body = strcat( body ",\n" ) )
                        firstVoid = nil
                        body = strcat( body s3dAddIndent( s3dContourJson( v ) 2 ) )
                    )
                )
                body = strcat( body "\n\t]" )
            else
                body = strcat( body ",\n\t\"voids\": []" )
            )
            strcat( body "\n}" )
        )
    )
)

; Shapes on the RIGID FLEX class, grouped by subclass name, live in the export
; state's 'shapes (round 77, D7; a session global before): nil until
; s3dCollectRigidFlexShapes has run, rebuilt per file.

; Ask for the WHOLE class once and sort the answer, rather than asking for each
; stackup layer by name.
;
; Asking by name made Allegro print
;     *WARNING* (axlDBGetShapes): No match for subclass name - "RIGID FLEX/TOP"
; for every conductor, the dielectric and the soldermask - none of which is ever
; drawn on this class - and once per stackup that contains them, so ten warnings
; on a three-stackup board. A miss cannot happen here: what is not in the table
; simply is not there. It is also one database query instead of one per layer
; per stackup, which mattered less but is not nothing.
;
; Only the RIGID FLEX class is consulted. PACKAGE GEOMETRY/SOLDERMASK_* also
; exists but describes footprint openings, not the extent of a board layer, so
; asking for it would be wrong rather than merely unhelpful.
procedure( s3dCollectRigidFlexShapes( g_state )
    let( ( shapes key pos table ( n 0 ) )
        table = makeTable( "s3dRigidFlexShapes" nil )
        g_state['shapes] = table
        shapes = nil
        errset( shapes = axlDBGetShapes( "RIGID FLEX" ) )

        foreach( s shapes
            key = nil
            errset( key = s->layer )
            when( stringp( key )
                ; "RIGID FLEX/COVERLAY_TOP" -> "COVERLAY_TOP"
                pos = nil
                for( i 1 strlen( key )
                    when( substring( key i 1 ) == "/"  pos = i )
                )
                when( pos
                    key = substring( key pos + 1 strlen( key ) - pos )
                    n = n + 1
                    table[key] = cons( s table[key] )
                )
            )
        )
        when( n > 0
            printf( "Simple 3D: %d shape(s) on RIGID FLEX subclasses.\n" n )
        )
        table
    )
)

; Every drawn shape of one stackup layer, as a JSON array. nil when the layer
; has none - conductors, the dielectric and the soldermask are not drawn on
; the RIGID FLEX class, and those layers span the whole zone instead.
procedure( s3dLayerShapesJson( t_layerName g_state )
    let( ( shapes body ( first t ) one table )
        unless( g_state['shapes]  s3dCollectRigidFlexShapes( g_state ) )
        table = g_state['shapes]
        shapes = table[t_layerName]
        when( shapes
            body = "[\n"
            foreach( s shapes
                one = s3dShapeJson( s )
                when( one
                    unless( first  body = strcat( body ",\n" ) )
                    first = nil
                    body = strcat( body s3dAddIndent( one ) )
                )
            )
            unless( first  strcat( body "\n]" ) )
        )
    )
)

; Every rigid-flex zone as ( name stackup outlineDbid ). nil when the design
; has no zones, which is the ordinary single-stackup case.
;
; The outline is the zone group's member, NOT zone->shapeBoundary: the
; reference calls that the boundary, but it comes back nil on every zone of
; a real board. Sweeping the RIGID FLEX/ZONE_OUTLINE subclass finds the same
; polygons, but their ->group and ->groups are nil, so that route cannot say
; which zone an outline belongs to. Going through the group is the only way
; to keep the association.
procedure( s3dZoneList()
    let( ( out groups outline )
        out = tconc( nil nil )
        groups = nil
        errset( groups = axlDBGetDesign()->groups )

        foreach( g groups
            when( g && (g->type == "ZONE_GROUP") && g->stackup
                outline = nil
                errset( outline = car( g->groupMembers ) )
                when( outline && outline->segments
                    tconc( out list( g->name g->stackup outline ) )
                )
            )
        )
        cdr( car( out ) )
    )
)

; One stackup as { "thickness": t, "layers": [ ... ] }.
;
; Every layer carries its own z_top / z_bottom, measured from the TOP OF THE
; CONDUCTOR CORE = 0. That datum is what lets zones of wildly different
; thickness butt together: measured on a real board, FLEX, STIFFENER1 and
; STIFFENER2 are 0.365, 0.49 and 2.44 thick with an identical 0.215 core, and
; a stiffener simply grows outwards from the copper.
;
; A layer also carries its drawn shapes, or null when it has none. That is the
; difference between this and a plain prism per zone: Allegro's own export puts
; 86.763 mm2 at the stiffener height while a zone prism puts 171.761 there,
; because the stiffener is a drawn shape smaller than the zone. Layers with no
; shapes - conductors, the dielectric, the soldermask - do span the whole zone.
; nil for a cross-section entry that is NOT part of the finished board body.
;
; Silkscreen and paste mask are both layerType MASK and both appear in the
; cross section, but neither belongs in the solid:
;   - the legend is exported separately, as its own geometry, from the
;     silkscreen section. Leaving it in the stack would draw it TWICE, and the
;     stack copy would be a sheet covering the whole board rather than the
;     characters actually printed on it.
;   - paste mask is a stencil aperture definition. It is not on the finished
;     board at all.
;
; This is requirement #1 from 2026-07-18 - "dielectrics + planes + conductors +
; soldermask both sides; silkscreen and paste mask excluded" - which
; calculateBoardThickness has always honoured. The per-layer emission did not,
; and on a plain board that put four extra 0.025 sheets into the stack and
; reported 1.204 mm where the board is 1.104. It never showed on the rigid-flex
; test board because those stackups carry no silkscreen or paste layers.
;
; layerFunction is the reliable test (SILKSCREEN / SOLDER_PASTE); the name is
; the fallback for a design that does not set one.
procedure( s3dLayerInBody( o_layer )
    let( ( probe )
        probe = strcat(
            if( o_layer->name then upperCase( o_layer->name ) else "" ) " "
            if( stringp( o_layer->layerFunction ) then
                upperCase( o_layer->layerFunction )
            else
                "" ) )
        ; Short markers on purpose. SILKSCREEN_TOP and PASTEMASK_TOP are the
        ; usual names and layerFunction usually says SILKSCREEN / SOLDER_PASTE,
        ; but a design that names a layer PASTE_TOP and sets no function would
        ; slip through a longer test. Nothing else in a cross section contains
        ; "SILK" or "PASTE" - not coverlay, adhesive, stiffener, soldermask,
        ; conductor or dielectric - so the short form cannot over-match.
        !( s3dContains( probe "SILK" ) || s3dContains( probe "PASTE" ) )
    )
)

procedure( s3dStackupJson( t_name g_stackup g_state )
    let( ( all layers span thk ( total 0.0 ) ( above 0.0 ) ( cum 0.0 ) ( i 0 )
           ( nSkip 0 ) zTop zBot shapes body out ( first t )
           silkTop silkBot allSpan )
        all = nil
        errset( all = axlXSectionGet( g_stackup 'all ) )

        ; Drop what is not part of the body BEFORE anything is measured: the
        ; z walk below closes the remaining layers up against the core, so a
        ; dropped sheet leaves no gap where it used to be.
        ;
        ; But REMEMBER which side carried a silkscreen before dropping it. A
        ; cross section assigns its mask and coating layers per stackup, so a
        ; rigid-flex board says "no silkscreen on the stiffener zones" exactly
        ; by leaving the layer out of those stackups - and dropping the layer
        ; here threw that statement away, after which the legend was printed
        ; over every zone alike. It is not body material and must not be built
        ; as such; it is a fact about the zone, so it travels as one.
        ;
        ; Which side by POSITION, not by name: a layer outside the outermost
        ; conductor on the top side is a top-side layer whatever it is called,
        ; and SILKSCREEN_TOP / SILK_TOP / "Silk Screen Top" all reduce to the
        ; same answer without a list of spellings.
        layers = nil
        silkTop = nil
        silkBot = nil
        allSpan = s3dConductorSpan( all )
        i = 0
        foreach( layer all
            if( s3dLayerInBody( layer ) then
                layers = cons( layer layers )
            else
                when( s3dLayerThk( layer ) > 0.0  nSkip = nSkip + 1 )
                when( s3dContains(
                        strcat( if( layer->name then upperCase( layer->name ) else "" ) " "
                                if( stringp( layer->layerFunction )
                                    then upperCase( layer->layerFunction ) else "" ) )
                        "SILK" )
                    if( allSpan && i > cadr( allSpan ) then
                        silkBot = t
                    else
                        silkTop = t
                    )
                )
            )
            i = i + 1
        )
        layers = reverse( layers )

        span = s3dConductorSpan( layers )
        unless( span  layers = nil )

        ; everything outside the top conductor, so the core top lands on 0
        i = 0
        foreach( layer layers
            when( i < car( span )  above = above + s3dLayerThk( layer ) )
            total = total + s3dLayerThk( layer )
            i = i + 1
        )

        when( nSkip > 0
            printf( "Simple 3D: stackup %s - %d silkscreen/paste layer(s) left out of the body.\n"
                    t_name nSkip )
        )

        ; "silkscreen": which SIDES of this stackup carry a printed legend. A
        ; reader that does not know the key behaves exactly as before - the
        ; legend goes everywhere - so an older Simple 3D still builds this file.
        out = strcat( s3dJsonQuote( t_name ) ": {\n"
                      "\t\"thickness\": " sprintf( nil "%f" total ) ",\n"
                      "\t\"silkscreen\": { \"top\": "
                      if( silkTop then "true" else "false" )
                      ", \"bottom\": "
                      if( silkBot then "true" else "false" ) " },\n"
                      "\t\"layers\": [\n" )

        foreach( layer layers
            thk = s3dLayerThk( layer )
            zTop = above - cum
            zBot = zTop - thk
            cum = cum + thk

            ; The two surface entries have no thickness and no material.
            when( thk > 0.0
                shapes = nil
                when( layer->name
                    shapes = s3dLayerShapesJson( layer->name g_state )
                )
                body = strcat(
                    "{\n"
                    "\t\"name\": " s3dJsonQuote( if( layer->name then layer->name else "" ) ) ",\n"
                    "\t\"type\": " s3dJsonQuote( if( layer->layerType then layer->layerType else "" ) ) ",\n"
                    "\t\"thickness\": " sprintf( nil "%f" thk ) ",\n"
                    "\t\"z_top\": " sprintf( nil "%f" zTop ) ",\n"
                    "\t\"z_bottom\": " sprintf( nil "%f" zBot ) ",\n"
                    "\t\"negative\": " if( s3dLayerIsNegative( layer ) then "true" else "false" ) ",\n"
                    "\t\"function\": " s3dJsonQuote( layer->layerFunction ) ",\n"
                    "\t\"shapes\": " if( shapes then s3dAddIndent( shapes ) else "null" ) "\n"
                    "}"
                )
                unless( first  out = strcat( out ",\n" ) )
                first = nil
                out = strcat( out s3dAddIndent( body 2 ) )
            )
        )
        strcat( out "\n\t]\n}" )
    )
)

; Every stackup the design has, keyed by name. Empty object on a plain board.
procedure( s3dStackupsJson( g_state )
    let( ( names out ( first t ) )
        names = nil
        errset( names = axlXSectionGet( nil 'stackups ) )
        if( names then
            out = "\"stackups\": {\n"
            foreach( s names
                when( stringp( s )
                    unless( first  out = strcat( out ",\n" ) )
                    first = nil
                    out = strcat( out s3dAddIndent( s3dStackupJson( s s g_state ) ) )
                )
            )
            strcat( out "\n}" )
        else
            ; An ORDINARY board has no named stackups, but it does have a cross
            ; section, and axlXSectionGet( nil 'all ) returns it. Emitting that
            ; under the name Allegro itself uses for the default - Primary -
            ; lets the reader build a plain board layer by layer too, so "Body
            ; stitching" stops being a setting that silently does nothing on
            ; every board that is not rigid-flex.
            ;
            ; nil is safe as the query ONLY because there are no named stackups
            ; here: on a rigid-flex design nil 'all returns the combined "All
            ; Stackups" view, which is not any real stackup (round 27).
            strcat( "\"stackups\": {\n"
                    s3dAddIndent( s3dStackupJson( "Primary" nil g_state ) )
                    "\n}" )
        )
    )
)

; The zone array: which stackup each zone uses, and its outline. The layer
; geometry lives in "stackups", so a zone is now just an outline plus a
; reference - several zones share one stackup (FLEX1 and FLEX2 here).
procedure( s3dZonesJson()
    let( ( zones contour body out ( first t ) ( n 0 ) )
        zones = s3dZoneList()

        if( zones then
            out = "\"zones\": [\n"
            foreach( z zones
                contour = s3dContourJson( caddr( z ) )
                when( contour
                    n = n + 1
                    unless( first  out = strcat( out ",\n" ) )
                    first = nil
                    body = strcat(
                        "{\n"
                        "\t\"name\": " s3dJsonQuote( car( z ) ) ",\n"
                        "\t\"stackup\": " s3dJsonQuote( cadr( z ) ) ",\n"
                        "\t\"contour\": " s3dAddIndent( contour ) "\n"
                        "}"
                    )
                    out = strcat( out s3dAddIndent( body ) )
                )
            )
            out = strcat( out "\n]" )
            printf( "Simple 3D: %d stackup zone(s) exported.\n" n )
            out
        else
            "\"zones\": []"
        )
    )
)
