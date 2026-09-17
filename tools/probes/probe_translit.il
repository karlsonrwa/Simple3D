;=====================================================================
;  probe_translit.il - DIAGNOSTIC ONLY. Reads nothing from the design.
;
;  The five pure procedures the Python transliterations in
;  tests/skill_transliterations.py copy, RUN - in a real Allegro, by the
;  real interpreter - over a fixed list of cases, so that the copies can be
;  compared against the original's own answers instead of against a reading
;  of its source.
;
;  Why it exists: half the product is SKILL and no test runs it, so four of
;  five semantic mutations made in skill/ passed the whole suite unnoticed
;  (docs/test-audit.md, 2026-09-15, finding 3). tests/test_skill_pins.py
;  closes that by reading the source; this closes it by execution, once,
;  and its output becomes tests/fixtures/skill_answers.json.
;
;  Nothing here touches the design: the board on the command line is only
;  what gives Allegro a session to interpret in.
;
;  Every line of the answer is machine-readable:
;      CASE <procedure> | <case name> | <answer>
;  with the answer printed with %L, so nil and t come out as themselves.
;
;    python tools/run_probe.py --with-exporter tools/probes/probe_translit.il \
;           s3dProbeTranslit input/Cadence_Demo.brd
;  REQUIRES: makeVariant3dIntermediates.il
;=====================================================================

procedure( s3dProbeTranslitSay( t_line )
    printf( "%s\n" t_line )
    drain( poport )
)

; One answer, in the one form the reader parses.
procedure( s3dProbeTranslitCase( t_proc t_case g_answer )
    s3dProbeTranslitSay( sprintf( nil "CASE %s | %s | %L" t_proc t_case g_answer ) )
)

; JSON from a string. The exporter parses files (s3dJsonRead) and there is no
; entry point for text, so the value parser is called directly, exactly as
; s3dJsonRead calls it: ( value nextIndex ), the value is the car.
procedure( s3dProbeTranslitParse( t_text )
    let( ( res )
        res = nil
        errset( res = s3dJsonVal( t_text 1 ) )
        when( res  car( res ) )
    )
)

; A disembodied property list standing in for a layer: ->name, ->layerFunction.
procedure( s3dProbeTranslitLayer( t_name t_func )
    let( ( o )
        o = ncons( nil )
        o->name = t_name
        o->layerFunction = t_func
        o
    )
)


