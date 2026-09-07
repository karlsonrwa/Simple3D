;=====================================================================
;  probe_maskrect.il - DIAGNOSTIC. Changes the SCRATCH COPY it runs on.
;
;  A rectangle drawn on a mask layer is an opening like a line or a shape
;  is: the find filter's "shapes" keyword "enables shapes, rects and frects"
;  (axlSetFindFilter reference), so the exporter's opening sweep should take
;  it without a word of its own. No board in input/ carries one, so this
;  probe makes the case: an unfilled and a filled rectangle on PACKAGE
;  GEOMETRY/SOLDERMASK_TOP over my_test_board2's pour (the two real mask
;  shapes sit around (2.6..5.5, 2.8..5.6)), then the exporter runs and its
;  opening count and copper polygons say what the sweep made of them.
;
;  Runs in the runner's scratch copy, so the user's board is not touched:
;    set S3D_PROBE_OUT=<folder>
;    python tools/run_probe.py --with-exporter tools/probes/probe_maskrect.il s3dProbeMaskRect BOARD.brd
;  REQUIRES: makeVariant3dIntermediates.il
;=====================================================================

procedure( s3dProbeMaskRect()
    let( ( plain filled out )
        out = nil
        errset( out = getShellEnvVar( "S3D_PROBE_OUT" ) )
        unless( stringp( out ) && (out != "")  out = s3dDesignFolder() )
        plain = nil
        filled = nil
        errset( plain = axlDBCreateRectangle( list( 2.7:2.9 3.4:3.6 ) nil "PACKAGE GEOMETRY/SOLDERMASK_TOP" ) )
        errset( filled = axlDBCreateRectangle( list( 4.0:2.9 4.7:3.6 ) t "PACKAGE GEOMETRY/SOLDERMASK_TOP" ) )
        printf( "probe_maskrect: unfilled rectangle %L, filled rectangle %L on PACKAGE GEOMETRY/SOLDERMASK_TOP\n"
                plain filled )
        foreach( made list( plain filled )
            when( made
                printf( "  made %L objType %L bBox %L\n" car( made ) car( made )->objType car( made )->bBox )
            )
        )
        drain( poport )
        makeVariant3dIntermediates( out nil )
        t
    )
)
