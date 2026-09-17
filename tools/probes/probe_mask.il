;=====================================================================
;  probe_mask.il - DIAGNOSTIC ONLY. Reads the design, changes nothing.
;
;  What the soldermask OPENINGS of a board are made of, beyond the pins'
;  own mask pads - the data an "exposed copper" export would need:
;
;   1. how many drawn objects sit on each SOLDERMASK subclass (shapes,
;      lines, rects, text, and the PIN / VIA CLASS flashes), by class
;   2. a pin's mask pad through axlDBGetPad( pin "PIN/SOLDERMASK_TOP"
;      "REGULAR" ) - the documented way - beside its etch pad; same for a
;      via. NOT axlPolyFromDB with a mask ?layer: two headless sessions sat
;      for ten minutes with that call in them and never came back.
;   3. one mask SHAPE against the copper under it: the etch objects whose
;      box meets the shape's (axlAddSelectBox with BOTH corners - given
;      one or none it prompts for a pick, which is a hang with no window),
;      each shape taken THROUGH ?window so a pour with thousands of voids
;      is not converted whole, then axlPolyOperation AND - does it work,
;      what does it cost
;
;  Progress goes to <probe-out>/probe_mask.progress.txt, drained after every
;  line, so a session that hangs still says where.
;
;  Usage:  python tools/run_probe.py tools/probes/probe_mask.il s3dProbeMask BOARD.brd
;  Loads on its own: the one sweep it needs is written out here rather than
;  taken from the exporter, which a probe loaded alone does not have.
;=====================================================================

S3D_ProbeMaskPort = nil

; The folder of a path, scanning for the last separator.
procedure( s3dProbeMaskFolder( t_path )
    let( ( ( cut 0 ) c )
        unless( stringp( t_path )  t_path = "" )
        for( i 1 strlen( t_path )
            c = substring( t_path i 1 )
            when( (c == "/") || (c == "\\")  cut = i )
        )
        if( cut > 1 then substring( t_path 1 cut - 1 ) else "." )
    )
)

; One line to the console AND to the progress file, drained at once.
procedure( s3dProbeMaskSay( t_line )
    printf( "%s\n" t_line )
    when( S3D_ProbeMaskPort
        fprintf( S3D_ProbeMaskPort "%s\n" t_line )
        drain( S3D_ProbeMaskPort )
    )
)

; Everything on one subclass, with the design otherwise hidden - the
; exporter's s3dSelectVisibleOn in miniature, so the probe loads on its own.
procedure( s3dProbeMaskSelect( t_layer l_filter )
    let( ( saveVis elems )
        saveVis = axlVisibleGet()
        axlVisibleDesign( nil )
        unless( axlVisibleLayer( t_layer t )
            s3dProbeMaskSay( sprintf( nil "  (no such layer: %s)" t_layer ) )
        )
        axlClearSelSet()
        axlSetFindFilter( ?enabled l_filter ?onButtons l_filter )
        axlAddSelectAll()
        elems = axlGetSelSet()
        axlClearSelSet()
        errset( axlVisibleSet( saveVis ) )
        elems
    )
)

procedure( s3dProbeMaskCount( t_layer )
    let( ( elems ( n 0 ) kinds line )
        kinds = makeTable( "s3dProbeMaskKinds" 0 )
        elems = s3dProbeMaskSelect( t_layer list( "noall" "lines" "shapes" "text" "pins" "vias" ) )
        foreach( e elems
            n = n + 1
            kinds[e->objType] = kinds[e->objType] + 1
        )
        line = sprintf( nil "  %-42s %6d object(s)" t_layer n )
        foreach( k kinds->?
            line = strcat( line sprintf( nil "  %s %d" k kinds[k] ) )
        )
        s3dProbeMaskSay( line )
        n
    )
)

