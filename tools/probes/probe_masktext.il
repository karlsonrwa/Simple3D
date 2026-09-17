;=====================================================================
;  probe_masktext.il - DIAGNOSTIC. Changes the COPY of the board it runs
;  on (the runner's scratch copy, never the original) and does not save it.
;
;  No board in input/ has text on a soldermask layer, so the case is made:
;  a text object is created on PACKAGE GEOMETRY/SOLDERMASK_TOP over an area
;  known to carry a copper pour, and the exporter is run into a folder given
;  by the environment variable S3D_PROBE_OUT (falls back to the design's
;  folder). The intermediate's pads.exposed.top should then carry the
;  copper under the letters, area-checked by the reader.
;
;  REQUIRES: makeVariant3dIntermediates.il
;=====================================================================

procedure( s3dProbeMaskText()
    let( ( made out )
        out = nil
        errset( out = getShellEnvVar( "S3D_PROBE_OUT" ) )
        unless( stringp( out ) && (out != "")  out = s3dDesignFolder() )
        ; my_test_board2: the two real mask shapes sit over a pour around
        ; (2.6..5.5, 2.8..5.6); a text there crosses that copper. The third
        ; argument is the text block size ID as a string - the reference
        ; allows that in place of the axlTextOrientation struct, and the
        ; rest of the orientation then takes its defaults.
        made = nil
        errset( made = axlDBCreateText( "MASK" list( 2.7 3.5 ) "10" "PACKAGE GEOMETRY/SOLDERMASK_TOP" nil ) )
        printf( "probe_masktext: created %L on PACKAGE GEOMETRY/SOLDERMASK_TOP\n" made )
        drain( poport )
        when( made
            foreach( tx car( made )
                printf( "  text %L bBox %L block %L\n" tx->text tx->bBox tx->textBlock )
            )
        )
        drain( poport )
        makeVariant3dIntermediates( out nil )
        t
    )
)
