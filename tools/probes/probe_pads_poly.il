;=====================================================================
;  probe_pads_poly.il - DIAGNOSTIC ONLY. Reads the design, changes nothing.
;
;  The ORACLE for the copper-pad export: for every pin, the pad polygon
;  Allegro itself puts on ETCH/TOP and ETCH/BOTTOM (axlPolyFromDB with
;  ?layer), as a bounding box and an area, beside the pin's own placement
;  (padstack, xy, rotation, isMirrored). The Python side rebuilds the pad
;  from the padstack library and the placement, and a test compares the
;  two - that is what settles which side a mirrored pin's pad lands on and
;  which way its figure is mirrored, instead of a reading of the docs.
;
;  One line per pin, tab separated:
;    PIN <padstack> <x> <y> <rotation> <mirrored 0/1> <through 0/1>
;        TOP <n polys> <area> <bbox x0 y0 x1 y1>   BOTTOM <n> <area> <bbox>
;  A layer with no polygon prints 0 0.0 - - - -.
;
;  Usage:  load("<path>/probe_pads_poly.il")   then   s3dProbePadsPoly()
;=====================================================================

procedure( s3dProbePolyOn( o_pin t_layer )
    let( ( polys ( n 0 ) ( area 0.0 ) bb x0 y0 x1 y1 )
        polys = nil
        errset( polys = axlPolyFromDB( o_pin ?layer t_layer ?padType 'REGULAR ) )
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

procedure( s3dProbePadsPoly()
    let( ( dsn ( n 0 ) )
        dsn = axlDBGetDesign()
        printf( "\n===== PAD POLYGONS PER PIN =====\n" )
        foreach( sym dsn->symbols
            foreach( pin sym->pins
                n = n + 1
                printf( "PIN\t%s\t%.6f\t%.6f\t%.6f\t%d\t%d\tTOP\t%s\tBOTTOM\t%s\n"
                        pin->name xCoord( pin->xy ) yCoord( pin->xy )
                        if( numberp( pin->rotation ) then pin->rotation else 0.0 )
                        if( pin->isMirrored then 1 else 0 )
                        if( pin->isThrough then 1 else 0 )
                        s3dProbePolyOn( pin "ETCH/TOP" )
                        s3dProbePolyOn( pin "ETCH/BOTTOM" ) )
            )
        )
        printf( "===== %d pin(s) =====\n" n )
        t
    )
)
