;=====================================================================
;  skill/s3d_util.il - console messages, folders beside the board, indentation, the subclass sweep
;
;  Part 1 of 9 of the Simple 3D exporter, cut from
;  makeVariant3dIntermediates.il in round 76 (plan D6) with every procedure
;  and comment as it was; that file loads the parts in order. Load it, or
;  simple3d.il, never a part on its own.
;=====================================================================

;=====================================================================
;  CONSOLE MESSAGES
;
;  axlUIWPrint carries a severity, and the Allegro console colors by it:
;  warnings in its warning color, errors in red, both with the *WARNING* /
;  *Error* prefix Allegro puts on its own messages. So these lines do NOT
;  spell the severity out themselves - Allegro says it, and saying it twice
;  reads as a mistake.
;
;  The documented levels are 'info0, 'info1, 'warn, 'error and 'fatal. There is
;  no "success" level, so a green completion line cannot be had this way; the
;  GUI log does color its own success line green, and that is where the result
;  is judged. 'fatal is deliberately unused - it beeps and its behaviour beyond
;  that is not documented here.
;
;  The message is passed as a %s ARGUMENT rather than as the format string: a
;  layer name or a path containing a per-cent sign would otherwise be read as a
;  conversion and either print wrongly or fault.
;
;  Falls back to printf when axlUIWPrint is unavailable or refuses the call, so
;  no message is ever lost to the attempt at coloring it.
;=====================================================================

procedure( s3dSay( s_level t_message )
    let( ( ok )
        ok = nil
        errset( ok = axlUIWPrint( nil s_level "%s" t_message ) )
        unless( ok
            printf( "%s\n" t_message )
        )
    )
)

