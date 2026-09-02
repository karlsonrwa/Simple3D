;=====================================================================
;  skill/s3d_silk.il - the silkscreen: config, collection, clipping, the streamed writer
;
;  Part 8 of 9 of the Simple 3D exporter, cut from
;  makeVariant3dIntermediates.il in round 76 (plan D6) with every procedure
;  and comment as it was; that file loads the parts in order. Load it, or
;  simple3d.il, never a part on its own.
;=====================================================================


;=====================================================================
;  SILKSCREEN  (NEW - simple3d)
;
;  Exports the silkscreen as filled regions so the Python side can extrude
;  them into thin solids sitting on the board faces.
;
;  The whole "line + width -> filled outline" problem is handed to Allegro:
;  axlPolyFromDB turns any line/cline/shape/rect dbid into o_polygon objects
;  with the width already applied and the requested end caps, and
;  axlText2Lines + axlPolyFromDB(?line2poly t) does the same for text (this is
;  the idiom the axlText2Lines documentation itself recommends). Nothing here
;  offsets or strokes geometry by hand.
;
;  Each polygon is written out in the SAME primitive vocabulary the board
;  outline already uses (segment / arc / circle), so the Python reader needs no
;  new geometry parser - build_contour() handles both.
;
;  VARIANTS: silkscreen is deliberately variant-INDEPENDENT. The bare board is
;  manufactured once for every assembly variant, so the printed legend of a
;  component that is not installed in a given variant is still physically on
;  the board. It is therefore collected once per design, not per variant.
;=====================================================================

; Built-in defaults, used when no config file is found (or it fails to parse).
; Mirrors simple3d_config.json - keep the two in step.
S3D_SilkDefaultTop = list(
    "BOARD GEOMETRY/SILKSCREEN_TOP"
    "PACKAGE GEOMETRY/SILKSCREEN_TOP"
    "REF DES/SILKSCREEN_TOP"
    "COMPONENT VALUE/SILKSCREEN_TOP"
)
S3D_SilkDefaultBottom = list(
    "BOARD GEOMETRY/SILKSCREEN_BOTTOM"
    "PACKAGE GEOMETRY/SILKSCREEN_BOTTOM"
    "REF DES/SILKSCREEN_BOTTOM"
    "COMPONENT VALUE/SILKSCREEN_BOTTOM"
)
; Ink thickness in mm. 25 um is a typical cured screen-printed legend.
S3D_SilkDefaultThickness = 0.025

;---------------------------------------------------------------------
;  Silkscreen configuration
;---------------------------------------------------------------------

