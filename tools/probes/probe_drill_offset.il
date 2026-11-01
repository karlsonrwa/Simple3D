;=====================================================================
;  probe_drill_offset.il - round 128, R1-4 of the 23.10.2026 review:
;  where Allegro puts the drill of a pin whose padstack carries a drill
;  offset - on parts placed turned and mirrored as the board has them -
;  and where the exporter's s3dDrillXY puts it.
;
;  s3dProbeDrillOffset - on the runner's scratch copy, never saved: every
;      padstack a drilled component pin uses is given the drill offset
;      (0.375 0.25) by axlPadstackEdit; then for every such pin a line with
;      its refdes and number, xy, rotation and mirror flag, the offset the
;      design's padstack and the one axlLoadPadstack hands the exporter
;      carry, Allegro's own drill (the centre of axlPolyFromDrillHole's
;      box) and s3dDrillXY's answer. Nothing is moved: a pin read after
;      axlTransformObject kept its old rotation and mirror flag in the
;      first version of this probe, while Allegro's drill had moved.
;
;    python tools/run_probe.py --with-exporter tools/probes/probe_drill_offset.il s3dProbeDrillOffset <board>
;  REQUIRES: makeVariant3dIntermediates.il
;=====================================================================

procedure( s3dProbeDrillOffset()
    let( ( pins done padstack poly box drill ours lib )
        pins = nil
        foreach( s axlDBGetDesign()->symbols
            when( s->refdes
                foreach( pin s->pins
                    padstack = nil
                    errset( padstack = pin->definition )
                    when( padstack && padstack->drillDiameter && (padstack->drillDiameter > 0)
                        pins = cons( list( s->refdes pin ) pins )
                    )
                )
            )
        )
        printf( "S3DDRILL %d drilled component pin(s)\n" length( pins ) )
        done = makeTable( "s3dProbeDrillDone" nil )
        foreach( entry pins
            padstack = cadr( entry )->definition
            unless( done[padstack->name]
                done[padstack->name] = t
                printf( "S3DDRILL padstack %s given the offset (0.375 0.25): %L\n" padstack->name
                        car( errset( axlPadstackEdit( padstack 'drillOffset list( 0.375 0.25 ) ) t ) ) )
            )
        )
        foreach( entry reverse( pins )
            padstack = cadr( entry )->definition
            poly = nil
            errset( poly = axlPolyFromDrillHole( cadr( entry ) ) t )
            box = nil
            when( poly  errset( box = car( poly )->bBox ) )
            drill = when( box
                list( (xCoord( car( box ) ) + xCoord( cadr( box ) )) / 2.0
                      (yCoord( car( box ) ) + yCoord( cadr( box ) )) / 2.0 ) )
            lib = nil
            errset( lib = axlLoadPadstack( cadr( entry )->name ) t )
            ours = nil
            when( lib  errset( ours = s3dDrillXY( cadr( entry ) lib ) t ) )
            printf( "S3DPIN %s %s | xy %L | rotation %L | mirrored %L | offset %L %L | allegro %L | s3dDrillXY %L\n"
                    car( entry ) cadr( entry )->number cadr( entry )->xy cadr( entry )->rotation
                    cadr( entry )->isMirrored padstack->drillOffset when( lib lib->drillOffset ) drill ours )
        )
        drain( poport )
        t
    )
)
