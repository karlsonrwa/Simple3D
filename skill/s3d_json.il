;=====================================================================
;  skill/s3d_json.il - s3dJsonQuote, the JSON reader, the config pair (shipped + local)
;
;  Part 2 of 9 of the Simple 3D exporter, cut from
;  makeVariant3dIntermediates.il in round 76 (plan D6) with every procedure
;  and comment as it was; that file loads the parts in order. Load it, or
;  simple3d.il, never a part on its own.
;=====================================================================


; A string, escaped and quoted for JSON.
;
; Layer, stackup and zone names go into the intermediate verbatim, and a single
; quote or backslash in any of them would break the whole file - not one entry,
; the whole export. Unlikely in a layer name, but a broken intermediate is a
; total failure while escaping costs one pass over a short string.
; A control character OTHER than tab, newline and carriage return - those three
; have escapes of their own below and must not trip this. Used only to ask a
; WHOLE string whether it needs the slow path - see s3dJsonQuote.
;
; COMPILED ON FIRST USE, not at load. This file is loaded from allegro.ilinit
; while the editor is starting, and after a batch that added load-time work
; Allegro began crashing on startup (2026-08-04). Which statement did it was
; never established, so the rule taken from it is the blunt one: loading these
; files does nothing but define procedures. `unset` rather than nil marks "not
; tried yet", so a pattern this Allegro will not take is attempted once and
; then left alone - and the quoting simply falls back to what it did before.
S3D_CtrlChars = 'unset

procedure( s3dCtrlCharPattern()
    when( S3D_CtrlChars == 'unset
        S3D_CtrlChars = nil
        errset( S3D_CtrlChars = pcreCompile( "[\\x01-\\x08\\x0b\\x0c\\x0e-\\x1f]" ) )
    )
    S3D_CtrlChars
)

procedure( s3dJsonQuote( g_value )
    let( ( out c ( scan nil ) pattern )
        if( stringp( g_value ) then
            ; JSON forbids a raw control character inside a string, and ONE of
            ; them anywhere - a stray CR pasted into a layer or symbol name -
            ; makes the WHOLE intermediate unparsable, with an error that names
            ; JSON rather than the name that carries it. The three that have a
            ; spelling of their own are escaped; anything else below 0x20 is
            ; replaced by a space, because SKILL has no verified way here to
            ; turn a character into its code and \u00XX cannot be built without
            ; one. Corrupt data either way - but the file still parses and the
            ; console says which string it was.
            ;
            ; Asked once per STRING, not once per character: the per-character
            ; test would run on every ordinary character of every name on the
            ; board, and this is called thousands of times on a dense legend.
            pattern = s3dCtrlCharPattern()
            when( pattern
                scan = pcreMatchp( pattern g_value )
            )
            when( scan
                s3dWarn( sprintf( nil
                    "Simple 3D: a control character in %s was replaced by a space (the string comes from the design and would break the JSON)."
                    g_value ) )
            )
            out = "\""
            for( i 1 strlen( g_value )
                c = substring( g_value i 1 )
                out = strcat( out
                    cond(
                        ( c == "\""  "\\\"" )
                        ( c == "\\"  "\\\\" )
                        ( c == "\t"  "\\t" )
                        ( c == "\n"  "\\n" )
                        ( c == "\r"  "\\r" )
                        ( scan && pcreMatchp( pattern c )  " " )
                        ( t          c )
                    ) )
            )
            strcat( out "\"" )
        else
            "null"
        )
    )
)