; Read the config file and return
;   list( l_topLayers l_bottomLayers f_thickness g_clip s_endCap g_export )
; Any missing piece falls back to the built-in default, and a file that cannot
; be read or parsed degrades to all defaults with a message - a broken config
; must never cost the user the whole export.
procedure( s3dSilkConfig( @optional ( t_file nil ) )
    let( ( cfg silk settings top bottom thickness clip endCap doExport )
        top = S3D_SilkDefaultTop
        bottom = S3D_SilkDefaultBottom
        thickness = S3D_SilkDefaultThickness
        clip = t
        endCap = 'ROUND
        doExport = t

        ; The two settings that live in GLOBALS get their defaults back here,
        ; with the locals above and before anything is read - these files load
        ; once per Allegro session, so a global left as the previous export set
        ; it outlives the design that set it (the round-42 trap). Restoring them
        ; further down, inside the branch that parses the file, covered a config
        ; with the key removed but not a board exported with NO config beside it
        ; at all: that one kept the last board's values.
        S3D_ExportFullBoard = t
        S3D_NegativeLayers = S3D_NegativeLayersDefault

        unless( t_file  t_file = "simple3d_config.json" )

        if( isFile( t_file ) then
            ; The tracked defaults with the local file merged over them - see
            ; s3dConfigRead. Reading the base alone would ignore whatever this
            ; installation set for itself.
            cfg = s3dConfigRead( t_file )
            if( cfg then
                printf( "Simple 3D: silkscreen config: %s\n" t_file )
                silk = s3dJsonGet( cfg "silkscreen" )
                settings = s3dJsonGet( cfg "settings" )

                when( s3dJsonList( silk "top" )     top = s3dJsonList( silk "top" ) )
                when( s3dJsonList( silk "bottom" )  bottom = s3dJsonList( silk "bottom" ) )

                when( s3dJsonGet( settings "silkscreenThickness" )
                    thickness = s3dJsonGet( settings "silkscreenThickness" )
                )
                when( s3dJsonHas( settings "clipToBoardOutline" )
                    clip = s3dJsonGet( settings "clipToBoardOutline" )
                )
                when( s3dJsonHas( settings "exportSilkscreen" )
                    doExport = s3dJsonGet( settings "exportSilkscreen" )
                )

                ; Which stackup layers are drawn as openings. Read here rather
                ; than left hardcoded because it is fabricator/site convention,
                ; not something the database states: negativeArtwork reads nil
                ; on every layer even where the polarity is unambiguous.
                ; Its default is restored at the top of this procedure, with
                ; S3D_ExportFullBoard's - see the note there.
                when( s3dJsonList( settings "negativeLayers" )
                    S3D_NegativeLayers = s3dJsonList( settings "negativeLayers" )
                    printf( "Simple 3D: negative (opening) layers: %L\n"
                            S3D_NegativeLayers )
                )

                ; Default restored at the top of this procedure, every time -
                ; see the note there.
                when( s3dJsonHas( settings "exportFullBoard" )
                    S3D_ExportFullBoard = s3dJsonGet( settings "exportFullBoard" )
                )
                when( stringp( s3dJsonGet( settings "endCapType" ) )
                    ; only the three Allegro end-cap keywords are accepted; a
                    ; typo silently becoming 'SQUARE would be hard to notice.
                    case( upperCase( s3dJsonGet( settings "endCapType" ) )
                        ( "ROUND"    endCap = 'ROUND )
                        ( "SQUARE"   endCap = 'SQUARE )
                        ( "OCTAGON"  endCap = 'OCTAGON )
                        ( t
                            s3dWarn( sprintf( nil "Simple 3D: unknown endCapType %L in %s; using ROUND."
                                              s3dJsonGet( settings "endCapType" ) t_file ) )
                        )
                    )
                )
            else
                s3dWarn( sprintf( nil "Simple 3D: could not parse %s; using built-in silkscreen defaults."
                                  t_file ) )
            )
        else
            printf( "Simple 3D: no silkscreen config at %s; using built-in defaults.\n" t_file )
        )
        list( top bottom thickness clip endCap doExport )
    )
)

;---------------------------------------------------------------------
;  Polygon -> JSON vertices
;
;  The polygon boundary goes into the JSON as Allegro's own vertex list -
;  (x, y, signed_radius) per point - and the arcs are rebuilt on the Python
;  side. It used to be rebuilt here, into segment/arc primitives; that put the
;  one genuinely ambiguous decision in the file format, where nothing could
;  check it. See PROJECT_NOTES round 10b: the doc sentence describing the sign
;  of the radius admits two readings, and an arc built on the wrong side of its
;  chord still closes, so the mistake is invisible until someone measures area.
;
;  Python can measure area - every polygon carries Allegro's own poly->area -
;  so it resolves the reading itself, per board, and says which one won. This
;  side therefore reports what the database holds and decides nothing.
;---------------------------------------------------------------------

; Write one vertex list as  [x, y, radius]  rows, indented x_indent tabs.
procedure( s3dWriteVertexList( p_port l_vertices x_indent )
    let( ( pad ( isFirst t ) xy rad )
        pad = ""
        for( i 1 x_indent
            pad = strcat( pad "	" )
        )
        foreach( vertex l_vertices
            if( isFirst then
                isFirst = nil
            else
                fprintf( p_port ",\n" )
            )
            xy = car( vertex )
            rad = cadr( vertex )
            unless( rad  rad = 0.0 )
            fprintf( p_port "%s[%f, %f, %f]" pad xCoord( xy ) yCoord( xy ) rad )
        )
    )
)

;---------------------------------------------------------------------
;  Collecting the silkscreen
;---------------------------------------------------------------------

; Every dbid on a silkscreen layer -> filled polygons.
;
; Text is the only special case. Allegro draws text as strokes, so a text dbid
; is vectorised with axlText2Lines and each resulting r_path is widened into a
; polygon with ?line2poly (verbatim the idiom in the axlText2Lines docs).
; True-type text has no text block and is converted directly instead - that is
; how exportJson tells the two apart as well.
; Messages about objects that were found but could not be exported. Collected
; while sweeping and carried into the JSON so the Python side can show them too
; - the Allegro console scrolls away, the GUI log does not, and it colors a
; line beginning with "warning" orange.
;
; A module-level accumulator rather than a return value: the collector already
; returns layer groups, and threading a second channel through it and through
; the clipper would obscure both for the sake of a message.
S3D_SilkWarnings = nil

; t if this object has no plotted width, and so would vanish in the artwork.
;
; A zero-width line or a text block with zero pen width is a design mistake -
; Allegro's own plot has nothing to draw with either - but axlPolyFromDB does
; not object: it returns nil, or a degenerate polygon that fails later with a
; message about geometry rather than about width. Catching it here lets the
; report name the layer and the place.
;
; Shapes are filled areas with no width to speak of, and true-type text is a
; filled outline with no pen, so neither can be zero-width.
procedure( s3dZeroWidth( o_dbid )
    let( ( w tb ( allZero nil ) segments )
        cond(
            ( o_dbid->objType == "text"
                tb = nil
                when( o_dbid->textBlock
                    errset( tb = axlGetParam( strcat( "paramTextBlock:" o_dbid->textBlock ) ) )
                )
                when( tb
                    w = tb->photoWidth
                    w && (abs( w ) < 1.0e-9)
                )
            )
            ( o_dbid->objType == "shape"  nil )
            ( t
                w = nil
                errset( w = o_dbid->width )
                if( w then
                    abs( w ) < 1.0e-9
                else
                    ; A path can carry its width per segment instead. Only
                    ; call it zero when there ARE segments and every one of
                    ; them is zero - with nothing to look at, say nothing.
                    segments = nil
                    errset( segments = o_dbid->segments )
                    when( segments
                        allZero = t
                        foreach( seg segments
                            when( seg->width && (abs( seg->width ) > 1.0e-9)
                                allZero = nil
                            )
                        )
                        allZero
                    )
                )
            )
        )
    )
)

; "text on REF DES/SILKSCREEN_TOP at (12.500, 4.000)" - enough to find it.
procedure( s3dDescribeObject( o_dbid t_layer )
    let( ( box corner )
        box = nil
        errset( box = o_dbid->bBox )
        corner = when( box  car( box ) )
        if( corner then
            sprintf( nil "%s on %s at (%.3f, %.3f)"
                     o_dbid->objType t_layer xCoord( corner ) yCoord( corner ) )
        else
            sprintf( nil "%s on %s" o_dbid->objType t_layer )
        )
    )
)

; A multi-segment path is converted ONE SEGMENT AT A TIME, and that is the
; whole point rather than an optimisation.
;
; axlPolyFromDB on a whole line/cline MITRES the joins between its segments: on
; a real board, a 0.15 wide line turning a right angle came back with a square
; outer corner whose diagonal offset was exactly 0.075*sqrt(2) - a textbook
; mitre - where the artwork has a round join, because a plot sweeps a round
; aperture along the path. The 3D model then showed sharp corners on some turns
; while others (junctions of two separate lines, where the round END CAPS
; overlap) came out round, which is exactly the inconsistency reported.
;
; Converting each segment separately gives each one round caps, and the union of
; those overlapping stadiums IS a round join. The documentation says the same
; thing from the other direction: of ?line2poly it notes "typically one poly is
; returned for each segment in the r_path" - which is why text, which goes
; through that path, never had the problem.
;
; They are deliberately NOT merged here. The Python side draws a compound of
; overlapping solids anyway, and when clipping is on axlPolyOperation unions
; them as a side effect of the AND.
procedure( s3dPolysFromDbid( o_dbid s_endCap )
    let( ( polys lines flat segments )
        polys = nil
        cond(
            ( o_dbid->objType == "text"
                ; Allegro draws text as strokes, so a text dbid is vectorised
                ; with axlText2Lines and each r_path widened with ?line2poly -
                ; verbatim the idiom in the axlText2Lines docs. True-type text
                ; has no text block and converts directly instead; that is how
                ; exportJson tells the two apart as well.
                if( o_dbid->textBlock then
                    errset( lines = axlText2Lines( o_dbid ) )
                    when( lines
                        flat = foreach( mapcan x lines x )
                        foreach( path flat
                            errset(
                                polys = append( polys
                                    axlPolyFromDB( path ?endCapType s_endCap ?line2poly t ) )
                            )
                        )
                    )
                    ; A font that does not vectorise still has an outline form.
                    unless( polys
                        errset( polys = axlPolyFromDB( o_dbid ?endCapType s_endCap ) )
                    )
                else
                    errset( polys = axlPolyFromDB( o_dbid ?endCapType s_endCap ) )
                )
            )
            ( o_dbid->objType == "path"
                segments = nil
                errset( segments = o_dbid->segments )
                foreach( segment segments
                    errset(
                        polys = append( polys
                            axlPolyFromDB( segment ?endCapType s_endCap ) )
                    )
                )
                ; A segment that will not convert on its own drops a piece of
                ; the line silently, and the area check downstream cannot see a
                ; missing stroke - each surviving polygon is still consistent
                ; with its own area. So say it here. One segment may yield more
                ; than one polygon, hence "fewer than".
                when( segments && (length( polys ) < length( segments ))
                    s3dWarn( sprintf( nil "Simple 3D: a silkscreen line has %d segment(s) but produced only %d polygon(s)."
                                      length( segments ) length( polys ) ) )
                )
                ; Single-segment paths, or a path whose segments will not
                ; convert on their own, still have to come out somehow.
                unless( polys
                    errset( polys = axlPolyFromDB( o_dbid ?endCapType s_endCap ) )
                )
            )
            ( t
                ; shapes, rects, filled areas: a boundary already, nothing to
                ; sweep, so convert whole.
                errset( polys = axlPolyFromDB( o_dbid ?endCapType s_endCap ) )
            )
        )
        polys
    )
)

; All silkscreen polygons on the given layers, GROUPED BY LAYER.
;
; Grouping is what lets the GUI offer the layers as checkboxes: the exporter
; collects every layer the config lists, and which of them actually reach the
; model is then chosen per build, with no re-export. The config answers "what
; exists", the checkboxes answer "what to draw".
;
; One sweep covers both component legends and free board geometry: with the
; silkscreen layers as the only visible ones, axlAddSelectAll returns the
; figures owned by symbols as well as the loose ones (which is why exportJson
; has to filter on elem->parent->refdes - here both are wanted).
;
; The sweep is s3dSelectVisibleOn, which puts the visibility and find-filter
; state back before the conversion below starts.
procedure( s3dCollectSilkByLayer( l_layers s_endCap )
    let( ( elems polys out key groups order zero message ( nBad 0 ) )
        out = nil
        groups = makeTable( "s3dSilkGroups" nil )
        order = tconc( nil nil )
        when( l_layers
            elems = s3dSelectVisibleOn( l_layers list( "noall" "lines" "shapes" "text" )
                                        "Simple 3D: no such layer: %s" )

            foreach( elem elems
                ; Bucket by the SOURCE object's layer, before conversion: a
                ; polygon has no layer of its own, and text loses even the dbid
                ; once axlText2Lines has vectorised it. Still one sweep per
                ; side - sweeping once per layer would multiply the visibility
                ; churn for nothing.
                key = nil
                errset( key = elem->layer )
                unless( stringp( key )  key = sprintf( nil "%L" key ) )

                ; Zero-width objects are reported and skipped rather than fed
                ; to the converter, which would either drop them silently or
                ; fail later with a message about geometry instead of width.
                zero = nil
                errset( zero = s3dZeroWidth( elem ) )
                when( zero
                    message = strcat( "zero width: " s3dDescribeObject( elem key )
                                      " - skipped, it cannot be plotted" )
                    s3dWarn( sprintf( nil "Simple 3D: %s." message ) )
                    S3D_SilkWarnings = cons( message S3D_SilkWarnings )
                )

                ; Per element, so one object the converter cannot handle costs
                ; that object and not the whole side. Before this, a single
                ; failure anywhere in the sweep propagated out of
                ; s3dMakeSilkscreen, was swallowed by the errset at the call
                ; site, and the export finished with no silkscreen at all and
                ; nothing on screen to say why.
                polys = nil
                unless( zero || errset( polys = s3dPolysFromDbid( elem s_endCap ) )
                    nBad = nBad + 1
                    when( nBad == 1
                        s3dWarn( sprintf( nil "Simple 3D: a %s object on %s could not be converted; skipping it (further ones are counted only)."
                                          elem->objType key ) )
                    )
                )
                foreach( poly polys
                    when( poly && !poly->isHole
                        unless( groups[key]
                            groups[key] = tconc( nil nil )
                            tconc( order key )
                        )
                        tconc( groups[key] poly )
                    )
                )
            )
        )

        when( nBad > 0
            s3dWarn( sprintf( nil "Simple 3D: %d silkscreen object(s) could not be converted and were skipped." nBad ) )
        )

        ; -> ( (layer polys) (layer polys) ... ), layers in the order Allegro
        ; first mentioned them, which keeps the GUI's list stable between runs.
        out = tconc( nil nil )
        foreach( key cdr( car( order ) )
            tconc( out list( key cdr( car( groups[key] ) ) ) )
        )
        cdr( car( out ) )
    )
)

; Total polygon count across a side's groups, for the console summary.
procedure( s3dGroupCount( l_groups )
    let( ( ( n 0 ) )
        foreach( group l_groups
            n = n + length( cadr( group ) )
        )
        n
    )
)

;---------------------------------------------------------------------
;  Clipping to the board
;---------------------------------------------------------------------

; The board area as polygons: the design outline minus every cutout - the same
; two sources makePcbContour() uses for the solid, so the silkscreen is clipped
; to exactly the material that exists.
procedure( s3dBoardPoly()
    let( ( dsn outline polys cutouts cutPolys res )
        dsn = axlDBGetDesign()
        outline = dsn->designOutline
        if( outline then
            errset( polys = axlPolyFromDB( outline ) )
            if( polys then
                cutPolys = nil
                cutouts = axlDBGetShapes( "BOARD GEOMETRY/CUTOUT" )
                foreach( cutout cutouts
                    errset( cutPolys = append( cutPolys axlPolyFromDB( cutout ) ) )
                )
                when( cutPolys
                    res = nil
                    errset( res = axlPolyOperation( polys cutPolys 'ANDNOT ) )
                    if( res then
                        polys = remd( nil res )
                    else
                        s3dWarn( "Simple 3D: could not subtract cutouts from the board outline; silkscreen is clipped to the outline only." )
                    )
                )
                polys
            else
                s3dWarn( "Simple 3D: could not convert the design outline to a polygon; silkscreen will not be clipped." )
                nil
            )
        else
            s3dWarn( "Simple 3D: no design outline; silkscreen will not be clipped." )
            nil
        )
    )
)

; t if bounding box l_inner lies entirely within l_outer.
procedure( s3dBBoxInside( l_inner l_outer )
    let( ( ( eps 1.0e-9 ) )
        when( l_inner && l_outer
            (xCoord( car( l_inner ) ) >= xCoord( car( l_outer ) ) - eps) &&
            (yCoord( car( l_inner ) ) >= yCoord( car( l_outer ) ) - eps) &&
            (xCoord( cadr( l_inner ) ) <= xCoord( cadr( l_outer ) ) + eps) &&
            (yCoord( cadr( l_inner ) ) <= yCoord( cadr( l_outer ) ) + eps)
        )
    )
)

; One batch through axlPolyOperation. That API is documented as best-effort
; ("provided as-is ... may fail", returns nil on failure), so a failed batch
; keeps its geometry unclipped and says so, rather than dropping legend that
; is almost certainly on the board anyway.
procedure( s3dClipChunk( l_chunk l_board )
    let( ( res )
        res = nil
        errset( res = axlPolyOperation( l_chunk l_board 'AND ) )
        if( res then
            remd( nil res )
        else
            s3dWarn( sprintf( nil "Simple 3D: silkscreen clip failed for %d polygon(s); kept unclipped."
                              length( l_chunk ) ) )
            l_chunk
        )
    )
)

; Clip silkscreen polygons to the board area.
;
; Two things keep this affordable. Polygons whose bounding box is inside the
; board's are passed through untouched when the board is a plain rectangle with
; no cutouts (the common case, and then correct by construction). The rest go
; through axlPolyOperation in batches: its documentation warns about time and
; memory beyond ~10000 polygons, and batching also contains a failure to the
; batch it happened in.
procedure( s3dClipPolys( l_polys l_board )
    let( ( ( batchSize 400 ) out batch ( n 0 ) fast boardBBox ( inside 0 ) )
        if( !l_board || !l_polys then
            l_polys
        else
            out = tconc( nil nil )
            batch = nil
            fast = (length( l_board ) == 1) && car( l_board )->isRect &&
                   !car( l_board )->holes
            when( fast  boardBBox = car( l_board )->bBox )

            foreach( poly l_polys
                if( fast && s3dBBoxInside( poly->bBox boardBBox ) then
                    inside = inside + 1
                    tconc( out poly )
                else
                    batch = cons( poly batch )
                    n = n + 1
                    when( n >= batchSize
                        foreach( clipped s3dClipChunk( batch l_board )
                            tconc( out clipped )
                        )
                        batch = nil
                        n = 0
                    )
                )
            )
            when( batch
                foreach( clipped s3dClipChunk( batch l_board )
                    tconc( out clipped )
                )
            )
            when( fast
                printf( "Simple 3D: %d silkscreen polygon(s) were wholly inside the board outline (clip skipped).\n"
                        inside )
            )
            cdr( car( out ) )
        )
    )
)

;---------------------------------------------------------------------
;  Top level
;---------------------------------------------------------------------

; Clip each layer's polygons separately.
;
; Clipping a whole side at once would be marginally cheaper, but axlPolyOperation
; unions overlapping polygons, so polygons from different layers would come back
; merged into single regions with no layer left to speak of. Groups that clip to
; nothing are dropped, so a layer that lies entirely off the board does not
; appear in the GUI as an empty choice.
procedure( s3dClipGroups( l_groups l_board )
    let( ( out clipped )
        out = tconc( nil nil )
        foreach( group l_groups
            clipped = s3dClipPolys( cadr( group ) l_board )
            when( clipped
                tconc( out list( car( group ) clipped ) )
            )
        )
        cdr( car( out ) )
    )
)

; Collect the whole silkscreen once for the design.
; -> list( f_thickness l_topPolys l_bottomPolys )  or nil if disabled/empty.
procedure( s3dMakeSilkscreen( l_config )
    let( ( top bottom thickness clip endCap doExport topPolys botPolys board )
        top = nth( 0 l_config )
        bottom = nth( 1 l_config )
        thickness = nth( 2 l_config )
        clip = nth( 3 l_config )
        endCap = nth( 4 l_config )
        doExport = nth( 5 l_config )

        when( doExport
            printf( "Simple 3D: collecting silkscreen...\n" )
            ; Cleared per export, not per side, so both sides report together.
            S3D_SilkWarnings = nil
            ; Both sides come back as ( (layer polys) ... ), so everything from
            ; here on works in groups: s3dGroupCount to count across them and
            ; s3dClipGroups to clip each layer on its own.
            topPolys = s3dCollectSilkByLayer( top endCap )
            botPolys = s3dCollectSilkByLayer( bottom endCap )
            printf( "Simple 3D: silkscreen polygons - top %d, bottom %d\n"
                    s3dGroupCount( topPolys ) s3dGroupCount( botPolys ) )
            foreach( group append( topPolys botPolys )
                printf( "Simple 3D:   %s - %d polygon(s)\n"
                        car( group ) length( cadr( group ) ) )
            )

            when( clip && (topPolys || botPolys)
                board = s3dBoardPoly()
                when( board
                    printf( "Simple 3D: clipping silkscreen to the board outline...\n" )
                    topPolys = s3dClipGroups( topPolys board )
                    botPolys = s3dClipGroups( botPolys board )
                    printf( "Simple 3D: after clipping - top %d, bottom %d\n"
                            s3dGroupCount( topPolys ) s3dGroupCount( botPolys ) )
                )
            )

            when( S3D_SilkWarnings
                s3dWarn( sprintf( nil "Simple 3D: %d silkscreen object(s) were skipped; see the warnings above and the GUI log."
                                  length( S3D_SilkWarnings ) ) )
            )

            when( topPolys || botPolys
                list( thickness topPolys botPolys reverse( S3D_SilkWarnings ) )
            )
        )
    )
)

; Stream one side's polygons into the open file.
;
; Streamed rather than accumulated into one string: a dense board's legend runs
; to tens of thousands of primitives, and building that with repeated strcat is
; quadratic and hits the same "insufficient memory" wall the component section
; already has a note about.
procedure( s3dWriteSilkPolys( p_port l_groups )
    let( ( ( firstPoly t ) holes ( firstHole t ) area layer )
        foreach( group l_groups
        layer = car( group )
        foreach( poly cadr( group )
            if( firstPoly then
                firstPoly = nil
            else
                fprintf( p_port ",\n" )
            )
            fprintf( p_port "\t\t\t{\n" )

            ; Which layer this polygon came from. The array stays FLAT - one
            ; object per polygon, exactly as before - so a reader that ignores
            ; this key still builds the whole legend.
            fprintf( p_port "\t\t\t\t\"layer\": %s,\n" s3dJsonQuote( layer ) )

            ; Allegro's own area for this polygon, already net of its holes.
            ; This is the reference the Python side resolves the arc convention
            ; against and then verifies every polygon by, so it is not optional
            ; bookkeeping - without it the reconstruction has nothing to check
            ; itself against. Costs one float per polygon.
            area = nil
            errset( area = poly->area )
            when( area
                fprintf( p_port "\t\t\t\t\"area\": %f,\n" area )
            )

            fprintf( p_port "\t\t\t\t\"vertices\": [\n" )
            s3dWriteVertexList( p_port poly->vertices 5 )
            fprintf( p_port "\n\t\t\t\t]" )

            holes = poly->holes
            when( holes
                fprintf( p_port ",\n\t\t\t\t\"holes\": [\n" )
                firstHole = t
                foreach( hole holes
                    if( firstHole then
                        firstHole = nil
                    else
                        fprintf( p_port ",\n" )
                    )
                    fprintf( p_port "\t\t\t\t\t[\n" )
                    s3dWriteVertexList( p_port hole->vertices 6 )
                    fprintf( p_port "\n\t\t\t\t\t]" )
                )
                fprintf( p_port "\n\t\t\t\t]" )
            )
            fprintf( p_port "\n\t\t\t}" )
        )
        )
    )
)

; The whole "silkscreen" object, written straight to the open file.
procedure( s3dWriteSilkscreen( p_port l_silk )
    let( ( thickness topPolys botPolys warnings ( firstWarn t ) )
        thickness = nth( 0 l_silk )
        topPolys = nth( 1 l_silk )
        botPolys = nth( 2 l_silk )
        warnings = nth( 3 l_silk )

        fprintf( p_port "\t\"silkscreen\": {\n" )
        fprintf( p_port "\t\t\"thickness\": %f,\n" thickness )

        ; What was found and could not be exported. Carried across so the GUI
        ; can repeat it: the Allegro console has scrolled past by the time
        ; anyone looks at the model.
        when( warnings
            fprintf( p_port "\t\t\"warnings\": [\n" )
            foreach( message warnings
                if( firstWarn then
                    firstWarn = nil
                else
                    fprintf( p_port ",\n" )
                )
                fprintf( p_port "\t\t\t%s" s3dJsonQuote( message ) )
            )
            fprintf( p_port "\n\t\t],\n" )
        )
        fprintf( p_port "\t\t\"top\": [\n" )
        s3dWriteSilkPolys( p_port topPolys )
        fprintf( p_port "\n\t\t],\n" )
        fprintf( p_port "\t\t\"bottom\": [\n" )
        s3dWriteSilkPolys( p_port botPolys )
        fprintf( p_port "\n\t\t]\n" )
        fprintf( p_port "\t}\n" )
    )
)
