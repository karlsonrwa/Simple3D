;=====================================================================
;  probe_pads_masks.il - DIAGNOSTIC ONLY. Reads the design, changes nothing.
;
;  Round 126 (R4-10 of the 23.10.2026 review): the oracle for the mask
;  OPENINGS as probe_pads_poly.il is the oracle for the copper. For every
;  pin and via, the pad polygons Allegro itself puts on the two outer etch
;  layers and on the two soldermask subclasses of the object's class (PIN
;  for a pin, VIA CLASS for a via), as an area and a bounding box, beside
;  the object's own placement. The fixture tests/fixtures/pads_masks.json
;  is a sample of these lines with the padstack library of the same
;  board's export; test_pads [20] rebuilds each pad and opening from the
;  library and compares.
;
;  One line per pin or via, tab separated:
;    OBJ <kind> <padstack> <x> <y> <rotation> <mirrored 0/1>
;        ETCH_TOP <n> <area> <x0> <y0> <x1> <y1>   ETCH_BOTTOM ...
;        MASK_TOP ...   MASK_BOTTOM ...
;  A layer with no polygon prints 0 0.0 - - - -.
;
;  REQUIRES: makeVariant3dIntermediates.il (s3dSelectVisibleOn, s3dViaLayers)
;  Usage:  load("<path>/probe_pads_masks.il")   then   s3dProbePadsMasks()
;=====================================================================

procedure( s3dProbeMaskPolyOn( o_obj t_layer )
    let( ( polys ( n 0 ) ( area 0.0 ) bb x0 y0 x1 y1 )
        polys = nil
        errset( polys = axlPolyFromDB( o_obj ?layer t_layer ?padType 'REGULAR ) )
        polys = remd( nil polys )
        n = length( polys )
        if( n == 0 then
            "0\t0.0\t-\t-\t-\t-"
        else
            x0 = nil
            foreach( p polys
                when( p->area  area = area + abs( p->area ) )
                bb = p->bBox
                when( bb
                    if( x0 then
                        x0 = min( x0 xCoord( car( bb ) ) )
                        y0 = min( y0 yCoord( car( bb ) ) )
                        x1 = max( x1 xCoord( cadr( bb ) ) )
                        y1 = max( y1 yCoord( cadr( bb ) ) )
                    else
                        x0 = xCoord( car( bb ) )
                        y0 = yCoord( car( bb ) )
                        x1 = xCoord( cadr( bb ) )
                        y1 = yCoord( cadr( bb ) )
                    )
                )
            )
            sprintf( nil "%d\t%.6f\t%.6f\t%.6f\t%.6f\t%.6f" n area x0 y0 x1 y1 )
        )
    )
)

procedure( s3dProbeMaskLine( o_obj t_kind t_class )
    printf( "OBJ\t%s\t%s\t%.6f\t%.6f\t%.6f\t%d\tETCH_TOP\t%s\tETCH_BOTTOM\t%s\tMASK_TOP\t%s\tMASK_BOTTOM\t%s\n"
            t_kind o_obj->name xCoord( o_obj->xy ) yCoord( o_obj->xy )
            if( numberp( o_obj->rotation ) then o_obj->rotation else 0.0 )
            if( o_obj->isMirrored then 1 else 0 )
            s3dProbeMaskPolyOn( o_obj "ETCH/TOP" )
            s3dProbeMaskPolyOn( o_obj "ETCH/BOTTOM" )
            s3dProbeMaskPolyOn( o_obj strcat( t_class "/SOLDERMASK_TOP" ) )
            s3dProbeMaskPolyOn( o_obj strcat( t_class "/SOLDERMASK_BOTTOM" ) ) )
)

procedure( s3dProbePadsMasks()
    let( ( dsn vias ( n 0 ) ( nv 0 ) )
        dsn = axlDBGetDesign()
        printf( "\n===== PAD AND MASK POLYGONS PER PIN AND VIA =====\n" )
        foreach( sym dsn->symbols
            foreach( pin sym->pins
                when( stringp( pin->name ) && pin->xy
                    n = n + 1
                    s3dProbeMaskLine( pin "pin" "PIN" )
                )
            )
        )
        vias = nil
        errset( vias = s3dSelectVisibleOn( s3dViaLayers() list( "noall" "vias" )
                                           "probe_pads_masks: no such layer: %s" ) )
        foreach( v vias
            when( stringp( v->name ) && v->xy
                nv = nv + 1
                s3dProbeMaskLine( v "via" "VIA CLASS" )
            )
        )
        printf( "===== %d pin(s), %d via(s) =====\n" n nv )
        t
    )
)