;---------------------------------------------------------------------
;  A small JSON reader, so the layer list lives in an editable file
;  instead of in the source (same idea as exportJson's config.json).
;
;  Purely functional: every parse step returns  list( value nextIndex )  and
;  nothing is mutated, which avoids needing a by-reference cursor. Handles the
;  JSON subset a config file needs: objects, arrays, strings (with escapes),
;  numbers, true/false/null. \uXXXX is consumed but not decoded (a layer name
;  is ASCII).
;
;  Parsed shape:  object -> ( 'jobj ((key value) ...) )
;                 array  -> ( 'jarr (value ...) )
;---------------------------------------------------------------------

; Characters a JSON number may be built from. A list + member() rather than a
; string + index(): member on strings is used elsewhere in this toolchain and
; is known to work here, whereas index() is a core-SKILL string function that
; the Allegro API reference does not carry - not worth betting the config
; reader on.
S3D_JsonNumChars = list( "0" "1" "2" "3" "4" "5" "6" "7" "8" "9"
                         "+" "-" "." "e" "E" )

procedure( s3dJsonSlurp( t_file )
    let( ( port line out )
        out = ""
        port = infile( t_file )
        when( port
            while( gets( line port )
                out = strcat( out line )
            )
            close( port )
            out
        )
    )
)

; Skip whitespace, return the new index.
procedure( s3dJsonWs( t_txt x_i )
    let( ( n c ( go t ) )
        n = strlen( t_txt )
        while( go && (x_i <= n)
            c = substring( t_txt x_i 1 )
            if( (c == " ") || (c == "\t") || (c == "\n") || (c == "\r") then
                x_i = x_i + 1
            else
                go = nil
            )
        )
        x_i
    )
)

; x_i points at the opening quote. -> list( t_string nextIndex )
procedure( s3dJsonStr( t_txt x_i )
    let( ( n c out ( go t ) )
        n = strlen( t_txt )
        out = ""
        x_i = x_i + 1
        while( go && (x_i <= n)
            c = substring( t_txt x_i 1 )
            cond(
                ( c == "\""
                    x_i = x_i + 1
                    go = nil
                )
                ( c == "\\"
                    x_i = x_i + 1
                    c = if( x_i <= n then substring( t_txt x_i 1 ) else "" )
                    cond(
                        ( c == "n"  out = strcat( out "\n" ) )
                        ( c == "t"  out = strcat( out "\t" ) )
                        ( c == "r"  out = strcat( out "\r" ) )
                        ( c == "b"  t )
                        ( c == "f"  t )
                        ( c == "u"  x_i = x_i + 4 )
                        ( t         out = strcat( out c ) )
                    )
                    x_i = x_i + 1
                )
                ( t
                    out = strcat( out c )
                    x_i = x_i + 1
                )
            )
        )
        list( out x_i )
    )
)

; -> list( f_number nextIndex )
procedure( s3dJsonNum( t_txt x_i )
    let( ( n c start ( go t ) )
        n = strlen( t_txt )
        start = x_i
        while( go && (x_i <= n)
            c = substring( t_txt x_i 1 )
            if( member( c S3D_JsonNumChars ) then
                x_i = x_i + 1
            else
                go = nil
            )
        )
        if( x_i > start then
            list( atof( substring( t_txt start x_i - start ) ) x_i )
        else
            ; not a number at all - step over the offending character so the
            ; caller cannot spin forever on malformed input.
            list( nil x_i + 1 )
        )
    )
)

; -> list( value nextIndex )
procedure( s3dJsonVal( t_txt x_i )
    let( ( c n )
        n = strlen( t_txt )
        x_i = s3dJsonWs( t_txt x_i )
        c = if( x_i <= n then substring( t_txt x_i 1 ) else "" )
        cond(
            ( c == "{"   s3dJsonObj( t_txt x_i ) )
            ( c == "["   s3dJsonArr( t_txt x_i ) )
            ( c == "\""  s3dJsonStr( t_txt x_i ) )
            ( (x_i + 3 <= n) && (substring( t_txt x_i 4 ) == "true")   list( t x_i + 4 ) )
            ( (x_i + 4 <= n) && (substring( t_txt x_i 5 ) == "false")  list( nil x_i + 5 ) )
            ( (x_i + 3 <= n) && (substring( t_txt x_i 4 ) == "null")   list( nil x_i + 4 ) )
            ( t  s3dJsonNum( t_txt x_i ) )
        )
    )
)

; x_i points at "{". -> list( ( 'jobj alist ) nextIndex )
procedure( s3dJsonObj( t_txt x_i )
    let( ( n c key res out ( go t ) )
        n = strlen( t_txt )
        x_i = x_i + 1
        out = nil
        while( go
            x_i = s3dJsonWs( t_txt x_i )
            c = if( x_i <= n then substring( t_txt x_i 1 ) else "" )
            cond(
                ( c == "}"  x_i = x_i + 1  go = nil )
                ( c == ","  x_i = x_i + 1 )
                ( c == "\""
                    res = s3dJsonStr( t_txt x_i )
                    key = car( res )
                    x_i = s3dJsonWs( t_txt cadr( res ) )
                    when( (x_i <= n) && (substring( t_txt x_i 1 ) == ":")
                        x_i = x_i + 1
                    )
                    res = s3dJsonVal( t_txt x_i )
                    x_i = cadr( res )
                    out = cons( list( key car( res ) ) out )
                )
                ( t  go = nil )        ; malformed or end of input
            )
        )
        list( list( 'jobj reverse( out ) ) x_i )
    )
)

; x_i points at "[". -> list( ( 'jarr elements ) nextIndex )
procedure( s3dJsonArr( t_txt x_i )
    let( ( n c res out ( go t ) )
        n = strlen( t_txt )
        x_i = x_i + 1
        out = nil
        while( go
            x_i = s3dJsonWs( t_txt x_i )
            c = if( x_i <= n then substring( t_txt x_i 1 ) else "" )
            cond(
                ( c == "]"  x_i = x_i + 1  go = nil )
                ( c == ","  x_i = x_i + 1 )
                ( c == ""   go = nil )
                ( t
                    res = s3dJsonVal( t_txt x_i )
                    x_i = cadr( res )
                    out = cons( car( res ) out )
                )
            )
        )
        list( list( 'jarr reverse( out ) ) x_i )
    )
)

procedure( s3dJsonRead( t_file )
    let( ( txt res )
        txt = s3dJsonSlurp( t_file )
        when( txt
            res = nil
            errset( res = s3dJsonVal( txt 1 ) )
            when( res  car( res ) )
        )
    )
)

; Value of t_key in a parsed object, or nil. Own lookup rather than assoc: the
; comparison must be a plain string compare, whatever assoc happens to use.
procedure( s3dJsonGet( g_node t_key )
    let( ( out )
        when( g_node && listp( g_node ) && (car( g_node ) == 'jobj)
            foreach( pair cadr( g_node )
                when( car( pair ) == t_key  out = cadr( pair ) )
            )
        )
        out
    )
)

; t if the key is present, regardless of its value. Needed to tell a JSON
; false/null apart from a missing key, since both parse to nil.
procedure( s3dJsonHas( g_node t_key )
    let( ( out )
        when( g_node && listp( g_node ) && (car( g_node ) == 'jobj)
            foreach( pair cadr( g_node )
                when( car( pair ) == t_key  out = t )
            )
        )
        out
    )
)

; The elements of an array value, as a plain SKILL list.
procedure( s3dJsonList( g_node t_key )
    let( ( val )
        val = s3dJsonGet( g_node t_key )
        when( val && listp( val ) && (car( val ) == 'jarr)
            cadr( val )
        )
    )
)

;---------------------------------------------------------------------
;  The settings file, and the local one on top of it
;
;  simple3d_config.json is under version control and holds the SHIPPED
;  DEFAULTS. simple3d_config.local.json sits beside it, is gitignored, and
;  holds whatever this installation does differently - the model folders, and
;  anything else someone wants to pin. The two are merged on read, local
;  winning key by key, so:
;
;    * pulling an update never touches your file and never conflicts;
;    * an improved layer list or a new default DOES reach you, because the
;      base file is still the one being updated;
;    * your absolute paths never enter a commit.
;
;  The window writes ONLY the local file. Nothing writes the base one.
;---------------------------------------------------------------------

; t if this is a parsed JSON object.
procedure( s3dJsonIsObj( g_node )
    listp( g_node ) && (car( g_node ) == 'jobj)
)

; The entry for a key in a parsed object's alist, or nil.
;
; Written out rather than using assoc: this file already learned that SKILL's
; member compares with eq, which two equal strings are not, and betting the
; settings on assoc's comparison being the other one is not worth the line it
; would save. `==` on strings compares contents.
procedure( s3dJsonEntry( t_key l_alist )
    let( ( ( hit nil ) )
        foreach( entry l_alist
            when( listp( entry ) && stringp( car( entry ) ) &&
                  (car( entry ) == t_key) && !hit
                hit = entry
            )
        )
        hit
    )
)

; base with over laid on top of it. Objects are merged key by key; anything
; else is REPLACED whole - a list or a number in the local file wins entirely,
; which is the only reading that lets it turn something off or shorten a list.
;
; PRESENCE in the alist decides, never truthiness. JSON false parses to nil
; here, so a test like `when( value ... )` would silently drop exactly the
; overrides that switch a setting off.
procedure( s3dJsonMerge( g_base g_over )
    prog( ( out entry hit )
        unless( s3dJsonIsObj( g_over ) && s3dJsonIsObj( g_base )
            return( g_over )
        )
        out = nil
        foreach( entry cadr( g_base )
            hit = s3dJsonEntry( car( entry ) cadr( g_over ) )
            if( hit then
                out = cons( list( car( entry )
                                  s3dJsonMerge( cadr( entry ) cadr( hit ) ) ) out )
            else
                out = cons( entry out )
            )
        )
        foreach( entry cadr( g_over )
            unless( s3dJsonEntry( car( entry ) cadr( g_base ) )
                out = cons( entry out )
            )
        )
        return( list( 'jobj reverse( out ) ) )
    )
)

; "…/simple3d_config.json" -> "…/simple3d_config.local.json"
procedure( s3dLocalConfigFile( t_file )
    let( ( n )
        n = strlen( t_file )
        if( (n > 5) && (lowerCase( substring( t_file n - 4 5 ) ) == ".json") then
            strcat( substring( t_file 1 n - 5 ) ".local.json" )
        else
            strcat( t_file ".local" )
        )
    )
)

; The settings as both halves of the tool see them: the tracked defaults with
; the local file merged over them. Either may be missing; a local file that
; will not parse is reported and ignored, because ignoring it leaves a working
; tool while failing on it would leave none.
procedure( s3dConfigRead( t_file )
    let( ( base localFile local )
        base = nil
        when( t_file && isFile( t_file )
            errset( base = s3dJsonRead( t_file ) )
        )
        localFile = if( t_file then s3dLocalConfigFile( t_file ) else nil )
        local = nil
        when( localFile && isFile( localFile )
            errset( local = s3dJsonRead( localFile ) )
            if( s3dJsonIsObj( local ) then
                printf( "Simple 3D: local settings on top: %s\n" localFile )
            else
                s3dWarn( sprintf( nil "Simple 3D: %s could not be parsed and was ignored."
                                  localFile ) )
            )
        )
        if( s3dJsonIsObj( local ) then s3dJsonMerge( base local ) else base )
    )
)