procedure( s3dProbeMaskPad( o_obj t_kind t_layer )
    let( ( pd )
        pd = nil
        errset( pd = axlDBGetPad( o_obj t_layer "REGULAR" ) )
        if( pd then
            sprintf( nil "%s %s: %s bBox %L" t_kind t_layer pd->figureName pd->bBox )
        else
            sprintf( nil "%s %s: nil" t_kind t_layer )
        )
    )
)

; The parts, each runnable alone in its own session (run_mask_parts.py):
; a part that hangs then costs one short session and names itself.
procedure( s3dProbeMaskOpen()
    let( ( path folder )
        path = nil
        errset( path = axlGetDrawingName() )
        folder = s3dProbeMaskFolder( path )
        S3D_ProbeMaskPort = outfile( strcat( folder "/../probe_mask.progress.txt" ) )
        printf( "probe_mask: drawing %L, progress port %L\n" path S3D_ProbeMaskPort )
        s3dProbeMaskSay( sprintf( nil "probe_mask on %L" path ) )
    )
)

procedure( s3dProbeMaskClose()
    s3dProbeMaskSay( "===== done =====" )
    when( S3D_ProbeMaskPort
        close( S3D_ProbeMaskPort )
        S3D_ProbeMaskPort = nil
    )
    t
)

procedure( s3dProbeMaskP0()
    let( ( dsn shown polys area bb shapes copper res t0 t1 n )
        dsn = axlDBGetDesign()
        s3dProbeMaskOpen()

        s3dProbeMaskSay( "===== 0. hello =====" )
        s3dProbeMaskClose()
    )
)

procedure( s3dProbeMaskP1()
    let( ( dsn shown polys area bb shapes copper res t0 t1 n )
        dsn = axlDBGetDesign()
        s3dProbeMaskOpen()
        s3dProbeMaskSay( "===== 1. OBJECTS ON THE SOLDERMASK SUBCLASSES =====" )
        foreach( lay list( "BOARD GEOMETRY/SOLDERMASK_TOP" "PACKAGE GEOMETRY/SOLDERMASK_TOP"
                           "MANUFACTURING/SOLDERMASK_TOP" "PIN/SOLDERMASK_TOP" "VIA CLASS/SOLDERMASK_TOP"
                           "BOARD GEOMETRY/SOLDERMASK_BOTTOM" "PACKAGE GEOMETRY/SOLDERMASK_BOTTOM"
                           "MANUFACTURING/SOLDERMASK_BOTTOM" "PIN/SOLDERMASK_BOTTOM" "VIA CLASS/SOLDERMASK_BOTTOM" )
            unless( errset( s3dProbeMaskCount( lay ) t )
                s3dProbeMaskSay( sprintf( nil "  %s: the count FAILED" lay ) )
            )
        )
        s3dProbeMaskClose()
    )
)

procedure( s3dProbeMaskP2()
    let( ( dsn shown polys area bb shapes copper res t0 t1 n )
        dsn = axlDBGetDesign()
        s3dProbeMaskOpen()
        s3dProbeMaskSay( "===== 2. A PIN'S MASK PAD BESIDE ITS ETCH PAD (axlDBGetPad) =====" )
        shown = 0
        foreach( sym dsn->symbols
            foreach( pin sym->pins
                when( shown < 3
                    s3dProbeMaskSay( sprintf( nil "  pin %s at %L: %s | %s"
                                              pin->name pin->xy
                                              s3dProbeMaskPad( pin "pin" "PIN/SOLDERMASK_TOP" )
                                              s3dProbeMaskPad( pin "pin" "ETCH/TOP" ) ) )
                    shown = shown + 1
                )
            )
        )
        s3dProbeMaskClose()
    )
)