procedure( s3dProbeTranslit()
    let( ( saved pin padstack a b )

        s3dProbeTranslitSay( "\n===== s3dLayerIsNegative =====" )
        ; The list the procedure reads is a global; put back what was there.
        saved = S3D_NegativeLayers
        S3D_NegativeLayers = list( "COVERLAY" "SOLDERMASK" "PASTEMASK" )
        foreach( nm list( "COVERLAY_TOP" "COVERLAY_BOTTOM" "SOLDERMASK_TOP"
                          "SOLDERMASK_BOTTOM" "PASTEMASK_TOP" "STIFFENER_TOP"
                          "STIFFENER_TOP2" "ADHESIVE_TOP" "ADHESIVE_TOP2"
                          "ADHESIVE_BOTTOM" "TOP" "BOTTOM" )
            s3dProbeTranslitCase( "s3dLayerIsNegative" sprintf( nil "name=%s" nm )
                s3dLayerIsNegative( s3dProbeTranslitLayer( nm nil ) ) )
        )
        s3dProbeTranslitCase( "s3dLayerIsNegative" "name=MASK_7 function=Coverlay"
            s3dLayerIsNegative( s3dProbeTranslitLayer( "MASK_7" "Coverlay" ) ) )
        s3dProbeTranslitCase( "s3dLayerIsNegative" "name=nil function=nil"
            s3dLayerIsNegative( s3dProbeTranslitLayer( nil nil ) ) )
        S3D_NegativeLayers = list( "EPOXY" )
        s3dProbeTranslitCase( "s3dLayerIsNegative" "keys=(EPOXY) name=EPOXY_TOP"
            s3dLayerIsNegative( s3dProbeTranslitLayer( "EPOXY_TOP" nil ) ) )
        s3dProbeTranslitCase( "s3dLayerIsNegative" "keys=(EPOXY) name=COVERLAY_TOP"
            s3dLayerIsNegative( s3dProbeTranslitLayer( "COVERLAY_TOP" nil ) ) )
        S3D_NegativeLayers = nil
        s3dProbeTranslitCase( "s3dLayerIsNegative" "keys=() name=COVERLAY_TOP"
            s3dLayerIsNegative( s3dProbeTranslitLayer( "COVERLAY_TOP" nil ) ) )
        S3D_NegativeLayers = saved

        s3dProbeTranslitSay( "\n===== s3dDrillXY =====" )
        ; pin->xy, pin->rotation; padstack->drillOffset - the three fields the
        ; procedure reads, and nothing else.
        foreach( c list( list( "rot=0 off=(0.375 0)"   0.0   0.375 0.0 )
                         list( "rot=90 off=(0.375 0)"  90.0  0.375 0.0 )
                         list( "rot=180 off=(0.375 0)" 180.0 0.375 0.0 )
                         list( "rot=270 off=(0.375 0)" 270.0 0.375 0.0 )
                         list( "rot=90 off=(0 0.25)"   90.0  0.0   0.25 )
                         list( "rot=45 off=(0.5 0.5)"  45.0  0.5   0.5 ) )
            pin = ncons( nil )
            pin->xy = list( 2.19 0.375 )
            pin->rotation = cadr( c )
            padstack = ncons( nil )
            padstack->drillOffset = list( caddr( c ) cadddr( c ) )
            s3dProbeTranslitCase( "s3dDrillXY" car( c ) s3dDrillXY( pin padstack ) )
        )
        ; ...and the shortcut: no offset at all means the pad, untouched.
        pin = ncons( nil )
        pin->xy = list( 2.19 0.375 )
        pin->rotation = 90.0
        padstack = ncons( nil )
        padstack->drillOffset = nil
        s3dProbeTranslitCase( "s3dDrillXY" "rot=90 off=nil" s3dDrillXY( pin padstack ) )
        padstack->drillOffset = list( 0.0 0.0 )
        s3dProbeTranslitCase( "s3dDrillXY" "rot=270 off=(0 0)" s3dDrillXY( pin padstack ) )
        pin->rotation = nil
        padstack->drillOffset = list( 0.375 0.0 )
        s3dProbeTranslitCase( "s3dDrillXY" "rot=nil off=(0.375 0)" s3dDrillXY( pin padstack ) )

        s3dProbeTranslitSay( "\n===== s3dBoxesMeet =====" )
        foreach( c list(
                list( "apart in x and y"   list( list( 0 0 ) list( 1 1 ) ) list( list( 2 2 ) list( 3 3 ) ) )
                list( "apart in x only"    list( list( 0 0 ) list( 1 1 ) ) list( list( 2 0 ) list( 3 1 ) ) )
                list( "apart in y only"    list( list( 0 0 ) list( 1 1 ) ) list( list( 0 2 ) list( 1 3 ) ) )
                list( "touching at a corner" list( list( 0 0 ) list( 1 1 ) ) list( list( 1 1 ) list( 2 2 ) ) )
                list( "overlapping"        list( list( 0 0 ) list( 2 2 ) ) list( list( 1 1 ) list( 3 3 ) ) )
                list( "one inside the other" list( list( 0 0 ) list( 4 4 ) ) list( list( 1 1 ) list( 2 2 ) ) )
                list( "no box on the left" nil list( list( 1 1 ) list( 2 2 ) ) ) )
            a = cadr( c )
            b = caddr( c )
            s3dProbeTranslitCase( "s3dBoxesMeet" car( c ) s3dBoxesMeet( a b ) )
            s3dProbeTranslitCase( "s3dBoxesMeet" strcat( car( c ) " reversed" )
                                  s3dBoxesMeet( b a ) )
        )

        s3dProbeTranslitSay( "\n===== s3dJsonQuote =====" )
        ; A control character cannot be written as a literal here, so the ones
        ; that have no spelling of their own are built with sprintf %c.
        foreach( c list( list( "plain"        "abc" )
                         list( "a quote"      "a\"b" )
                         list( "a backslash"  "a\\b" )
                         list( "a tab"        "a\tb" )
                         list( "a newline"    "a\nb" )
                         list( "a return"     "a\rb" )
                         list( "not a string" 7 ) )
            s3dProbeTranslitCase( "s3dJsonQuote" car( c ) s3dJsonQuote( cadr( c ) ) )
        )
        ; A control character other than tab/newline/return has to be got into
        ; a SKILL string somehow, and sprintf "%c" is not available here. Three
        ; ways are tried and whichever works carries the case; the answer says
        ; which, so a reader knows what was actually exercised.
        foreach( c list( list( "control 0x08 (escape \\b)"  "a\bb" )
                         list( "control 0x0c (escape \\f)"  "a\fb" ) )
            s3dProbeTranslitCase( "s3dJsonQuote" car( c ) s3dJsonQuote( cadr( c ) ) )
            s3dProbeTranslitCase( "s3dJsonQuote" strcat( car( c ) " byte" )
                                  strlen( cadr( c ) ) )
        )
        foreach( n list( 1 8 11 12 14 31 )
            let( ( s )
                s = nil
                errset( s = strcat( "a" sprintf( nil "%c" n ) "b" ) )
                if( s then
                    s3dProbeTranslitCase( "s3dJsonQuote"
                        sprintf( nil "control 0x%02x" n ) s3dJsonQuote( s ) )
                else
                    s3dProbeTranslitSay( sprintf( nil
                        "SKIP s3dJsonQuote | control 0x%02x | sprintf %%c is not available here" n ) )
                )
            )
        )

        s3dProbeTranslitSay( "\n===== s3dJsonMerge =====" )
        ; Parsed from text, merged, and read back key by key - so the answer
        ; is what the merge DID, not how it is stored. A JSON false and a
        ; missing key both read back nil, so s3dJsonHas is printed beside
        ; s3dJsonGet: together they say which of the two it is.
        let( ( base over merged silk )
            base = s3dProbeTranslitParse(
                "{ \"silk\": { \"top\": true, \"bottom\": true, \"flat\": false }, \"pads\": true }" )
            over = s3dProbeTranslitParse( "{ \"silk\": { \"flat\": true } }" )
            merged = s3dJsonMerge( base over )
            silk = s3dJsonGet( merged "silk" )
            foreach( key list( "top" "bottom" "flat" )
                s3dProbeTranslitCase( "s3dJsonMerge" strcat( "silk." key )
                    s3dJsonGet( silk key ) )
                s3dProbeTranslitCase( "s3dJsonMerge" strcat( "silk." key " present" )
                    s3dJsonHas( silk key ) )
            )
            s3dProbeTranslitCase( "s3dJsonMerge" "pads" s3dJsonGet( merged "pads" ) )

            base = s3dProbeTranslitParse( "{ \"a\": { \"b\": 1 } }" )
            over = s3dProbeTranslitParse( "{ \"a\": 2 }" )
            s3dProbeTranslitCase( "s3dJsonMerge" "a scalar over an object"
                s3dJsonGet( s3dJsonMerge( base over ) "a" ) )

            base = s3dProbeTranslitParse( "{ \"a\": 1 }" )
            over = s3dProbeTranslitParse( "{ \"b\": 2 }" )
            merged = s3dJsonMerge( base over )
            s3dProbeTranslitCase( "s3dJsonMerge" "a key only the base has"
                s3dJsonGet( merged "a" ) )
            s3dProbeTranslitCase( "s3dJsonMerge" "a key only the override has"
                s3dJsonGet( merged "b" ) )
        )

        s3dProbeTranslitSay( "\n===== END =====" )
        t
    )
)