procedure( s3dWarn( t_message )
    s3dSay( 'warn t_message )
)

procedure( s3dErr( t_message )
    s3dSay( 'error t_message )
)

; s3dMakeDirs( t_path ) -> create every missing level of a directory path.
; createDir makes only one level at a time; a path like ".../A1/cad" where an
; intermediate level is missing needs each segment created in turn.
; LIMITATION: UNC paths (//server/share/...) are not handled - parseString
; collapses the leading slashes, so the first segment would be created as a
; relative folder. Local drive paths (d:/...) only.
procedure( s3dMakeDirs( t_path )
    let( ( norm parts acc seg )
        ; normalise slashes; parseString drops empty tokens so "d:/a//b" is safe
        norm = buildString( parseString( t_path "\\" ) "/" )
        parts = parseString( norm "/" )
        acc = ""
        foreach( seg parts
            acc = if( acc == "" then seg else strcat( acc "/" seg ) )
            ; skip the bare drive letter "d:" (creating it is meaningless).
            ; A drive token is exactly 2 chars ending in ":".
            unless( (strlen( acc ) == 2) && (substring( acc 2 1 ) == ":")
                unless( isDir( acc )
                    errset( createDir( acc ) )
                )
            )
        )
        isDir( t_path )
    )
)

; s3dDesignFolder() -> the folder holding the open .brd, "" if it cannot be read.
;
; Why this exists: Variants.lst lives BESIDE THE BOARD, always. It used to be
; opened by its bare name, which resolves against Allegro's WORKING directory
; instead - and when the two differ, the file next to the board is invisible,
; the export quietly takes its no-variant path and writes one JSON with every
; component in it. Nothing about that says "your variants were not read".
;
; axlCurrentDesign returns the NAME only ("flex2-a0"); the full path of the
; drawing, extension and all, is axlGetDrawingName. The folder is everything
; before the last separator, found by SCANNING rather than with parseString,
; because parseString collapses the leading slashes of a UNC path
; (//server/share/...) and would hand back a relative folder - the limitation
; s3dMakeDirs above still carries.
procedure( s3dDesignFolder()
    prog( ( full n i cut ch )
        full = nil
        errset( full = axlGetDrawingName() )
        unless( stringp( full )  return( "" ) )
        n = strlen( full )
        cut = 0
        for( i 1 n
            ch = substring( full i 1 )
            when( (ch == "/") || (ch == "\\")  cut = i )
        )
        ; no separator at all: a bare filename, so there is no folder to give
        when( cut == 0  return( "" ) )
        return( if( cut == 1 then "/" else substring( full 1 cut - 1 ) ) )
    )
)

; s3dVariantFilePath() -> where Variants.lst is: beside the board.
;
; Falls back to the bare name - the working directory, which is where this
; looked before - when the drawing path cannot be read, so an Allegro that does
; not answer axlGetDrawingName is no worse off than it was.
procedure( s3dVariantFilePath()
    let( ( dir last )
        dir = s3dDesignFolder()
        last = if( dir == "" then "" else substring( dir strlen( dir ) 1 ) )
        cond(
            ( dir == ""                        "Variants.lst" )
            ; a folder that already ends in a separator - the root, "/" - must
            ; not get a second one
            ( (last == "/") || (last == "\\")  strcat( dir "Variants.lst" ) )
            ( t                                strcat( dir "/Variants.lst" ) )
        )
    )
)

; s3dAddIndent( t_string [ x_levels ] ) -> prefix every line with x_levels tabs.
; Reconstructed from the call sites; output matches the reference demo.json
; byte-for-byte. (The original repo used this but never shipped its source.)
;
; PREFIXED as of 2026-08-04, and this one matters more than most: the upstream
; script CALLS addIndent without defining it, so the name belongs to something
; else on the machine that runs it. Ours is a reconstruction - if the real one
; is loaded after this file, the JSON's indentation silently becomes whatever
; that version does, and if its arity differs the export dies mid-write.
procedure( s3dAddIndent( t_string @optional ( x_levels 1 ) )
    let( ( pad lines i )
        pad = ""
        for( i 1 x_levels
            pad = strcat( pad "\t" )
        )
        cond(
            ( !t_string           nil )
            ( !stringp( t_string ) t_string )
            ( t
                lines = parseString( t_string "\n" )
                if( lines then
                    buildString( mapcar( lambda( (line) strcat( pad line ) ) lines ) "\n" )
                else
                    strcat( pad t_string )
                )
            )
        )
    )
)

; t if t_hay contains t_needle.
procedure( s3dContains( t_hay t_needle )
    let( ( ( n 0 ) ( found nil ) )
        n = strlen( t_needle )
        when( n > 0
            for( i 1 strlen( t_hay ) - n + 1
                when( substring( t_hay i n ) == t_needle  found = t )
            )
        )
        found
    )
)
; Everything on the given subclasses, selected with the design otherwise
; hidden - the one sweep the exporter and the probes share (round 76, D3;
; until then five copies of it).
;
; The visibility and find-filter state is snapshotted and restored, per the
; programming model in the axlVisibleDesign documentation. Without that the
; user is left staring at a blank board after an export. Restored BEFORE the
; caller does anything with the result, so a slow or failing conversion
; afterwards cannot strand the session with a hidden design.
;
; A layer that does not exist is reported through s3dWarn with t_missingFmt
; (one %s, the layer) and the sweep goes on with the others.
;
; axlGetFindFilter reports DYNTHEMALS among the on-buttons but refuses to
; take it back ("Options are ignored for onButtons"), so handing its own
; answer straight back produced a warning on every export (round 14). It is
; dropped from what is restored.
procedure( s3dSelectVisibleOn( l_layers l_filter t_missingFmt )
    let( ( saveVis saveEnabled saveOn elems )
        saveVis     = axlVisibleGet()
        saveEnabled = axlGetFindFilter( t )
        saveOn      = axlGetFindFilter( nil )

        axlVisibleDesign( nil )
        foreach( layer l_layers
            unless( axlVisibleLayer( layer t )
                s3dWarn( sprintf( nil t_missingFmt layer ) )
            )
        )
        axlClearSelSet()
        axlSetFindFilter( ?enabled l_filter ?onButtons l_filter )
        axlAddSelectAll()
        elems = axlGetSelSet()
        axlClearSelSet()

        errset( axlVisibleSet( saveVis ) )
        when( saveEnabled || saveOn
            errset( axlSetFindFilter( ?enabled saveEnabled
                                      ?onButtons remove( "DYNTHEMALS" saveOn ) ) )
        )
        elems
    )
)