procedure( s3dProbeMaskP2b()
    let( ( dsn shown polys area bb shapes copper res t0 t1 n )
        dsn = axlDBGetDesign()
        s3dProbeMaskOpen()
        s3dProbeMaskSay( "===== 2b. A VIA'S MASK PAD (axlDBGetPad) =====" )
        shown = 0
        foreach( v s3dProbeMaskSelect( "VIA CLASS/TOP" list( "noall" "vias" ) )
            when( shown < 3
                s3dProbeMaskSay( sprintf( nil "  via %s at %L: %s | %s"
                                          v->name v->xy
                                          s3dProbeMaskPad( v "via" "VIA CLASS/SOLDERMASK_TOP" )
                                          s3dProbeMaskPad( v "via" "ETCH/TOP" ) ) )
                shown = shown + 1
            )
        )
        s3dProbeMaskClose()
    )
)

procedure( s3dProbeMaskP3()
    let( ( dsn shown polys area bb shapes copper res t0 t1 n )
        dsn = axlDBGetDesign()
        s3dProbeMaskOpen()
        s3dProbeMaskSay( "===== 3. ONE MASK SHAPE AGAINST THE COPPER UNDER IT =====" )
        shapes = nil
        errset( shapes = axlDBGetShapes( "BOARD GEOMETRY/SOLDERMASK_TOP" ) )
        unless( shapes  errset( shapes = axlDBGetShapes( "PACKAGE GEOMETRY/SOLDERMASK_TOP" ) ) )
        if( shapes then
            shown = 0
            foreach( s shapes
                when( shown < 4
                    shown = shown + 1
                    bb = nil
                    errset( bb = s->bBox )
                    polys = nil
                    errset( polys = axlPolyFromDB( s ) )
                    polys = remd( nil polys )
                    s3dProbeMaskSay( sprintf( nil "  mask shape at %L: %d poly(s)" bb length( polys ) ) )
                    ; the copper: everything on ETCH/TOP inside the shape's box.
                    ; BOTH corners, always - one corner or nil is a prompt.
                    copper = nil
                    n = 0
                    when( bb && car( bb ) && cadr( bb )
                        t0 = getCurrentTime()
                        axlClearSelSet()
                        axlSetFindFilter( ?enabled list( "noall" "clines" "shapes" "pins" "vias" )
                                          ?onButtons list( "noall" "clines" "shapes" "pins" "vias" ) )
                        axlVisibleDesign( nil )
                        axlVisibleLayer( "ETCH/TOP" t )
                        when( errset( axlAddSelectBox( list( car( bb ) cadr( bb ) ) ) t )
                            foreach( o axlGetSelSet()
                                n = n + 1
                                when( n <= 200
                                    if( o->objType == "shape" then
                                        errset( copper = append( copper remd( nil axlPolyFromDB( o ?window bb ) ) ) )
                                    else
                                        errset( copper = append( copper remd( nil axlPolyFromDB( o ?layer "ETCH/TOP" ?padType 'REGULAR ?endCapType 'ROUND ) ) ) )
                                    )
                                )
                            )
                        )
                        axlClearSelSet()
                        axlVisibleDesign( t )
                        s3dProbeMaskSay( sprintf( nil "    %d etch object(s) in its box -> %d copper poly(s) (first 200 objects) [%s]"
                                                  n length( copper ) getCurrentTime() ) )
                    )
                    when( polys && copper
                        res = nil
                        errset( res = axlPolyOperation( polys copper 'AND ) t )
                        res = remd( nil res )
                        area = 0.0
                        foreach( p res  when( p->area  area = area + p->area ) )
                        t1 = getCurrentTime()
                        s3dProbeMaskSay( sprintf( nil "    AND -> %d poly(s), area %L (opening area %L)  [%s .. %s]"
                                                  length( res ) area car( polys )->area t0 t1 ) )
                    )
                )
            )
        else
            s3dProbeMaskSay( "  no mask shapes on BOARD GEOMETRY or PACKAGE GEOMETRY / SOLDERMASK_TOP" )
        )
        s3dProbeMaskClose()
    )
)

procedure( s3dProbeMask()
    s3dProbeMaskP1()
    s3dProbeMaskP2()
    s3dProbeMaskP2b()
    s3dProbeMaskP3()
)
