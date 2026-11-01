;=====================================================================
;  probe_translit.il - DIAGNOSTIC ONLY. Reads nothing from the design.
;
;  The pure procedures the Python transliterations in
;  tests/skill_transliterations.py copy - five, since round 116
;  s3dCmdExpands, since round 118 the variant parser gdsysGetVariantInfo
;  on the files of tests/fixtures/variants, and since round 120 the names
;  the variants' files get and which of them share one (the last asks the
;  real file system, in build/probe-names, removed after), and since round
;  129 the launcher's paths and its check's reading of a log (simple3d.il,
;  which this loads from the same tree, and the logs of
;  tests/fixtures/preflight) - RUN in a real Allegro, by the
;  real interpreter, over a fixed list of cases, so that the copies can be
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
;  REQUIRES: makeVariant3dIntermediates.il, and simple3d.il, which it loads
;=====================================================================

; The file s3dVariantFilePath is pointed at while gdsysGetVariantInfo is
; asked about one (s3dProbeTranslitVariants).
S3D_ProbeVariantFile = nil

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

; The variant parser (round 118, R2-9 of the 23.10.2026 review), on every
; file in tests/fixtures/variants of the tree the exporter was loaded from.
; It reads the one file s3dVariantFilePath names, so that is pointed at each
; case in turn and put back after. The answer is the variant table: the
; variants in name order, each with its symbol list exactly as the parser
; leaves it - the stray tokens a caller filters out included.
procedure( s3dProbeTranslitVariants()
    let( ( dir res table answer )
        dir = strcat( s3dExporterFolderOf( S3D_ExporterLoadedFrom ) "/tests/fixtures/variants" )
        foreach( name sort( getDirFiles( dir ) 'alphalessp )
            when( rexMatchp( "\\.lst$" name )
                res = s3dProbeTranslitParseFile( strcat( dir "/" name ) )
                if( res == 'error then
                    answer = "error"
                else
                    table = car( res )
                    answer = foreach( mapcar key s3dProbeTranslitNames( table )
                                 list( key table[key] ) )
                )
                s3dProbeTranslitCase( "gdsysGetVariantInfo" name answer )
            )
        )
    )
)

; The parser's answer on one file, or 'error: s3dVariantFilePath, the one
; file it reads, pointed there and put back after.
procedure( s3dProbeTranslitParseFile( t_path )
    let( ( saved res ok )
        saved = getd( 's3dVariantFilePath )
        S3D_ProbeVariantFile = t_path
        putd( 's3dVariantFilePath lambda( ( ) S3D_ProbeVariantFile ) )
        res = nil
        ok = errset( res = gdsysGetVariantInfo() )
        putd( 's3dVariantFilePath saved )
        S3D_ProbeVariantFile = nil
        if( ok then res else 'error )
    )
)

; A variant table's names, in name order.
procedure( s3dProbeTranslitNames( o_table )
    let( ( names )
        names = nil
        foreach( key o_table  names = cons( key names ) )
        sort( names 'alphalessp )
    )
)

; Which variants would share a file (round 120), asked of the real file
; system in build/probe-names of the tree the exporter was loaded from, made
; here and removed after. The procedure makes a folder of its own inside it
; and removes that; what is left inside after every case is the last answer.
procedure( s3dProbeTranslitClashes()
    let( ( root dir res left )
        root = s3dExporterFolderOf( S3D_ExporterLoadedFrom )
        dir = strcat( root "/build/probe-names" )
        s3dMakeDirs( dir )
        foreach( c list( list( "Full FULL ALT" list( "Full" "FULL" "ALT" ) )
                         list( "full Full FULL" list( "full" "Full" "FULL" ) )
                         list( "A a b B" list( "A" "a" "b" "B" ) )
                         list( "Rev:A Rev_A" list( "Rev:A" "Rev_A" ) )
                         list( "Rev:A Rev:B" list( "Rev:A" "Rev:B" ) )
                         list( "a, a and a space" list( "a" "a " ) )
                         list( "x, x and a dot" list( "x" "x." ) ) )
            s3dProbeTranslitCase( "s3dVariantFileClashes" car( c )
                                  s3dVariantFileClashes( dir "brd" cadr( c ) ) )
        )
        ; the Cyrillic case twins of v21, as the parser hands them over: lowerCase
        ; leaves them as they are, and Windows does not
        res = s3dProbeTranslitParseFile( strcat( root "/tests/fixtures/variants/v21-cyrillic-case-twins.lst" ) )
        s3dProbeTranslitCase( "s3dVariantFileClashes" "the names of v21-cyrillic-case-twins.lst"
                              if( res == 'error then
                                  "error"
                              else
                                  s3dVariantFileClashes( dir "brd" s3dProbeTranslitNames( car( res ) ) ) ) )
        left = setof( f getDirFiles( dir ) !member( f list( "." ".." ) ) )
        s3dProbeTranslitCase( "s3dVariantFileClashes" "left behind" left )
        deleteDir( dir )
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
    let( ( saved pin padstack a b root dir res paths )

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
        ; round 128 (R1n-10): letters and digits only, the function and the
        ; name each on its own
        s3dProbeTranslitCase( "s3dLayerIsNegative" "name=SM_TOP function=SOLDER_MASK"
            s3dLayerIsNegative( s3dProbeTranslitLayer( "SM_TOP" "SOLDER_MASK" ) ) )
        s3dProbeTranslitCase( "s3dLayerIsNegative" "name=MASK_9 function=Solder Mask"
            s3dLayerIsNegative( s3dProbeTranslitLayer( "MASK_9" "Solder Mask" ) ) )
        s3dProbeTranslitCase( "s3dLayerIsNegative" "name=SOLDER-MASK_TOP"
            s3dLayerIsNegative( s3dProbeTranslitLayer( "SOLDER-MASK_TOP" nil ) ) )
        s3dProbeTranslitCase( "s3dLayerIsNegative" "name=LAY_TOP function=COVER"
            s3dLayerIsNegative( s3dProbeTranslitLayer( "LAY_TOP" "COVER" ) ) )
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
        ; round 128 (R1-4): a mirrored pin's offset flipped before the turn
        foreach( c list( list( "mirrored rot=0 off=(0.375 0.25)"   0.0   0.375 0.25 )
                         list( "mirrored rot=90 off=(0.375 0.25)"  90.0  0.375 0.25 )
                         list( "mirrored rot=180 off=(0.375 0.25)" 180.0 0.375 0.25 )
                         list( "mirrored rot=270 off=(0.375 0.25)" 270.0 0.375 0.25 ) )
            pin = ncons( nil )
            pin->xy = list( 2.19 0.375 )
            pin->rotation = cadr( c )
            pin->isMirrored = t
            padstack = ncons( nil )
            padstack->drillOffset = list( caddr( c ) cadddr( c ) )
            s3dProbeTranslitCase( "s3dDrillXY" car( c ) s3dDrillXY( pin padstack ) )
        )

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

        s3dProbeTranslitSay( "\n===== s3dCmdExpands =====" )
        ; What Windows' cmd would replace in a string (round 116). The
        ; environment is Allegro's own, so every name asked is one that holds,
        ; or does not, on any Windows: OS, windir and Path are there,
        ; NOPE_S3D is not.
        foreach( text list( "x %OS% y" "x %os% y" "x %Os% y" "x %NOPE_S3D% y"
                            "x %NOPE_S3D%OS% y" "x %OS:~0,3% y" "x %OS:Win=W% y"
                            "x %:OS% y" "x %NOPE_S3D:~1% y" "x %CD% y" "x %random% y"
                            "x %ERRORLEVEL% y" "x %=C:% y" "50% / 60%" "x % y" "x %% y"
                            "x %%OS%% y" "x !OS! y" "x %windir% y" "x %PATH% y" "%OS%"
                            "D:/Projects/AI/Claude/Simple3D" "" )
            s3dProbeTranslitCase( "s3dCmdExpands" strcat( "text=" text ) s3dCmdExpands( text ) )
        )
        s3dProbeTranslitCase( "s3dCmdExpands" "text=nil" s3dCmdExpands( nil ) )
        ; And how getShellEnvVar takes the case of a name, which s3dCmdDefined
        ; leans on: in any case, like cmd (measured 31.10.2026).
        foreach( nm list( "OS" "os" "Os" "windir" "WINDIR" "PATH" "Path" "path" )
            s3dProbeTranslitSay( sprintf( nil "ENV %s | %L" nm stringp( getShellEnvVar( nm ) ) ) )
        )

        s3dProbeTranslitSay( "\n===== parseString =====" )
        ; SKILL's own, with no break characters given: the variant parser's
        ; copy has to break a line where it does (round 118).
        foreach( c list( list( "space" "a b" ) list( "tab" "a\tb" ) list( "newline" "a\nb" )
                         list( "return" "a\rb" ) list( "runs" "  a   b  " ) list( "empty" "" ) )
            s3dProbeTranslitCase( "parseString" car( c ) parseString( cadr( c ) ) )
        )

        s3dProbeTranslitSay( "\n===== gdsysGetVariantInfo =====" )
        s3dProbeTranslitVariants()

        s3dProbeTranslitSay( "\n===== s3dFileNameSafe =====" )
        ; What a file name cannot carry becomes "_" (round 120). A control
        ; character gets into a string here only through an escape: \t, \b.
        foreach( c list( list( "plain" "Full" ) list( "a colon" "Rev:A" ) list( "a slash" "A/B" )
                         list( "a backslash" "A\\B" ) list( "the rest" "x*?\"<>|y" )
                         list( "a tab" "a\tb" ) list( "control 0x08" "a\bb" )
                         list( "kept" "BOM 100% #1 (v2) [x] {y} a.b ~!@$^&=+,;'`" )
                         list( "empty" "" ) )
            s3dProbeTranslitCase( "s3dFileNameSafe" car( c ) s3dFileNameSafe( cadr( c ) ) )
        )

        s3dProbeTranslitSay( "\n===== s3dVariantFileName =====" )
        foreach( c list( list( "Variants_Test-B0" "Full" ) list( "brd" "FULL" )
                         list( "brd" "Rev:A" ) list( "brd" "A b" ) )
            s3dProbeTranslitCase( "s3dVariantFileName"
                                  sprintf( nil "design=%s variant=%s" car( c ) cadr( c ) )
                                  s3dVariantFileName( car( c ) cadr( c ) ) )
        )

        s3dProbeTranslitSay( "\n===== s3dVariantFileClashes =====" )
        s3dProbeTranslitClashes()

        ; Round 129 (R2n-14, R2n-15, R2n-17, R2n-18 of the 28.10.2026 review):
        ; the launcher's paths and its check's reading of a log, and the
        ; exporter's own slashes and folder walk. The launcher's live in
        ; simple3d.il, loaded here from the tree the exporter came from -
        ; errset: its last lines put a menu item in, which a session with no
        ; window may refuse. The texts are tools/skill_answers.py's.
        root = s3dExporterFolderOf( S3D_ExporterLoadedFrom )
        s3dProbeTranslitSay( sprintf( nil "simple3d.il loaded: %L"
                                      errset( load( strcat( root "/simple3d.il" ) ) t ) ) )
        paths = list( "D:\\a\\b" "D:/a/b/" "D:\\a\\b\\" "D:\\" "D:/" "/" "\\\\server\\share\\x"
                      "//server/share/x" "//server/share/" "a\\\\b" "" "pcb" "D:/a/rev/pcb" "/pcb"
                      "D:/pcb" "//server" "\\\\server\\share\\rev\\pcb" )
        foreach( proc list( "s3dSlashes" "s3dLeafOf" "s3dFolderOf" "s3dExporterSlashes" )
            s3dProbeTranslitSay( sprintf( nil "\n===== %s =====" proc ) )
            foreach( p paths
                s3dProbeTranslitCase( proc sprintf( nil "text=%s" p )
                                      apply( stringToSymbol( proc ) list( p ) ) )
            )
            unless( proc == "s3dExporterSlashes"
                s3dProbeTranslitCase( proc "text=nil" apply( stringToSymbol( proc ) list( nil ) ) )
            )
        )

        s3dProbeTranslitSay( "\n===== s3dDirsToMake =====" )
        foreach( p list( "D:/a/b" "D:\\a\\b" "//server/share/a/b" "\\\\server\\share\\a" "a/b" "/a/b"
                         "D:\\a\\\\b" "//server/share" "D:" "" )
            s3dProbeTranslitCase( "s3dDirsToMake" sprintf( nil "text=%s" p ) s3dDirsToMake( p ) )
        )

        s3dProbeTranslitSay( "\n===== s3dLineText =====" )
        foreach( c list( list( "S3D_OK LF" "S3D_OK\n" ) list( "S3D_OK CRLF" "S3D_OK\r\n" )
                         list( "S3D_OK" "S3D_OK" ) list( "S3D_OK space LF" "S3D_OK \n" )
                         list( "LF" "\n" ) list( "empty" "" ) list( "a CR CR LF" "a\r\r\n" )
                         list( "nil" nil ) )
            s3dProbeTranslitCase( "s3dLineText" car( c ) s3dLineText( cadr( c ) ) )
        )

        s3dProbeTranslitSay( "\n===== s3dIsPathName =====" )
        foreach( p list( "pythonw" "pythonw.exe" "C:/Python314/pythonw.exe" "C:pythonw.exe"
                         "tools\\python" "" )
            s3dProbeTranslitCase( "s3dIsPathName" sprintf( nil "text=%s" p ) s3dIsPathName( p ) )
        )
        s3dProbeTranslitCase( "s3dIsPathName" "text=nil" s3dIsPathName( nil ) )

        s3dProbeTranslitSay( "\n===== s3dPreflightRead =====" )
        dir = strcat( root "/tests/fixtures/preflight" )
        foreach( name sort( getDirFiles( dir ) 'alphalessp )
            when( rexMatchp( "\\.log$" name )
                res = s3dPreflightRead( strcat( dir "/" name ) )
                s3dProbeTranslitCase( "s3dPreflightRead" name
                                      list( nth( 0 res ) nth( 1 res ) nth( 2 res ) ) )
            )
        )

        s3dProbeTranslitSay( "\n===== s3dPreflightDialog =====" )
        foreach( c list( 'missing 'python 'silent )
            s3dProbeTranslitCase( "s3dPreflightDialog" sprintf( nil "case=%L" c )
                                  s3dPreflightDialog( c "C:/x/pythonw.exe" ) )
        )

        s3dProbeTranslitSay( "\n===== END =====" )
        t
    )
)
