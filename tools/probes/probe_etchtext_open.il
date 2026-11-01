;=====================================================================
;  probe_etchtext_open.il - DIAGNOSTIC. Changes the COPY of the board it
;  runs on (the runner's scratch copy, never the original) and does not
;  save it.
;
;  Round 126 (R4-4 of the 23.10.2026 review): is copper written as TEXT on
;  an ETCH layer seen under a drawn mask opening? The copper sweep's find
;  filter had lines, clines, shapes, pins and vias, no text. No board in
;  input/ has such a case, so it is made, twice: an opening drawn on
;  PACKAGE GEOMETRY/SOLDERMASK_TOP and the board exported into
;  <out>/no_text, then a text on ETCH/TOP inside that opening and the board
;  exported again into <out>/with_text. Whatever copper the area had
;  before is in both; the text's strokes are the difference - in
;  pads.exposed.top when the sweep sees text, nowhere when it does not.
;  <out> is the environment variable S3D_PROBE_OUT (else the design's
;  folder). probe_masktext.il is the other way round: text ON THE MASK,
;  which makes an opening, not copper.
;
;  REQUIRES: makeVariant3dIntermediates.il
;  Usage:  load("<path>/probe_etchtext_open.il")   then   s3dProbeEtchTextOpen()
;=====================================================================

procedure( s3dProbeEtchTextOpen()
    let( ( out before after made text )
        out = nil
        errset( out = getShellEnvVar( "S3D_PROBE_OUT" ) )
        unless( stringp( out ) && (out != "")  out = s3dDesignFolder() )
        before = strcat( out "/no_text" )
        after = strcat( out "/with_text" )
        s3dMakeDirs( before )
        s3dMakeDirs( after )
        ; my_test_board2 (29.5 x 23 mm): a 6 x 4 mm opening at 20..26 x 9..13,
        ; away from the board's own label on the mask at y 18..21.
        made = nil
        errset( made = axlDBCreateRectangle( list( 20.0:9.0 26.0:13.0 ) t
                                             "PACKAGE GEOMETRY/SOLDERMASK_TOP" ) )
        printf( "probe_etchtext_open: opening %L\n" made )
        drain( poport )
        makeVariant3dIntermediates( before nil )
        text = nil
        errset( text = axlDBCreateText( "CU" list( 21.0 10.0 ) "10" "ETCH/TOP" nil ) )
        printf( "probe_etchtext_open: text %L\n" text )
        when( text
            foreach( tx car( text )
                printf( "  text %L layer %L bBox %L\n" tx->text tx->layer tx->bBox )
            )
        )
        drain( poport )
        makeVariant3dIntermediates( after nil )
        printf( "probe_etchtext_open: END\n" )
        t
    )
)
