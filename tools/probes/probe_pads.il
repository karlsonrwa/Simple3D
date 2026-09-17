;=====================================================================
;  probe_pads.il - DIAGNOSTIC ONLY. Reads the design, changes nothing.
;
;  What a pin's padstack says about its copper, as the database holds it,
;  before an exporter is written on top of it (memory: probe, don't guess -
;  every guessed attribute name was wrong and failed silently).
;
;   1. every attribute of one pad (pd->??) and one padstack (ps->??)
;   2. per distinct padstack: usage, isThrough, drill, offset, and every
;      REGULAR pad on an ETCH layer with figureName, bBox, offset, radius,
;      sides, inside, corners - and for SHAPE pads the path walked with
;      axlPathGetPathSegs / axlPathSegGetEndPoint / axlPathSegGetArcCenter
;   3. the count of pins by (padstack, isMirrored, rotation) so the
;      placement side rule can be checked against real numbers
;
;  Usage:  load("<path>/probe_pads.il")   then   s3dProbePads()
;  Headless: allegro -nograph -s <abs .scr> <board copy>, the .scr does
;  `skill load(...)`, `skill s3dProbePads()`, `exit`.
;=====================================================================

procedure( s3dProbePadPath( pth t_indent )
    let( ( segs prev e c cw ( n 0 ) )
        segs = nil
        errset( segs = axlPathGetPathSegs( pth ) )
        printf( "%spath: %d segment(s)\n" t_indent length( segs ) )
        foreach( sg segs
            e = nil  c = nil  cw = nil
            errset( e = axlPathSegGetEndPoint( sg ) )
            errset( c = axlPathSegGetArcCenter( sg ) )
            errset( cw = axlPathSegGetArcClockwise( sg ) )
            n = n + 1
            when( n <= 40
                printf( "%s  end %L  center %L  cw %L\n" t_indent e c cw )
            )
            prev = e
        )
    )
)

procedure( s3dProbePadstack( t_name )
    let( ( ps pads ( nEtch 0 ) lay )
        ps = nil
        errset( ps = axlLoadPadstack( t_name ) )
        if( !ps then
            printf( "  %s: axlLoadPadstack -> nil\n" t_name )
        else
            printf( "\n--- padstack %s ---\n" t_name )
            errset( printf( "  usage %L  type %L  isThrough %L  holeType %L  plating %L\n"
                            ps->usage ps->type ps->isThrough ps->holeType ps->plating ) )
            errset( printf( "  drillDiameter %L  drillSizeWidth %L  drillSizeHeight %L  drillOffset %L  startEnd %L\n"
                            ps->drillDiameter ps->drillSizeWidth ps->drillSizeHeight
                            ps->drillOffset ps->startEnd ) )
            pads = nil
            errset( pads = ps->pads )
            printf( "  %d pad entries\n" length( pads ) )
            foreach( pd pads
                lay = nil
                errset( lay = pd->layer )
                when( pd->figureName && !( upperCase( pd->figureName ) == "NULL" )
                    printf( "  pad layer %L type %L figure %L bBox %L offset %L radius %L sides %L inside %L corners %L name %L\n"
                            lay pd->type pd->figureName pd->bBox pd->offset
                            pd->radius pd->sides pd->inside pd->corners pd->name )
                    when( pd->figure
                        printf( "    figure: %L\n" pd->figure )
                        foreach( pth pd->figure
                            s3dProbePadPath( pth "    " )
                        )
                    )
                )
            )
        )
    )
)

procedure( s3dProbePads()
    let( ( dsn names seen ( nPins 0 ) ( nMir 0 ) key counts ps pd shown pads rots )
        dsn = axlDBGetDesign()
        printf( "\n===== PAD FIGURE TYPES THIS ALLEGRO KNOWS =====\n" )
        errset( printf( "%L\n" axlPadFigureTypes() ) )

        printf( "\n===== ONE PAD, EVERY ATTRIBUTE (pd->??) =====\n" )
        shown = nil
        foreach( sym dsn->symbols
            foreach( pin sym->pins
                unless( shown
                    printf( "pin->?? = %L\n" pin->?? )
                    printf( "pin: name %L xy %L rotation %L isMirrored %L isThrough %L isMech %L startEnd %L\n"
                            pin->name pin->xy pin->rotation pin->isMirrored pin->isThrough pin->isMech pin->startEnd )
                    ps = nil
                    errset( ps = axlLoadPadstack( pin->name ) )
                    when( ps
                        printf( "padstack->?? = %L\n" ps->?? )
                        pads = nil
                        errset( pads = ps->pads )
                        foreach( p pads
                            unless( shown
                                when( p->figureName && !( upperCase( p->figureName ) == "NULL" )
                                    printf( "pad->?? = %L\n" p->?? )
                                    shown = t
                                )
                            )
                        )
                    )
                    shown = t
                )
            )
        )

        printf( "\n===== PINS BY PADSTACK / MIRROR / ROTATION =====\n" )
        counts = makeTable( "s3dProbeCounts" 0 )
        rots = makeTable( "s3dProbeRots" 0 )
        names = nil
        foreach( sym dsn->symbols
            foreach( pin sym->pins
                nPins = nPins + 1
                when( pin->isMirrored  nMir = nMir + 1 )
                key = sprintf( nil "%s|%L" pin->name pin->isMirrored )
                counts[key] = counts[key] + 1
                rots[pin->rotation] = rots[pin->rotation] + 1
                unless( member( pin->name names )  names = cons( pin->name names ) )
            )
        )
        printf( "%d pin(s), %d mirrored, %d distinct padstack(s)\n" nPins nMir length( names ) )
        foreach( k counts->?
            printf( "  %-40s %d\n" k counts[k] )
        )
        printf( "rotations:\n" )
        foreach( r rots->?
            printf( "  %L: %d\n" r rots[r] )
        )

        printf( "\n===== EVERY DISTINCT PADSTACK =====\n" )
        foreach( n reverse( names )
            s3dProbePadstack( n )
        )
        printf( "\n===== done =====\n" )
        t
    )
)
