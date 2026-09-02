;=====================================================================
;  makeVariant3dIntermediates.il
;
;  Exports an Allegro PCB design to an intermediate JSON that the
;  "Simple 3D" Python tool turns into a STEP assembly.
;
;  ORIGIN & CREDIT
;  Based on the original makeVariant3dIntermediates.il by juulsA
;  (https://github.com/juulsA/exportStep). This copy has been
;  modified for the Simple 3D toolchain. Changes vs the original are
;  marked inline with "FIX (simple3d)" or "NEW (simple3d)":
;    * addIndent() - was called 8x but never defined in the repo; added here
;      as s3dAddIndent(), prefixed so it cannot collide with the real one.
;    * getVariantInfo -> gdsysGetVariantInfo (the defined name).
;    * calculateBoardThickness - only SOLDERMASK counts toward the mask
;      thickness; SILKSCREEN/PASTEMASK are also layerType "MASK" and were
;      wrongly folded in and overwritten. Side is decided by position.
;    * makePcb - the no-cutout branch emitted a bare "thickness": 1.67
;      scalar the reader rejects; now emits the real thickness object.
;    * makeSlot - makeCircle was called with 3 args; it takes (xy diameter).
;    * removed a leftover debug printf("i am here").
;    * symbolReturn3DElements - now also emits "mfr_pn" (the MFRPN article
;      number, read from the component definition) for the STEP writer.
;    * s3dGetMfrPn / s3dJsonEscape / s3dCheckMfrPn helpers added.
;    * SILKSCREEN export (format_version 2) - see the SILKSCREEN section
;      below. Adds a small JSON reader so the layer list lives in
;      simple3d_config.json, collection of the silkscreen as filled
;      polygons, and clipping to the board area.
;    * create3dIntermediateFormat - guarded the case where no component has
;      a STEP mapping (car of an unbound marker faulted).
;    * WHAT GETS EXPORTED - the symbol list is built from the design and the
;      variant table only removes from it, so a symbol the Variants.lst
;      parser does not return (mechanical components) is no longer lost.
;      NO_STEP_EXPORT excludes a symbol outright, and says so by name.
;    * symbolReturn3DElements - takes the symbol dbid the caller already
;      holds instead of resolving a refdes string through two lookups.
;
;  USAGE
;    makeVariant3dIntermediates( outputDir [ pcbColor ] [ configFile ] )
;  Writes <design>.json (or one <design>_<variant>.json per variant if a
;  Variants.lst sits BESIDE THE BOARD) into outputDir. Design units must be mm.
;  configFile is the silkscreen layer/settings JSON; when omitted,
;  "simple3d_config.json" in the working directory is used if present, and
;  otherwise the built-in defaults apply.
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

; --- MFRPN helpers DISABLED (property attachment unreliable; kept for future) ---

; defvar( S3D_MfrPnProp "MFRPN" )

; Case-insensitive property read via axlDBGetProperties. The dictionary
; spelling is whatever the netlist declared (F4 prints MFRPN); match loosely.
; procedure( s3dPropCI( dbid t_name )
;     let( ( props p key val want )
;         val  = nil
;         want = upperCase( t_name )
;         when( dbid
;             errset( props = axlDBGetProperties( dbid ) )
;             when( props
;                 foreach( p props
;                     when( p && listp( p )
;                         key = car( p )
;                         unless( stringp( key ) key = sprintf( nil "%L" key ) )
;                         when( upperCase( key ) == want
;                             val = cdr( p )
;                             when( listp( val ) val = car( val ) )
;                         )
;                     )
;                 )
;             )
;         )
;         when( val && !stringp( val ) val = sprintf( nil "%L" val ) )
;         when( val && val != "" val )
;     )
; )

; MFRPN lives on the component definition (F4: "Properties attached to
; component definition"). An instance-level override, if present, wins.
; procedure( s3dGetMfrPn( comp )
;     let( ( val )
;         val = nil
;         when( comp
;             val = s3dPropCI( comp S3D_MfrPnProp )
;             unless( val
;                 when( comp->compdef  val = s3dPropCI( comp->compdef S3D_MfrPnProp ) )
;             )
;         )
;         val
;     )
; )

; Minimal JSON string escaping for the article number.
; procedure( s3dJsonEscape( t_string )
;     let( ( out c i n )
;         unless( stringp( t_string ) t_string = sprintf( nil "%L" t_string ) )
;         out = ""
;         n = strlen( t_string )
;         for( i 1 n
;             c = substring( t_string i 1 )
;             cond(
;                 ( c == "\""  out = strcat( out "\\\"" ) )
;                 ( c == "\\"  out = strcat( out "\\\\" ) )
;                 ( c == "\t"  out = strcat( out "\\t"  ) )
;                 ( c == "\n"  out = strcat( out "\\n"  ) )
;                 ( t          out = strcat( out c ) )
;             )
;         )
;         out
;     )
; )

;=====================================================================
;  WHAT GETS EXPORTED  (NEW - simple3d)
;
;  Two rules, and the second is the reason this section exists at all.
;
;  1. A symbol carrying NO_STEP_EXPORT is never exported, whatever else says
;     otherwise - including its presence in Variants.lst. Each one is named in
;     the console, because a part silently missing from a 3D model is a bug
;     report waiting to happen and the user has no way to tell "excluded on
;     purpose" from "lost".
;
;  2. The list of symbols to export is built from the DESIGN, not from the
;     parsed Variants.lst. That is a reversal: the variant list used to BE the
;     export list, so anything the parser did not hand back simply vanished -
;     which is what happened to mechanical components (Component Class
;     MECHANICAL: real symbols, real PKGDEF_STEP_FILE, no electrical
;     connections). Now the variant table can only ever REMOVE a symbol, never
;     be the sole source of one, and a refdes the table has never heard of is
;     present in every variant. Mechanical parts are exactly that case, and so
;     is anything else the variant machinery does not track.
;=====================================================================

S3D_NoExportProp = "NO_STEP_EXPORT"

; The opt-out from the variant rule. Unlike NO_STEP_EXPORT, which is one of
; Allegro's own symbol properties, this one does not exist until something
; creates it: simple3d.il defines it in the design's property dictionary at
; load and before every export (see s3dEnsureAlwaysProp there, and the config
; switch allegro.defineAlwaysExportProp). Once defined it behaves like any
; other property - it appears in Allegro's Properties dialog and is attached
; the ordinary way.
;
; WHY IT HAS TO EXIST AT ALL. A wire-solder pad and a connector housing look
; identical in the database: both carry a refdes, a STEP model and no BOM
; line, and neither is named in a Variants.lst. But the housing should
; disappear with the connector it belongs to, while the pad is part of the
; bare board and belongs in every variant. No rule can tell those apart,
; because the difference is intent - so the intent is written on the part.
S3D_AlwaysExportProp = "ALWAYS_STEP_EXPORT"

; Per-export sequence for synthesising unique JSON keys for symbols that carry a
; STEP model but no refdes (mechanical parts). Reset at the top of every
; create3dIntermediateFormat so each variant numbers its mechanicals from 1.
S3D_MechSeq = 0

; t if the named property is attached to this object.
;
; Presence is the test, not the value: NO_STEP_EXPORT is a flag with no value,
; so a value-based check would miss it. axlDBGetProperties is used rather than
; the generic ->prop attribute because it hands back a plain assoc list that can
; be walked with a runtime name; property names come back as symbols, hence the
; %L coercion.
procedure( s3dObjectHasProp( o_dbid t_name )
    let( ( props key ( want nil ) ( found nil ) )
        want = upperCase( t_name )
        when( o_dbid
            props = nil
            errset( props = axlDBGetProperties( o_dbid ) )
            foreach( entry props
                when( entry
                    key = if( listp( entry ) then car( entry ) else entry )
                    unless( stringp( key )  key = sprintf( nil "%L" key ) )
                    when( upperCase( key ) == want  found = t )
                )
            )
        )
        found
    )
)

; The VALUE of a named property, or nil.
;
; Same key coercion as s3dObjectHasProp, and for the same reason: the names come
; back as SYMBOLS, so `car( entry ) == "IDX_BEND_TYPE_INFO"` is false however
; plainly the property is there. That cost a round trip with a live board -
; every bend was exported saying it carried no bend parameters while the probe
; printed them.
;
; Entries are (name value) - a two-element list - but a dotted pair is handled
; too, and a valueless flag comes back as t.
procedure( s3dPropValue( o_dbid t_name )
    let( ( props key ( want nil ) ( value nil ) )
        want = upperCase( t_name )
        when( o_dbid
            props = nil
            errset( props = axlDBGetProperties( o_dbid ) )
            foreach( entry props
                when( entry && listp( entry )
                    key = car( entry )
                    unless( stringp( key )  key = sprintf( nil "%L" key ) )
                    when( upperCase( key ) == want
                        value = if( listp( cdr( entry ) ) then
                                    cadr( entry )
                                else
                                    cdr( entry ) )
                    )
                )
            )
        )
        value
    )
)

; t if this symbol is marked NO_STEP_EXPORT.
;
; Checked on the symbol instance (where the F4 dump shows it), and also on the
; component and its definition: putting it on a definition to drop every
; instance of a part - every fiducial, say - is the obvious thing to want, and
; costs nothing to support.
procedure( s3dNoStepExport( o_sym )
    let( ( comp )
        comp = nil
        errset( comp = o_sym->component )
        s3dObjectHasProp( o_sym S3D_NoExportProp ) ||
        (comp && s3dObjectHasProp( comp S3D_NoExportProp )) ||
        (comp && comp->compdef && s3dObjectHasProp( comp->compdef S3D_NoExportProp ))
    )
)

; t if this symbol is marked ALWAYS_STEP_EXPORT - "keep me in every variant".
;
; Read at the same three levels as NO_STEP_EXPORT and for the same reason: on
; the definition it covers every instance of a library part at once, which is
; what a solder pad wants - mark the pad in the library and no board ever needs
; touching again.
;
; Presence is the test, and for this property that is not a simplification: it
; is created as BOOLEAN, and Allegro says of those that the value is ignored
; and the property either exists or does not. Attaching it with a nil value
; still attaches it; the way to say "no" is to DELETE it. Allegro prints that
; itself when you try:
;
;   *WARNING* (axlDBAddProp): Adding Boolean property "ALWAYS_STEP_EXPORT",
;   despite 'nil' being provided as the value. To make the property 'False'
;   instead, call axlDBDeleteProp() to remove it.
procedure( s3dAlwaysStepExport( o_sym )
    let( ( comp )
        comp = nil
        errset( comp = o_sym->component )
        s3dObjectHasProp( o_sym S3D_AlwaysExportProp ) ||
        (comp && s3dObjectHasProp( comp S3D_AlwaysExportProp )) ||
        (comp && comp->compdef && s3dObjectHasProp( comp->compdef S3D_AlwaysExportProp ))
    )
)

; The model files Allegro keeps a copy of INSIDE the .brd, by original
; filename. Returns a list of strings, or nil.
;
; Once a 3D model has been mapped, Allegro stores a copy in the design database
; as an attachment named "3D:<original file name>/<something>", for example
;   3D:SWITRONIC_IT-1187.step/ACIS
; Only the file name is wanted here. Simple 3D never uses those copies - it
; reads model files from disk - but knowing they exist is what lets the export
; tell "this model is nowhere" apart from "this model is in the board, just not
; on your disk", which are two very different problems for the user.
;
; Deliberately tolerant: the part after the last "/" is dropped whatever it
; says, so a different Allegro version naming it something else still parses.
procedure( s3dEmbeddedModels()
    let( ( names out id rest pos ( n 0 ) )
        out = tconc( nil nil )
        names = nil
        errset( names = axlGetAllAttachmentNames() )

        foreach( entry names
            when( stringp( entry ) && (strlen( entry ) > 3) &&
                  (substring( entry 1 3 ) == "3D:")
                ; drop the "3D:" prefix
                rest = substring( entry 4 strlen( entry ) - 3 )
                ; drop a trailing "/<tag>", if there is one
                pos = nil
                for( i 1 strlen( rest )
                    when( substring( rest i 1 ) == "/"  pos = i )
                )
                when( pos  rest = substring( rest 1 pos - 1 ) )
                when( rest && (strlen( rest ) > 0)
                    n = n + 1
                    tconc( out rest )
                )
            )
        )

        cdr( car( out ) )
    )
)

; The same list as one JSON key, ready to drop into the header block. Always
; emitted, even empty, so the shape of the file does not depend on the board.
; No trailing comma: the caller adds the separator.
procedure( s3dEmbeddedModelsJson()
    let( ( models out ( first t ) ( nBad 0 ) )
        models = s3dEmbeddedModels()
        out = "\"embedded_models\": ["
        foreach( m models
            ; A quote or backslash would produce invalid JSON, and this file has
            ; no escaper (the one written for MFRPN is commented out). A model
            ; file named like that does not occur in practice, so skip it and
            ; say so rather than corrupt the whole intermediate.
            if( s3dHasJsonSpecial( m ) then
                nBad = nBad + 1
            else
                unless( first  out = strcat( out ", " ) )
                first = nil
                out = strcat( out "\"" m "\"" )
            )
        )
        when( nBad > 0
            s3dWarn( sprintf( nil "Simple 3D: %d embedded model name(s) contain a quote or backslash and were left out of the report." nBad ) )
        )
        strcat( out "]" )
    )
)

; t if the string holds a character that would need JSON escaping.
procedure( s3dHasJsonSpecial( t_str )
    let( ( ( bad nil ) c )
        for( i 1 strlen( t_str )
            c = substring( t_str i 1 )
            when( (c == "\"") || (c == "\\")  bad = t )
        )
        bad
    )
)

; t if this symbol has a STEP model association (PKGDEF_STEP_FILE on its symbol
; definition) - which is exactly what axlStepGet reports. Used to admit a
; mechanical symbol that carries a 3D model but has no refdes: those are dropped
; by the refdes gate in s3dSymbolsToExport otherwise. Anything without a STEP
; association (FORMAT, DRAFTING, plain graphics) returns nil and is not admitted,
; so this needs no separate symbol-type filter.
procedure( s3dHasStepModel( o_sym )
    let( ( m )
        m = nil
        errset( m = axlStepGet( nil nil o_sym ) )
        m && m->step_name && t
    )
)

; Every refdes the variant table mentions anywhere, upper-cased. Used to judge
; whether the FILE describes this board (s3dVariantFit), not to decide any one
; symbol's fate: a refdes the table never mentions is not exported either, since
; the list governs everything that has one.
;
; Is this token from the variant list a reference designator at all?
;
; The parser splits its lines on spaces and strips a fixed set of characters,
; which leaves the odd bare "\n" behind when a line ends in " )". Such a token
; can never match a real refdes, so it has never changed an export - but it does
; land in the counts ("variant list covers N of M"), and a diagnostic number
; that is quietly one too big is worse than no number.
procedure( s3dIsRefdesToken( t_token )
    stringp( t_token ) && rexMatchp( "[A-Za-z0-9]" t_token )
)

procedure( s3dVariantKnownRefdes( g_variantSymbolList )
    let( ( known )
        known = makeTable( "s3dKnownRefdes" nil )
        when( g_variantSymbolList
            foreach( variant g_variantSymbolList
                foreach( refdes g_variantSymbolList[variant]
                    when( s3dIsRefdesToken( refdes )
                        known[upperCase( refdes )] = t
                    )
                )
            )
        )
        known
    )
)

; Is this symbol a mechanical part? DIAGNOSTIC ONLY - it does not decide an
; export.
;
; It used to be the variant rule (round 49). The rule is now simply "has a
; refdes -> the variant list governs it" (user decision, 2026-08-03), because a
; MECHANICAL-class part with a refdes CAN be named in the list, and when the
; list does not name it the honest reading is "not installed" - the same as for
; any other part. What survives of round 49 is its first test: a symbol with no
; refdes has no logical component either (the docs: refdes is "nil if no
; associated component"), so the two are one condition and the export tests the
; simpler one.
;
; Kept because probe_variants.il reports WHICH KIND of part each symbol is, and
; the three reads below are the only place that question is answered. All read
; defensively - a board can carry a symbol in an unusual state, and none of
; these reads is worth an aborted export:
;
;   * NO LOGICAL COMPONENT. A symbol placed in the layout that the netlist does
;     not know has no `component` at all - and a part that is not in the
;     schematic cannot possibly be in a variant list generated from it. This is
;     the one that matters for a bracket or a mating connector added in Allegro
;     alone, whatever class its symbol happens to carry.
;   * the SYMBOL's own type, "MECHANICAL" (an .osm placed directly, usually
;     without a refdes at all).
;   * the component definition's CLASS, where a PLACED part with a refdes says
;     it is mechanical. On variants_test-b0, A1 and A2 are MOLEX housings
;     sitting exactly on XP1 and XP2 - refdes, a STEP model, no BOM line.
procedure( s3dIsMechanical( o_sym )
    let( ( kind cls comp )
        kind = nil
        cls = nil
        comp = nil
        errset( kind = o_sym->type )
        errset( comp = o_sym->component )
        errset( cls = o_sym->component->compdef->class )
        !comp ||
        (stringp( kind ) && (upperCase( kind ) == "MECHANICAL")) ||
        (stringp( cls ) && (upperCase( cls ) == "MECHANICAL"))
    )
)

; How well the parsed variant table fits THIS board - said out loud, once.
;
; Round 6 caught the Variants.lst that parses into ZERO variants. Two more ways
; the same mistake arrives parse perfectly and then quietly export the whole
; board under variant names, which is indistinguishable from variants working:
;
;   * a STUB - one variant, usually called "dummy", whose base list is empty.
;     It installs nothing, so under the current rule every part with a refdes is
;     dropped and the variant file holds only the symbols that have none.
;     Several projects on this disk carry exactly that file.
;   * a file belonging to a DIFFERENT project: plenty of refdes, none of which
;     exists on this board. Same outcome, and more convincing still, because
;     the variant names look real.
;
; The rule the export follows - "the list governs every part that has a refdes;
; a symbol without one is outside it" - does not change here. This only names
; what is about to happen.
;
; Returns t to go on, and raises for the foreign file: a board exported under
; another project's variant names is worse than no export at all, because
; nothing downstream can tell.
procedure( s3dVariantFit( g_variantSymbolList t_path )
    prog( ( known nKnown nBoard onBoard refdes examples )
        known = s3dVariantKnownRefdes( g_variantSymbolList )
        nKnown = 0
        examples = nil
        foreach( key known
            nKnown = nKnown + 1
            when( length( examples ) < 5  examples = cons( key examples ) )
        )

        nBoard = 0
        onBoard = 0
        foreach( sym axlDBGetDesign()->symbols
            refdes = sym->refdes
            when( refdes
                nBoard = nBoard + 1
                when( known[upperCase( refdes )]  onBoard = onBoard + 1 )
            )
        )

        when( nKnown == 0
            error( strcat(
                sprintf( nil "Simple 3D: %s names variants but lists no components.\n" t_path )
                "Every variant would install nothing, so the export would be a\n"
                "bare board carrying only the symbols that have no refdes. That\n"
                "is what a stub Variants.lst - one empty \"dummy\" variant -\n"
                "produces; several projects carry one by accident.\n"
                "Replace it with this board's own Variants.lst, or delete it to\n"
                "export everything once, without variants.\n" ) )
        )

        when( (nBoard > 0) && (onBoard == 0)
            error( strcat(
                sprintf( nil "Simple 3D: %s does not describe this board.\n" t_path )
                sprintf( nil "None of the %d component(s) it lists is placed here, and %d are.\n"
                         nKnown nBoard )
                sprintf( nil "It lists, for example: %L\n" reverse( examples ) )
                "That file belongs to a different project. Exporting with it would\n"
                "install none of this board's components, writing one STRIPPED\n"
                "board per variant name, which nothing downstream could tell from\n"
                "a real set of variants.\n"
                "Replace it with this board's own Variants.lst, or delete it to\n"
                "export everything once, without variants.\n" ) )
        )

        printf( "Simple 3D: variant list covers %d of %d placed component(s).\n"
                onBoard nBoard )
        t
    )
)

; The symbol dbids to export for one variant (or for the whole design when
; there is no variant table). Returns dbids, not names: iterating the design
; already has the symbol in hand, so nothing has to be looked up again by
; refdes - which is one less way for a symbol to go missing.
procedure( s3dSymbolsToExport( g_variantSymbolList t_variant )
    let( ( out installed refdes label ( nNoExport 0 ) ( nNotInVariant 0 )
           ( nUntracked 0 ) ( nAlways 0 ) )
        out = tconc( nil nil )
        ; Only what THIS variant installs is needed now. The union over all
        ; variants (s3dVariantKnownRefdes) is still built, once, by
        ; s3dVariantFit - to judge whether the file describes this board at all.
        installed = makeTable( "s3dInstalled" nil )
        when( g_variantSymbolList && t_variant
            foreach( refdes g_variantSymbolList[t_variant]
                when( s3dIsRefdesToken( refdes )
                    installed[upperCase( refdes )] = t
                )
            )
        )

        foreach( sym axlDBGetDesign()->symbols
            refdes = sym->refdes
            ; Admit a symbol that has a refdes (a placed component) OR one that
            ; carries a STEP model but no refdes (a mechanical part, e.g. a
            ; CR2032 holder). Short-circuit keeps the extra axlStepGet probe off
            ; the refdes-bearing symbols, so their path is unchanged.
            when( refdes || s3dHasStepModel( sym )
                cond(
                    ( s3dNoStepExport( sym )
                        nNoExport = nNoExport + 1
                        ; %s on nil throws ("format spec. incompatible with
                        ; data"), which would kill the whole export from inside
                        ; a message. sym->name is documented as a string, but
                        ; this branch exists precisely for symbols in unusual
                        ; states - and symbolReturn3DElements already guards the
                        ; same read the same way.
                        label = if( refdes then
                                    refdes
                                else
                                    if( sym->name then sym->name else "(unnamed symbol)" ) )
                        printf( "Simple 3D: %s - NOT exported: the symbol carries the %s property.\n"
                                label S3D_NoExportProp )
                    )
                    ; With a variant table, ANYTHING THAT HAS A REFDES is
                    ; exported only if this variant installs it - mechanical or
                    ; not. Absence from the list is the list saying "not
                    ; installed", and a refdes is exactly what makes a part
                    ; nameable in the list at all.
                    ;
                    ; Two earlier rules stood here (user decision, 2026-08-03):
                    ; "the variant list IS the export list" lost mechanical
                    ; parts; "subtract only what the table mentions somewhere"
                    ; kept R3 in every variant; and "subtract only what is not
                    ; s3dIsMechanical" kept a MECHANICAL-class part with a
                    ; refdes - A1/A2/A4, MOLEX housings - in variants that do
                    ; not install it. The distinction is now the one the data
                    ; actually carries: a refdes can be listed, so the list
                    ; governs it; a symbol without one never can be, so nothing
                    ; but NO_STEP_EXPORT governs it. See s3dIsMechanical, which
                    ; remains for the probe and no longer decides an export.
                    ;
                    ; t_variant is tested for the same reason `installed` is
                    ; built under it: a table with no variant named fills nothing
                    ; in, and under this rule that would drop EVERY component
                    ; rather than a few. No caller does it - both do exist, so
                    ; the guard costs one comparison and removes a silent one.
                    ;
                    ; ALWAYS_STEP_EXPORT is the one way out, and it is tested
                    ; LAST so that it cannot rescue a symbol NO_STEP_EXPORT has
                    ; already excluded: "never" outranks "always". It is also
                    ; the only test here that costs a property read per symbol,
                    ; and the && chain reaches it only for a part the variant
                    ; was about to drop.
                    ( g_variantSymbolList && t_variant && refdes &&
                      !installed[upperCase( refdes )] &&
                      !s3dAlwaysStepExport( sym )
                        nNotInVariant = nNotInVariant + 1
                    )
                    ( t
                        when( g_variantSymbolList && !refdes
                            nUntracked = nUntracked + 1
                        )
                        when( g_variantSymbolList && refdes &&
                              !installed[upperCase( refdes )]
                            nAlways = nAlways + 1
                        )
                        tconc( out sym )
                    )
                )
            )
        )

        when( nNoExport > 0
            printf( "Simple 3D: %d symbol(s) excluded by %s.\n" nNoExport S3D_NoExportProp )
        )
        when( nNotInVariant > 0
            printf( "Simple 3D: %d component(s) not installed in variant %s.\n"
                    nNotInVariant t_variant )
        )
        when( nUntracked > 0
            printf( "Simple 3D: %d symbol(s) have no refdes and cannot be named in a variant; exported in every variant.\n"
                    nUntracked )
        )
        when( nAlways > 0
            printf( "Simple 3D: %d component(s) not installed in variant %s but kept by %s.\n"
                    nAlways t_variant S3D_AlwaysExportProp )
        )
        cdr( car( out ) )
    )
)

; Pre-flight check for the Simple 3D menu. Returns
;   ( refDesWithoutMfrPn  refDesWithoutStepModel ).
; Only components that would be exported (refdes + STEP mapping) are checked.
procedure( s3dCheckMfrPn()
    let( ( noMfrPn noModel sym comp mapping )
        noMfrPn = tconc( nil nil )
        noModel = tconc( nil nil )
        foreach( sym axlDBGetDesign()->symbols
            ; Symbols excluded on purpose must not be reported as missing a 3D
            ; model - that list is for parts that WOULD be exported if they had
            ; one, and padding it with deliberate exclusions makes it useless.
            when( sym->refdes && !s3dNoStepExport( sym )
                mapping = nil
                errset( mapping = axlStepGet( nil nil sym ) )
                if( mapping && mapping->step_name then
                    ; MFRPN check DISABLED (property attachment unreliable);
                    ; kept for future - restore the two lines below to re-enable:
                    ; comp = sym->component
                    ; unless( s3dGetMfrPn( comp )  tconc( noMfrPn sym->refdes ) )
                    t
                else
                    tconc( noModel sym->refdes )
                )
            )
        )
        list( cdr( car( noMfrPn ) ) cdr( car( noModel ) ) )
    )
)

;=====================================================================
;  ORIGINAL SCRIPT (with the inline fixes noted in the header)
;=====================================================================

procedure( gdsysGetVariantInfo()
    ; FIX (simple3d): beside the BOARD, not in Allegro's working directory.
    ; See s3dVariantFilePath.
    let(    (   ( variantFile s3dVariantFilePath() )
            ( state "findVariant" )
            pattern inPort currentVariant variantTable alternateParts part partProperties refDes symbols
            ; Declared since round 75 (plan D2): SKILL is dynamically scoped, so
            ; a name assigned here without a declaration became a session
            ; global - tools/skill_checks.py check #5 reports such a name now.
            newLine newLineEnd newLineWithinProperty propertyStart propertySeparator blankSpace
            line parts subStrings properties temp valueKey )

        pattern = pcreCompile("[\"\t+\\()]")
        newLine = pcreCompile("\t\t")
        newLineEnd = pcreCompile("\t\t \\)")
        newLineWithinProperty = pcreCompile( "=\"\t\t " )
        propertyStart = pcreCompile( "^\t\t\\(.*" )
        propertySeparator = pcreCompile( "(\" )" )
        blankSpace = pcreCompile( " " )

        inPort = infile( variantFile )

        if( inPort then

            variantTable = makeTable( "variantTable" nil )
            alternateParts = makeTable( "alternateParts" nil )
            parts = makeTable( "parts" nil )
            partProperties = makeTable( "partProperties" nil )

            while( gets( line inPort )

                case( state
                    (
                        "findVariant"
                        ; parse for \"
                        subStrings = parseString( line "\"" )

                        when( length( subStrings ) == 3
                            currentVariant = nth( 1 subStrings )
                            state = "awaitStartCondition"
                        )
                    )
                    (
                        "awaitStartCondition"
                        when( strcmp( line "\t\t(base\n" ) == 0
                            state = "appendSymbols"
                            symbols = list()
                        )
                    )
                    (
                        "appendSymbols"
                        if( strcmp( line "\t\t)\n" ) == 0 then
                            state = "awaitEndCondition"
                        else
                            ;append symbols to list
                            symbols = nconc( symbols parseString( line ) )
                        )
                    )
                    (
                        "awaitEndCondition"
                        if( strcmp( line "\t)\n" ) == 0 then
                            ;remove ")" in list
                            symbols = remove( ")" symbols )
                            symbols = mapcar( lambda( ( symbol ) pcreReplace( pattern symbol "" 0 ) )  symbols )

                            ; append components to array
                            variantTable[currentVariant] = symbols
                            alternateParts[currentVariant] = parts

                            ; initialize parts (again, clear previous values)
                            parts = makeTable( "parts" nil )

                            state = "findVariant"
                        else
                            ; alternate part properties
                            when( pcreMatchp( propertyStart line )

                                ; find variant specific information
                                subStrings = parseString( line )

                                when( length( subStrings ) > 1
                                    refDes = pcreReplace( pattern nth( 0 subStrings ) "" 0 )

                                    ; substrings without first element (refDes)
                                    properties = buildString( cdr(subStrings) )

                                    temp = pcreReplace( propertySeparator properties "\\\\" 0 )
                                    subStrings = parseString( temp "\\\\" )

                                    ; check, if property information ends in this line
                                    if( strcmp( car(last(subStrings)) ")\n" ) == 0 then

                                        foreach( subString subStrings
                                            ; parse properties
                                            valueKey = parseString( subString "=" )

                                            when( length(valueKey ) == 2
                                                partProperties[nth( 0 valueKey )] = pcreReplace( pattern nth( 1 valueKey ) "" 0 )
                                            )
                                        )

                                        ; set part properties, clear properties
                                        parts[refDes] = partProperties
                                        partProperties = makeTable( "partProperties" nil )

                                        ; append to symbol list
                                        ; FIX (simple3d): was nth( 0 subStrings ),
                                        ; but subStrings was reassigned above to the
                                        ; PROPERTY chunks, so this appended the first
                                        ; property token ("VALUE=12pF") to the variant's
                                        ; symbol list instead of the refdes. Seen on
                                        ; PAG30N/BNO as two
                                        ;   Simple 3D: VALUE=12pF - not found in the design
                                        ; lines. refDes is already correct here - it is
                                        ; what parts[refDes] above is keyed by.
                                        symbols = nconc( symbols list( refDes ) )
                                    else
                                        state = "awaitMoreProperties"
                                    )
                                )
                            )
                        )
                    )
                    (
                        "awaitMoreProperties"
                        ; add more properties

                        ; append line to properties and check
                        ; newLineEnd needs to be replaced by space + ), because the last space is ignore by buildString (...) in previous loop
                        properties = strcat( properties pcreReplace( newLineEnd line " )" 0 ) )
                        properties = pcreReplace( newLineWithinProperty properties "=\"" 0 )
                        properties = pcreReplace( newLine properties "" 0 )
                        temp = pcreReplace( propertySeparator properties "\\\\" 0 )
                        temp = pcreReplace( newLineEnd temp "\\\\" 0 )
                        subStrings = parseString( temp "\\\\" )

                        ; check, if property information ends in this line
                        when( strcmp( car(last(subStrings)) ")\n" ) == 0
                            foreach( subString subStrings

                                ; parse properties
                                valueKey = parseString( subString "=" )

                                when( length(valueKey ) == 2
                                    partProperties[nth( 0 valueKey )] = pcreReplace( blankSpace pcreReplace( pattern cadr( valueKey ) "" 0 ) "" 0 )
                                )
                            )

                            ; set part properties, clear properties
                            parts[refDes] = partProperties
                            partProperties = makeTable( "partProperties" nil )

                            ; append to symbol list
                            ; FIX (simple3d): same bug as in the single-line branch
                            ; above - subStrings holds property chunks by now, not
                            ; the refdes. This is the multi-line-properties path.
                            symbols = nconc( symbols list( refDes ) )

                            properties = ""

                            state = "awaitEndCondition"
                        )
                    )
                    (
                        t
                        warn( "I should not be here ... " )
                    )
                )
            )
            list( variantTable alternateParts )
        else
            error( "Can not read from file ... " )
            nil
        )
    )
)

procedure( makeLine( segment )
    let( ( extents xStart yStart xEnd yEnd element )
        extents = segment->startEnd

        xStart = caar( extents )
        yStart = cadar( extents )

        xEnd = caadr( extents )
        yEnd = cadadr( extents )

        element = strcat(
            "{\n\t\"type\": \"segment\",\n"
            "\t\"start\": [" sprintf( nil "%f" xStart ) ", " sprintf( nil "%f" yStart ) "],\n"
            "\t\"end\": [" sprintf( nil "%f" xEnd ) ", " sprintf( nil "%f" yEnd ) "]\n"
            "}"
        )
    )
)

procedure( makeArc( segment )
    let( ( xy xCenter yCenter radius extents xStart yStart xEnd yEnd cw ccw angle1 angle2 startAngle endAngle element )
        xy = segment->xy
        xCenter = car( xy )
        yCenter = cadr( xy )

        radius = segment->radius

        extents = segment->startEnd

        xStart = caar( extents )
        yStart = cadar( extents )

        xEnd = caadr( extents )
        yEnd = cadadr( extents )

        cw = segment->isClockwise

        if(cw then
            ccw = "false"
        else
            ccw = "true"
        )

        angle1 =  axlRadToDeg( atan2( ( yStart - yCenter ), ( xStart - xCenter ) ) )

        ; convert to positive angle
        when( negativep( angle1 )
            angle1 = angle1 + 360
        )

        angle2 = axlRadToDeg( atan2( ( yEnd - yCenter ), ( xEnd - xCenter ) ) )

        ; convert to positive angle
        when( negativep( angle2 )
            angle2 = angle2 + 360
        )

        if( cw then
            startAngle = angle2
            endAngle = angle1
        else
            startAngle = angle1
            endAngle = angle2
        )

        element = strcat(
            "{\n\t\"type\": \"arc\",\n"
            "\t\"center\": [" sprintf( nil "%f" xCenter ) ", " sprintf( nil "%f" yCenter ) "],\n"
            "\t\"radius\": " sprintf( nil "%f" radius ) ",\n"
            "\t\"alpha\": " sprintf( nil "%f" startAngle ) ",\n"
            "\t\"beta\": " sprintf( nil "%f" endAngle ) ",\n"
            "\t\"ccw\": " ccw "\n"
            "}"
        )
    )
)

procedure( makeCircle( xy diameter )
    let( ( element )
        element = strcat(
            "{\n\t\"type\": \"circle\",\n"
            "\t\"x\": " sprintf( nil "%f" xCoord( xy ) ) ",\n"
            "\t\"y\": " sprintf( nil "%f" yCoord( xy ) ) ",\n"
            "\t\"radius\": " sprintf( nil "%f" diameter/2 ) "\n"
            "}"
        )
    )
)

procedure( rotateXY( origin xy angle )
    let( ( angleRad dX dY dXY x y )
        angleRad = axlDegToRad( angle )
        dX = xCoord( xy ) - xCoord( origin )
        dY = yCoord( xy ) - yCoord( origin )
        dXY = list( dX dY )

        x = xCoord( origin ) + xCoord( dXY ) * cos( angleRad ) - yCoord( dXY ) * sin( angleRad )
        y = yCoord( origin ) + xCoord( dXY ) * sin( angleRad ) + yCoord( dXY ) * cos( angleRad )

        list( x y )
    )
)

; Where the DRILL is, which is not always where the pad is.
;
; A padstack may carry an offset from its origin to the hole - Allegro's
; Padstack Editor calls it "Offset from padstack origin to hole", on the Drill
; Offset tab - and an edge connector is exactly what it is for: the pads sit on
; the board while the holes straddle the edge as half-holes. The offset is
; expressed in the PADSTACK's own frame, so it must be rotated by the pin's
; rotation before it is added to the pin's location.
;
; This lived inside makeSlot and nowhere else, so the round-hole branch of
; symbolReturnPinHoles cut at the PAD centre. On the user's bone-a2 the four
; PLS-4 holes carry offset x = 0.375 with the padstack turned to face the board
; edge: the drill belongs on y = 0 and we were putting it 0.375 mm higher, which
; is why Allegro's own 3D showed half-circles on the edge where our STEP showed
; keyholes. One procedure now, called from both branches, so they cannot drift
; apart again.
;
; nil-safe on both counts: a padstack with no offset and a pin with no rotation
; are the ordinary case, and both mean "the drill is where the pad is".
procedure( s3dDrillXY( pin padstack )
    let( ( xy offset rotation dx dy )
        xy       = pin->xy
        offset   = padstack->drillOffset
        rotation = pin->rotation
        dx = 0.0
        dy = 0.0
        when( offset
            when( numberp( xCoord( offset ) )  dx = xCoord( offset ) )
            when( numberp( yCoord( offset ) )  dy = yCoord( offset ) )
        )
        unless( numberp( rotation )  rotation = 0.0 )
        if( (dx == 0.0) && (dy == 0.0) then
            ; Nothing to apply. Returned as-is rather than rotated by zero, so
            ; the overwhelmingly common padstack is not put through a sin/cos
            ; that can only add noise to a coordinate that was exact.
            xy
        else
            rotateXY( xy list( xCoord( xy ) + dx  yCoord( xy ) + dy ) rotation )
        )
    )
)

procedure( makeSlot( pin padstack )
    let( ( xy x y rotation drillSizeWidth drillSizeHeight slot radius xCenter yCenter xyCenter alpha beta ccw segment
           tmp xStart yStart xEnd yEnd xyStart xyEnd )   ; declared, round 75 (D2)
        ; get coordinates - the DRILL's, not the pad's
        rotation = pin->rotation

        xy = s3dDrillXY( pin padstack )
        x = xCoord( xy )
        y = yCoord( xy )

        drillSizeWidth = padstack->drillSizeWidth
        drillSizeHeight = padstack->drillSizeHeight

        ; if slot is actually a hole
        if( drillSizeWidth == drillSizeHeight then
            ; FIX (simple3d): makeCircle takes (xy diameter), not (x y d).
            slot = makeCircle( list( x y ) drillSizeWidth )
        else
            ; default state is drillSizeWidth < drillSizeHeight
            ; otherwise swap both and add 90 deg rotation
            unless( drillSizeHeight >= drillSizeWidth
                tmp = drillSizeWidth
                drillSizeWidth = drillSizeHeight
                drillSizeHeight = tmp
                rotation = rotation + 90.0
            )

            ; calculate radius
            radius = drillSizeWidth / 2

            ; make first half circle
            xCenter = x
            yCenter = y + ( drillSizeHeight - drillSizeWidth ) / 2

            ; apply rotation
            xyCenter = rotateXY( xy list( xCenter yCenter ) rotation )
            xCenter = xCoord( xyCenter )
            yCenter = yCoord( xyCenter )

            ; calculate angles
            alpha = 0.0 + rotation
            beta = 180.0 + rotation
            alpha = modf( alpha 360.0 )
            beta = modf( beta 360.0 )
            ccw = "false"

            segment = strcat(
                "{\n\t\"type\": \"arc\",\n"
                "\t\"center\": [" sprintf( nil "%f" xCenter ) ", " sprintf( nil "%f" yCenter ) "],\n"
                "\t\"radius\": " sprintf( nil "%f" radius ) ",\n"
                "\t\"alpha\": " sprintf( nil "%f" alpha ) ",\n"
                "\t\"beta\": " sprintf( nil "%f" beta ) ",\n"
                "\t\"ccw\": " ccw "\n"
                "}"
            )

            slot = tconc( nil segment )

            ; make first line
            xStart = x - radius
            yStart = y + ( drillSizeHeight - drillSizeWidth ) / 2

            xEnd = x - radius
            yEnd = y - ( drillSizeHeight - drillSizeWidth ) / 2

            ; apply rotation
            xyStart = rotateXY( xy list( xStart yStart ) rotation )
            xStart = xCoord( xyStart )
            yStart = yCoord( xyStart )

            xyEnd = rotateXY( xy list( xEnd yEnd ) rotation )
            xEnd = xCoord( xyEnd )
            yEnd = yCoord( xyEnd )

            segment = strcat(
                "{\n\t\"type\": \"segment\",\n"
                "\t\"start\": [" sprintf( nil "%f" xStart ) ", " sprintf( nil "%f" yStart ) "],\n"
                "\t\"end\": [" sprintf( nil "%f" xEnd ) ", " sprintf( nil "%f" yEnd ) "]\n"
                "}"
            )

            tconc( slot segment )

            ; make last half circle
            xCenter = x
            yCenter = y - ( drillSizeHeight - drillSizeWidth ) / 2

            ; apply rotation
            xyCenter = rotateXY( xy list( xCenter yCenter ) rotation )
            xCenter = xCoord( xyCenter )
            yCenter = yCoord( xyCenter )

            ; calculate angles
            alpha = 180.0 + rotation
            beta = 360.0 + rotation
            alpha = modf( alpha 360.0 )
            beta = modf( beta 360.0 )
            ccw = "true"

            segment = strcat(
                "{\n\t\"type\": \"arc\",\n"
                "\t\"center\": [" sprintf( nil "%f" xCenter ) ", " sprintf( nil "%f" yCenter ) "],\n"
                "\t\"radius\": " sprintf( nil "%f" radius ) ",\n"
                "\t\"alpha\": " sprintf( nil "%f" alpha ) ",\n"
                "\t\"beta\": " sprintf( nil "%f" beta ) ",\n"
                "\t\"ccw\": " ccw "\n"
                "}"
            )

            tconc( slot segment )

            ; make last line
            xStart = x + radius
            yStart = y - ( drillSizeHeight - drillSizeWidth ) / 2

            xEnd = x + radius
            yEnd = y + ( drillSizeHeight - drillSizeWidth ) / 2

            ; apply rotation
            xyStart = rotateXY( xy list( xStart yStart ) rotation )
            xStart = xCoord( xyStart )
            yStart = yCoord( xyStart )

            xyEnd = rotateXY( xy list( xEnd yEnd ) rotation )
            xEnd = xCoord( xyEnd )
            yEnd = yCoord( xyEnd )

            segment = strcat(
                "{\n\t\"type\": \"segment\",\n"
                "\t\"start\": [" sprintf( nil "%f" xStart ) ", " sprintf( nil "%f" yStart ) "],\n"
                "\t\"end\": [" sprintf( nil "%f" xEnd ) ", " sprintf( nil "%f" yEnd ) "]\n"
                "}"
            )

            tconc( slot segment )
        )
        ; return slot
        car( slot )
    )
)

procedure( boardGeometryParseSegment( segment )
    let( ( element )
        case( segment->objType
            (
                "line"
                element = makeLine( segment )
            )
            (
                "arc"
                if( segment->isCircle then
                    element = makeCircle( segment->xy 2*segment->radius )
                else
                    element = makeArc( segment )
                )
            )
            (
                t
                warn( "Unknown segment ...\n")
            )
        )
        element
    )
)

procedure( calculateBoardThickness()
    ; FIX (simple3d): SILKSCREEN_* and PASTEMASK_* are ALSO layerType "MASK"
    ; (verified on a real board), so the original
    ;     if name == "SOLDERMASK_TOP" then top else bottom
    ; put silkscreen into the bottom mask and, using plain "=", let each later
    ; MASK layer overwrite the previous one. Now: only SOLDERMASK layers count,
    ; classified top/bottom by cross-section position relative to the outermost
    ; conductor (so a renamed mask still lands correctly). Dielectric pseudo-
    ; layers have name = nil, hence the guard.
    ;
    ; NOTE (simple3d): this sums a SINGLE stackup. Multi-stackup / rigid-flex
    ; designs (more than one stackup zone) are NOT supported - the whole board
    ; is exported with this one averaged thickness. See the README limitation.
    let( ( stackup padToPadThickness topSoldermaskThickness bottomSoldermaskThickness
           topCondPos nm thk )
        stackup = axlXSectionGet( nil 'all )
        padToPadThickness = 0.0
        topSoldermaskThickness = 0.0
        bottomSoldermaskThickness = 0.0
        topCondPos = nil

        ; first conductor/plane from the top gives the reference position
        foreach( layer stackup
            case( layer->layerType
                ( ( "CONDUCTOR" "PLANE" )
                    unless( topCondPos  topCondPos = layer->position )
                )
                ( t nil )
            )
        )

        foreach( layer stackup
            thk = layer->thickness
            unless( thk  thk = 0.0 )
            case( layer->layerType
                ( ( "CONDUCTOR" "DIELECTRIC" "PLANE" )
                    padToPadThickness = padToPadThickness + thk
                )
                ( ( "MASK" )
                    nm = if( layer->name then upperCase( layer->name ) else "" )
                    when( substring( nm 1 10 ) == "SOLDERMASK"
                        if( topCondPos && layer->position && (layer->position < topCondPos) then
                            topSoldermaskThickness = topSoldermaskThickness + thk
                        else
                            bottomSoldermaskThickness = bottomSoldermaskThickness + thk
                        )
                    )
                )
                ( t nil )
            )
        )
        list( topSoldermaskThickness padToPadThickness bottomSoldermaskThickness )
    )
)

;=====================================================================
;  MULTI-STACKUP / RIGID-FLEX
;
;  A rigid-flex board is several zones, each with its own stackup and its
;  own thickness. Everything needed is in the database:
;
;    axlXSectionGet( nil 'stackups )   -> the stackup names
;    axlXSectionGet( <name> 'all )     -> that stackup's layers
;    design->groups, type "ZONE_GROUP" -> the zones
;    zone->stackup                     -> which stackup a zone uses
;    zone->groupMembers                -> the zone outline polygon
;
;  Measured on a real rigid-flex board, and the reason this is not simply
;  "one thickness per zone": FLEX, STIFFENER1 and STIFFENER2 total 0.365,
;  0.49 and 2.44 but their conductor cores are all 0.215. The zones butt
;  against each other at the COPPER, not at their outer faces - a 2.44 mm
;  stiffener grows 2.125 up and 0.1 down from the same core. So each zone
;  is emitted as (above, core, below), not as one number.
;=====================================================================

; (above core below) for one stackup, in design units. g_stackup may be nil
; for a single-stackup design.
;
; Split by POSITION relative to the outermost conductors, never by layer
; name. A flex stackup has no SOLDERMASK layer at all - coverlay, adhesive
; and stiffener sit there instead - so the name gate calculateBoardThickness
; uses reports 0.0 for both sides of it. Verified against the API's own
; axlXSectionGet(<name> 'thickness): above+core+below reproduces it exactly
; on every stackup of the test board.
; Thickness of one cross-section entry, 0.0 when it has none (the two
; surface entries).
procedure( s3dLayerThk( o_layer )
    let( ( thk )
        thk = nil
        errset( thk = o_layer->thickness )
        if( thk && numberp( thk ) then thk else 0.0 )
    )
)

; Index (0-based) of the first and last conductor in the entry list, as
; ( firstIdx lastIdx ), or nil if the stackup has no conductor at all.
;
; **LIST ORDER, never layer->position.** Measured on a real rigid-flex
; board: position DUPLICATES (6 is both SOLDERMASK_TOP and the dielectric,
; 10 is both SOLDERMASK_BOTTOM and the bottom surface) and is not monotonic,
; because it indexes the combined "All Stackups" view rather than this
; stackup. The order axlXSectionGet( <name> 'all ) returns IS the physical
; order - checked line by line against Allegro's own cross-section editor,
; top surface first.
;
; The earlier version of this code compared positions and put SOLDERMASK_TOP
; inside the core instead of above it: the total still came out right, so
; nothing looked wrong, but the core - which is the datum every zone is
; aligned on - sat 0.025 mm low on one stackup.
procedure( s3dConductorSpan( l_layers )
    let( ( ( i 0 ) first last )
        foreach( layer l_layers
            case( layer->layerType
                ( ( "CONDUCTOR" "PLANE" )
                    unless( first  first = i )
                    last = i
                )
                ( t nil )
            )
            i = i + 1
        )
        when( first  list( first last ) )
    )
)

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

; The contour of one shape or polygon, as a JSON array of primitives.
; Same parser the board outline uses - a zone outline, a stiffener shape and
; the board edge all carry the same line/arc segments.
procedure( s3dContourJson( o_dbid )
    let( ( contour element )
        contour = nil
        errset(
            foreach( segment o_dbid->segments
                element = boardGeometryParseSegment( segment )
                when( element
                    if( contour then
                        tconc( contour element )
                    else
                        contour = tconc( nil element )
                    )
                )
            )
        )
        when( contour
            strcat( "[\n" s3dAddIndent( buildString( car( contour ) ",\n" ) ) "\n]" )
        )
    )
)

; Layer-name prefixes whose drawn shapes are OPENINGS, not material.
; Overridden from settings.negativeLayers in simple3d_config.json.
;
; Kept as a named default as well, because the override is a GLOBAL and these
; files load once per Allegro session: without something to restore, the list
; one board's config set outlives that board. See s3dSilkConfig, and the
; round-42 note on S3D_ExportFullBoard just below.
S3D_NegativeLayersDefault = list( "COVERLAY" "SOLDERMASK" "PASTEMASK" )
S3D_NegativeLayers = S3D_NegativeLayersDefault

; Write <design>.json - the WHOLE board, variants ignored - beside the
; per-variant files. Overridden from settings.exportFullBoard.
;
; Why it is wanted: the variant list decides what is INSTALLED, and a drawing
; sometimes has to show what is on the bare board regardless - the same reason
; ALWAYS_STEP_EXPORT exists, but for the whole board at once rather than part by
; part. NO_STEP_EXPORT still applies: it is tested before any variant question.
;
; The file has the name the no-variant export already uses, which cannot collide
; with <design>_<variant>.json, and it carries "full_board": true so the window
; can name it in the queue rather than showing one nameless extra file.
S3D_ExportFullBoard = t

; t if this layer's shapes are openings rather than material.
;
; Determined by IPC-2581 layer FUNCTION where the design carries one -
; layerFunction is what the Mask Layer Site File assigns, per the rigid-flex
; documentation - and by name prefix otherwise.
;
; NOT by negativeArtwork: that flag is about film generation and reads nil on
; every layer of a real rigid-flex board, including the coverlay, which is
; unambiguously drawn as openings. Believing it produced a board with the
; coverlay inverted - material where the windows should be.
procedure( s3dLayerIsNegative( o_layer )
    let( ( nm fn ( neg nil ) probe )
        nm = nil
        errset( nm = o_layer->name )
        fn = nil
        errset( fn = o_layer->layerFunction )

        ; the function name, when there is one, carries the same words
        probe = ""
        when( stringp( fn )  probe = upperCase( fn ) )
        when( stringp( nm )  probe = strcat( probe " " upperCase( nm ) ) )

        foreach( key S3D_NegativeLayers
            when( stringp( key ) && (strlen( key ) > 0)
                ; substring search, so COVERLAY matches COVERLAY_TOP and a
                ; function spelled "Coverlay" alike
                for( i 1 (strlen( probe ) - strlen( key ) + 1)
                    when( substring( probe i strlen( key ) ) == upperCase( key )
                        neg = t
                    )
                )
            )
        )
        neg
    )
)

; One drawn shape as { "outline": [...], "voids": [ [...], ... ] }.
;
; Voids are the holes punched in a layer - ADHESIVE_TOP has 7 of them on the
; test board, STIFFENER_TOP and ADHESIVE_TOP2 six each, and the six small
; COVERLAY_TOP patches sit exactly in those holes. They have to become holes
; in the face, not material.
procedure( s3dShapeJson( o_shape )
    let( ( outline voids body ( firstVoid t ) )
        outline = s3dContourJson( o_shape )
        when( outline
            body = strcat( "{\n\t\"outline\": " s3dAddIndent( outline ) )

            voids = nil
            errset( voids = o_shape->voids )
            if( voids then
                body = strcat( body ",\n\t\"voids\": [\n" )
                foreach( v voids
                    when( s3dContourJson( v )
                        unless( firstVoid  body = strcat( body ",\n" ) )
                        firstVoid = nil
                        body = strcat( body s3dAddIndent( s3dContourJson( v ) 2 ) )
                    )
                )
                body = strcat( body "\n\t]" )
            else
                body = strcat( body ",\n\t\"voids\": []" )
            )
            strcat( body "\n}" )
        )
    )
)

; Shapes on the RIGID FLEX class, grouped by subclass name. Built once per
; export; nil until s3dCollectRigidFlexShapes has run.
S3D_RigidFlexShapes = nil

; Ask for the WHOLE class once and sort the answer, rather than asking for each
; stackup layer by name.
;
; Asking by name made Allegro print
;     *WARNING* (axlDBGetShapes): No match for subclass name - "RIGID FLEX/TOP"
; for every conductor, the dielectric and the soldermask - none of which is ever
; drawn on this class - and once per stackup that contains them, so ten warnings
; on a three-stackup board. A miss cannot happen here: what is not in the table
; simply is not there. It is also one database query instead of one per layer
; per stackup, which mattered less but is not nothing.
;
; Only the RIGID FLEX class is consulted. PACKAGE GEOMETRY/SOLDERMASK_* also
; exists but describes footprint openings, not the extent of a board layer, so
; asking for it would be wrong rather than merely unhelpful.
procedure( s3dCollectRigidFlexShapes()
    let( ( shapes key pos ( n 0 ) )
        S3D_RigidFlexShapes = makeTable( "s3dRigidFlexShapes" nil )
        shapes = nil
        errset( shapes = axlDBGetShapes( "RIGID FLEX" ) )

        foreach( s shapes
            key = nil
            errset( key = s->layer )
            when( stringp( key )
                ; "RIGID FLEX/COVERLAY_TOP" -> "COVERLAY_TOP"
                pos = nil
                for( i 1 strlen( key )
                    when( substring( key i 1 ) == "/"  pos = i )
                )
                when( pos
                    key = substring( key pos + 1 strlen( key ) - pos )
                    n = n + 1
                    S3D_RigidFlexShapes[key] = cons( s S3D_RigidFlexShapes[key] )
                )
            )
        )
        when( n > 0
            printf( "Simple 3D: %d shape(s) on RIGID FLEX subclasses.\n" n )
        )
        S3D_RigidFlexShapes
    )
)

; Every drawn shape of one stackup layer, as a JSON array. nil when the layer
; has none - conductors, the dielectric and the soldermask are not drawn on
; the RIGID FLEX class, and those layers span the whole zone instead.
procedure( s3dLayerShapesJson( t_layerName )
    let( ( shapes body ( first t ) one )
        unless( S3D_RigidFlexShapes  s3dCollectRigidFlexShapes() )
        shapes = S3D_RigidFlexShapes[t_layerName]
        when( shapes
            body = "[\n"
            foreach( s shapes
                one = s3dShapeJson( s )
                when( one
                    unless( first  body = strcat( body ",\n" ) )
                    first = nil
                    body = strcat( body s3dAddIndent( one ) )
                )
            )
            unless( first  strcat( body "\n]" ) )
        )
    )
)

; Every rigid-flex zone as ( name stackup outlineDbid ). nil when the design
; has no zones, which is the ordinary single-stackup case.
;
; The outline is the zone group's member, NOT zone->shapeBoundary: the
; reference calls that the boundary, but it comes back nil on every zone of
; a real board. Sweeping the RIGID FLEX/ZONE_OUTLINE subclass finds the same
; polygons, but their ->group and ->groups are nil, so that route cannot say
; which zone an outline belongs to. Going through the group is the only way
; to keep the association.
procedure( s3dZoneList()
    let( ( out groups outline )
        out = tconc( nil nil )
        groups = nil
        errset( groups = axlDBGetDesign()->groups )

        foreach( g groups
            when( g && (g->type == "ZONE_GROUP") && g->stackup
                outline = nil
                errset( outline = car( g->groupMembers ) )
                when( outline && outline->segments
                    tconc( out list( g->name g->stackup outline ) )
                )
            )
        )
        cdr( car( out ) )
    )
)

; One stackup as { "thickness": t, "layers": [ ... ] }.
;
; Every layer carries its own z_top / z_bottom, measured from the TOP OF THE
; CONDUCTOR CORE = 0. That datum is what lets zones of wildly different
; thickness butt together: measured on a real board, FLEX, STIFFENER1 and
; STIFFENER2 are 0.365, 0.49 and 2.44 thick with an identical 0.215 core, and
; a stiffener simply grows outwards from the copper.
;
; A layer also carries its drawn shapes, or null when it has none. That is the
; difference between this and a plain prism per zone: Allegro's own export puts
; 86.763 mm2 at the stiffener height while a zone prism puts 171.761 there,
; because the stiffener is a drawn shape smaller than the zone. Layers with no
; shapes - conductors, the dielectric, the soldermask - do span the whole zone.
; nil for a cross-section entry that is NOT part of the finished board body.
;
; Silkscreen and paste mask are both layerType MASK and both appear in the
; cross section, but neither belongs in the solid:
;   - the legend is exported separately, as its own geometry, from the
;     silkscreen section. Leaving it in the stack would draw it TWICE, and the
;     stack copy would be a sheet covering the whole board rather than the
;     characters actually printed on it.
;   - paste mask is a stencil aperture definition. It is not on the finished
;     board at all.
;
; This is requirement #1 from 2026-07-18 - "dielectrics + planes + conductors +
; soldermask both sides; silkscreen and paste mask excluded" - which
; calculateBoardThickness has always honoured. The per-layer emission did not,
; and on a plain board that put four extra 0.025 sheets into the stack and
; reported 1.204 mm where the board is 1.104. It never showed on the rigid-flex
; test board because those stackups carry no silkscreen or paste layers.
;
; layerFunction is the reliable test (SILKSCREEN / SOLDER_PASTE); the name is
; the fallback for a design that does not set one.
procedure( s3dLayerInBody( o_layer )
    let( ( probe )
        probe = strcat(
            if( o_layer->name then upperCase( o_layer->name ) else "" ) " "
            if( stringp( o_layer->layerFunction ) then
                upperCase( o_layer->layerFunction )
            else
                "" ) )
        ; Short markers on purpose. SILKSCREEN_TOP and PASTEMASK_TOP are the
        ; usual names and layerFunction usually says SILKSCREEN / SOLDER_PASTE,
        ; but a design that names a layer PASTE_TOP and sets no function would
        ; slip through a longer test. Nothing else in a cross section contains
        ; "SILK" or "PASTE" - not coverlay, adhesive, stiffener, soldermask,
        ; conductor or dielectric - so the short form cannot over-match.
        !( s3dContains( probe "SILK" ) || s3dContains( probe "PASTE" ) )
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

procedure( s3dStackupJson( t_name g_stackup )
    let( ( all layers span thk ( total 0.0 ) ( above 0.0 ) ( cum 0.0 ) ( i 0 )
           ( nSkip 0 ) zTop zBot shapes body out ( first t )
           silkTop silkBot allSpan )
        all = nil
        errset( all = axlXSectionGet( g_stackup 'all ) )

        ; Drop what is not part of the body BEFORE anything is measured: the
        ; z walk below closes the remaining layers up against the core, so a
        ; dropped sheet leaves no gap where it used to be.
        ;
        ; But REMEMBER which side carried a silkscreen before dropping it. A
        ; cross section assigns its mask and coating layers per stackup, so a
        ; rigid-flex board says "no silkscreen on the stiffener zones" exactly
        ; by leaving the layer out of those stackups - and dropping the layer
        ; here threw that statement away, after which the legend was printed
        ; over every zone alike. It is not body material and must not be built
        ; as such; it is a fact about the zone, so it travels as one.
        ;
        ; Which side by POSITION, not by name: a layer outside the outermost
        ; conductor on the top side is a top-side layer whatever it is called,
        ; and SILKSCREEN_TOP / SILK_TOP / "Silk Screen Top" all reduce to the
        ; same answer without a list of spellings.
        layers = nil
        silkTop = nil
        silkBot = nil
        allSpan = s3dConductorSpan( all )
        i = 0
        foreach( layer all
            if( s3dLayerInBody( layer ) then
                layers = cons( layer layers )
            else
                when( s3dLayerThk( layer ) > 0.0  nSkip = nSkip + 1 )
                when( s3dContains(
                        strcat( if( layer->name then upperCase( layer->name ) else "" ) " "
                                if( stringp( layer->layerFunction )
                                    then upperCase( layer->layerFunction ) else "" ) )
                        "SILK" )
                    if( allSpan && i > cadr( allSpan ) then
                        silkBot = t
                    else
                        silkTop = t
                    )
                )
            )
            i = i + 1
        )
        layers = reverse( layers )

        span = s3dConductorSpan( layers )
        unless( span  layers = nil )

        ; everything outside the top conductor, so the core top lands on 0
        i = 0
        foreach( layer layers
            when( i < car( span )  above = above + s3dLayerThk( layer ) )
            total = total + s3dLayerThk( layer )
            i = i + 1
        )

        when( nSkip > 0
            printf( "Simple 3D: stackup %s - %d silkscreen/paste layer(s) left out of the body.\n"
                    t_name nSkip )
        )

        ; "silkscreen": which SIDES of this stackup carry a printed legend. A
        ; reader that does not know the key behaves exactly as before - the
        ; legend goes everywhere - so an older Simple 3D still builds this file.
        out = strcat( s3dJsonQuote( t_name ) ": {\n"
                      "\t\"thickness\": " sprintf( nil "%f" total ) ",\n"
                      "\t\"silkscreen\": { \"top\": "
                      if( silkTop then "true" else "false" )
                      ", \"bottom\": "
                      if( silkBot then "true" else "false" ) " },\n"
                      "\t\"layers\": [\n" )

        foreach( layer layers
            thk = s3dLayerThk( layer )
            zTop = above - cum
            zBot = zTop - thk
            cum = cum + thk

            ; The two surface entries have no thickness and no material.
            when( thk > 0.0
                shapes = nil
                when( layer->name
                    shapes = s3dLayerShapesJson( layer->name )
                )
                body = strcat(
                    "{\n"
                    "\t\"name\": " s3dJsonQuote( if( layer->name then layer->name else "" ) ) ",\n"
                    "\t\"type\": " s3dJsonQuote( if( layer->layerType then layer->layerType else "" ) ) ",\n"
                    "\t\"thickness\": " sprintf( nil "%f" thk ) ",\n"
                    "\t\"z_top\": " sprintf( nil "%f" zTop ) ",\n"
                    "\t\"z_bottom\": " sprintf( nil "%f" zBot ) ",\n"
                    "\t\"negative\": " if( s3dLayerIsNegative( layer ) then "true" else "false" ) ",\n"
                    "\t\"function\": " s3dJsonQuote( layer->layerFunction ) ",\n"
                    "\t\"shapes\": " if( shapes then s3dAddIndent( shapes ) else "null" ) "\n"
                    "}"
                )
                unless( first  out = strcat( out ",\n" ) )
                first = nil
                out = strcat( out s3dAddIndent( body 2 ) )
            )
        )
        strcat( out "\n\t]\n}" )
    )
)

; Every stackup the design has, keyed by name. Empty object on a plain board.
procedure( s3dStackupsJson()
    let( ( names out ( first t ) )
        names = nil
        errset( names = axlXSectionGet( nil 'stackups ) )
        if( names then
            out = "\"stackups\": {\n"
            foreach( s names
                when( stringp( s )
                    unless( first  out = strcat( out ",\n" ) )
                    first = nil
                    out = strcat( out s3dAddIndent( s3dStackupJson( s s ) ) )
                )
            )
            strcat( out "\n}" )
        else
            ; An ORDINARY board has no named stackups, but it does have a cross
            ; section, and axlXSectionGet( nil 'all ) returns it. Emitting that
            ; under the name Allegro itself uses for the default - Primary -
            ; lets the reader build a plain board layer by layer too, so "Body
            ; stitching" stops being a setting that silently does nothing on
            ; every board that is not rigid-flex.
            ;
            ; nil is safe as the query ONLY because there are no named stackups
            ; here: on a rigid-flex design nil 'all returns the combined "All
            ; Stackups" view, which is not any real stackup (round 27).
            strcat( "\"stackups\": {\n"
                    s3dAddIndent( s3dStackupJson( "Primary" nil ) )
                    "\n}" )
        )
    )
)

; The zone array: which stackup each zone uses, and its outline. The layer
; geometry lives in "stackups", so a zone is now just an outline plus a
; reference - several zones share one stackup (FLEX1 and FLEX2 here).
procedure( s3dZonesJson()
    let( ( zones contour body out ( first t ) ( n 0 ) )
        zones = s3dZoneList()

        if( zones then
            out = "\"zones\": [\n"
            foreach( z zones
                contour = s3dContourJson( caddr( z ) )
                when( contour
                    n = n + 1
                    unless( first  out = strcat( out ",\n" ) )
                    first = nil
                    body = strcat(
                        "{\n"
                        "\t\"name\": " s3dJsonQuote( car( z ) ) ",\n"
                        "\t\"stackup\": " s3dJsonQuote( cadr( z ) ) ",\n"
                        "\t\"contour\": " s3dAddIndent( contour ) "\n"
                        "}"
                    )
                    out = strcat( out s3dAddIndent( body ) )
                )
            )
            out = strcat( out "\n]" )
            printf( "Simple 3D: %d stackup zone(s) exported.\n" n )
            out
        else
            "\"zones\": []"
        )
    )
)

;=====================================================================
;  Bends
;
;  A bend is not geometry in Allegro. It is a line, an area and a property,
;  and all three are needed to fold anything:
;
;    axlGetBends()                the names
;    axlGetBendInnerRadius(name)  the radius - the only bend parameter with
;                                 an API of its own
;    RIGID FLEX/BEND_LINE         the axis. The documentation is explicit
;                                 that the line "represents the midpoint of
;                                 the bend", so the strip that curls is
;                                 centred on it rather than starting there.
;    RIGID FLEX/BEND_AREA         the extent of that strip. Measured ACROSS
;                                 the line it is the developed length of the
;                                 arc: how much flat material the fold eats.
;                                 Trimmed to the design outline, so it is
;                                 measured rather than derived.
;    IDX_BEND_TYPE_INFO           angle, inner side, order, type.
;
;  That last one is UNDOCUMENTED - it appears in neither the SKILL API index
;  nor the DB attribute reference - so it is emitted RAW and parsed on the
;  Python side. A field spelled differently by another Allegro version can
;  then be handled without a re-export, and the string itself is in the
;  intermediate where it can be read.
;
;  Line and area are associated through their GROUP: "All of the Bend Area
;  objects are also collected together to form a single group. The group name
;  is defined by the Bend Area Name" (Defining a Bend Area). That is also how
;  zones had to be read - a zone outline's ->group is nil - so the group is
;  tried first here too, with a subclass sweep as the fallback.
;=====================================================================

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

; Bend lines swept off their subclass. nil until asked for; only ever asked
; for on a design that HAS bends, so an ordinary board pays no visibility
; churn for a feature it does not use.
S3D_BendLines = nil

procedure( s3dSweepBendLines()
    s3dSelectVisibleOn( list( "RIGID FLEX/BEND_LINE" ) list( "noall" "lines" )
                        "Simple 3D: no %s subclass in this design." )
)

; The members of the group named t_name, or nil.
procedure( s3dGroupNamed( t_name )
    let( ( ( found nil ) )
        errset(
            foreach( g axlDBGetDesign()->groups
                when( g && !found && stringp( g->name ) && (g->name == t_name)
                    found = g->groupMembers
                )
            )
        )
        found
    )
)

; ( lineDbid areaDbid ) for one bend, from its group. Either may be nil.
procedure( s3dBendParts( t_name )
    let( ( ( line nil ) ( area nil ) lay )
        foreach( m s3dGroupNamed( t_name )
            lay = nil
            errset( lay = m->layer )
            when( stringp( lay )
                lay = upperCase( lay )
                when( !line && s3dContains( lay "BEND_LINE" )  line = m )
                when( !area && s3dContains( lay "BEND_AREA" )  area = m )
            )
        )
        list( line area )
    )
)

; The two endpoints of a path, as ( (x y) (x y) ).
;
; A bend line's own ->startEnd is nil - it is a path, not a segment - and the
; endpoints live on its segments. Taking the first segment's start and the
; last one's end also reads a bend line drawn as several collinear pieces.
procedure( s3dPathEnds( o_dbid )
    let( ( segs ( lastSeg nil ) a b )
        segs = nil
        errset( segs = o_dbid->segments )
        when( segs
            foreach( s segs  lastSeg = s )
            a = nil
            b = nil
            errset( a = car( car( segs )->startEnd ) )
            errset( b = cadr( lastSeg->startEnd ) )
            when( a && b  list( a b ) )
        )
    )
)

; t if a point is inside a bBox given as ( (xl yl) (xh yh) ).
procedure( s3dBBoxHas( l_bBox l_pt )
    let( ( lo hi )
        lo = car( l_bBox )
        hi = cadr( l_bBox )
        (xCoord( l_pt ) >= xCoord( lo )) && (xCoord( l_pt ) <= xCoord( hi )) &&
        (yCoord( l_pt ) >= yCoord( lo )) && (yCoord( l_pt ) <= yCoord( hi ))
    )
)

; How wide a shape is measured ACROSS the line a-b. On a bend area that is
; the developed length of the arc, which is the one number that says how much
; flat board the fold consumes - and it is a measurement, not a derivation
; from radius and angle, so it stays right when the two disagree.
procedure( s3dSpanAcross( o_shape l_a l_b )
    let( ( dx dy len nx ny ( lo nil ) ( hi nil ) w )
        dx = xCoord( l_b ) - xCoord( l_a )
        dy = yCoord( l_b ) - yCoord( l_a )
        len = sqrt( dx * dx + dy * dy )
        when( len > 0.0
            nx = dy / len
            ny = - dx / len
            errset(
                foreach( seg o_shape->segments
                    foreach( p seg->startEnd
                        w = nx * (xCoord( p ) - xCoord( l_a )) +
                            ny * (yCoord( p ) - yCoord( l_a ))
                        when( !lo || (w < lo)  lo = w )
                        when( !hi || (w > hi)  hi = w )
                    )
                )
            )
            when( lo && hi  hi - lo )
        )
    )
)

; The bend area whose bBox contains a point. Bend areas "cannot overlap"
; (Defining a Bend Area), so containment picks exactly one.
procedure( s3dBendAreaAt( l_pt )
    let( ( ( found nil ) )
        unless( S3D_RigidFlexShapes  s3dCollectRigidFlexShapes() )
        foreach( s S3D_RigidFlexShapes["BEND_AREA"]
            when( !found && errset( s3dBBoxHas( s->bBox l_pt ) ) &&
                  s3dBBoxHas( s->bBox l_pt )
                found = s
            )
        )
        found
    )
)

; The whole bend array. "bends": [] on any board without them, which is
; every board this tool has exported until now.
procedure( s3dBendsJson()
    let( ( names parts line area ends mid radius width info body out
           ( first t ) ( n 0 ) ( made 0 ) ( swept nil ) ( warned nil ) )
        names = nil
        errset( names = axlGetBends() )

        if( !names then
            "\"bends\": []"
        else
            out = "\"bends\": [\n"
            foreach( b names
                when( stringp( b )
                    n = n + 1
                    parts = s3dBendParts( b )
                    line  = car( parts )
                    area  = cadr( parts )

                    ; Fallback: the group route found no line. Sweep the
                    ; subclass and pair by order, which is only defensible
                    ; because it is announced.
                    unless( line
                        unless( swept
                            S3D_BendLines = s3dSweepBendLines()
                            swept = t
                        )
                        when( length( S3D_BendLines ) == length( names )
                            line = nth( n - 1 S3D_BendLines )
                            unless( warned
                                warned = t
                                s3dWarn( "Simple 3D: bend lines are not in their bend groups; pairing them with the bend names IN ORDER. Check the folded model." )
                            )
                        )
                    )

                    ends = if( line then s3dPathEnds( line ) else nil )
                    if( !ends then
                        s3dWarn( sprintf( nil "Simple 3D: bend %s has no readable bend line; it will not be folded." b ) )
                    else
                        mid = list( (xCoord( car( ends ) ) + xCoord( cadr( ends ) )) / 2.0
                                    (yCoord( car( ends ) ) + yCoord( cadr( ends ) )) / 2.0 )
                        unless( area  area = s3dBendAreaAt( mid ) )

                        radius = nil
                        errset( radius = axlGetBendInnerRadius( b ) )
                        width = if( area then s3dSpanAcross( area car( ends ) cadr( ends ) ) else nil )

                        info = s3dPropValue( line "IDX_BEND_TYPE_INFO" )
                        unless( stringp( info )
                            s3dWarn( sprintf( nil "Simple 3D: bend %s carries no IDX_BEND_TYPE_INFO, so its angle is unknown; it will not be folded." b ) )
                        )

                        body = strcat(
                            "{\n"
                            "\t\"name\": " s3dJsonQuote( b ) ",\n"
                            "\t\"line\": { \"start\": ["
                            sprintf( nil "%f" xCoord( car( ends ) ) ) ", "
                            sprintf( nil "%f" yCoord( car( ends ) ) ) "], \"end\": ["
                            sprintf( nil "%f" xCoord( cadr( ends ) ) ) ", "
                            sprintf( nil "%f" yCoord( cadr( ends ) ) ) "] },\n"
                            "\t\"inner_radius\": "
                            if( radius then sprintf( nil "%f" radius ) else "null" ) ",\n"
                            "\t\"width\": "
                            if( width then sprintf( nil "%f" width ) else "null" ) ",\n"
                            "\t\"info\": " s3dJsonQuote( info ) "\n"
                            "}"
                        )
                        unless( first  out = strcat( out ",\n" ) )
                        first = nil
                        made = made + 1
                        out = strcat( out s3dAddIndent( body ) )
                    )
                )
            )
            printf( "Simple 3D: %d of %d bend(s) exported.\n" made n )
            strcat( out "\n]" )
        )
    )
)

procedure( makePcbContour( dsn )
    let( ( outline segments ( edges 'unbound ) ( cut 'unbound ) ( cuts 'unbound ) element cutouts )
        ; make pcb geometry
        outline = dsn->designOutline
        segments = outline->segments

        foreach( segment segments
            ; parse segment
            element = boardGeometryParseSegment( segment )

            if( boundp( 'edges ) then
                tconc( edges element )
            else
                edges = tconc( nil element )
            )
        )

        ; make cutouts
        cutouts = axlDBGetShapes( "BOARD GEOMETRY/CUTOUT" )

        when( cutouts
            foreach( cutout cutouts
                segments = cutout->segments

                foreach( segment segments
                    ; parse segment
                    element = boardGeometryParseSegment( segment )

                    if( boundp( 'cut ) then
                        tconc( cut element )
                    else
                        cut = tconc( nil element )
                    )
                )

                cut = buildString( car( cut ) ",\n" )
                cut = strcat(
                    "[\n"
                    s3dAddIndent( cut )
                    "\n]"
                )

                if( boundp( 'cuts ) then
                    tconc( cuts cut )
                else
                    cuts = tconc( nil cut )
                )

                cut = 'unbound
            )
        )

        unless( boundp( 'cuts )
            cuts = nil
        )

        ; FIX (simple3d 2026-07-22): cuts was guarded here but edges was not,
        ; so a design whose outline yields no segments faulted on this very
        ; line instead of reporting an empty outline. Same fault class as the
        ; unbound `cuts` at the makePcb call site.
        unless( boundp( 'edges )
            s3dWarn( "Simple 3D: the design outline produced no segments." )
            edges = nil
        )

        ; return
        list( edges cuts )
    )
)

; FIX (simple3d 2026-07-22): takes the SYMBOL dbid, not a refdes string.
;
; It used to take a name and resolve it with axlDBFindByName( 'refdes ... ),
; which returns a component instance, whose ->symbol is then the symbol. Two
; lookups that can each come back empty, for a symbol the caller was already
; holding. Callers now iterate the design, so the dbid is passed straight
; through and refdes is read off it. A string is still accepted, because it
; costs three lines and keeps the old call shape working.
procedure( symbolReturn3DElements( g_symbol )
    let( ( stepPackageMapping refDes dbid sym mappingData stepFileName offset_x offset_y offset_z rotation_x rotation_y rotation_z isMirrored xy angle hole mfrPn zone zoneName ( holes 'unbound ) )

        stepPackageMapping = nil

        if( stringp( g_symbol ) then
            refDes = g_symbol
            dbid = axlDBFindByName( 'refdes refDes )
            sym = dbid->symbol
        else
            sym = g_symbol
            refDes = sym->refdes
            ; A mechanical symbol has no refdes (docs: "nil if no associated
            ; component"). Synthesise a unique, readable JSON key from the symbol
            ; name plus a per-export sequence (CR2032_MECH1, CR2032_MECH2, ...),
            ; so several of them cannot collapse onto one duplicate JSON key -
            ; json.load keeps only the last, which would silently drop the rest.
            unless( stringp( refDes )
                S3D_MechSeq = S3D_MechSeq + 1
                refDes = sprintf( nil "%s_MECH%d"
                                  if( sym->name then sym->name else "MECH" )
                                  S3D_MechSeq )
            )
        )

        ; step package mappingData
        ; Guard the call: an unresolved refdes used to reach axlStepGet(nil nil
        ; nil), which warned opaquely and then dropped the component in silence.
        ; Name it instead. mappingData stays nil -> stepFileName stays nil -> the
        ; when(stepFileName ...) below still skips it, so behaviour is unchanged
        ; apart from the message.
        if( sym then
            mappingData = axlStepGet( nil nil sym )
        else
            printf( "Simple 3D: %s - not found in the design, skipped.\n" refDes )
        )
        stepFileName = mappingData->step_name

        offset_x = mappingData->offset_x
        offset_y = mappingData->offset_y
        offset_z = mappingData->offset_z

        rotation_x = mappingData->rotation_x
        rotation_y = mappingData->rotation_y
        rotation_z = mappingData->rotation_z

        ; MFRPN DISABLED (property attachment unreliable); kept for future.
        ; It lives on the component definition, not the instance:
        ; mfrPn = s3dGetMfrPn( dbid->component )

        ; symbol
        if( sym->isMirrored then
            isMirrored = "true"
        else

            isMirrored = "false"
        )

        xy = sym->xy
        angle = sym->rotation

        ; The zone this part stands in, by its own placement point.
        ; axlZoneAccess is the documented way to ask; its reference says the
        ; return is "xy", which cannot be right for a zone lookup, so the name
        ; is read defensively and stays nil if the answer is not a zone dbid.
        zoneName = nil
        zone = nil
        errset( zone = axlZoneAccess( 'point xy ) )
        when( zone
            errset( zoneName = zone->name )
        )
        unless( stringp( zoneName )  zoneName = nil )

        ; set step package mapping
        when( stepFileName
            stepPackageMapping = strcat(
                "\"" sprintf( nil "%s" refDes ) "\": {\n"
                "\t\"step_mapping\": {\n"
                "\t\t\"step_name\": \"" sprintf( nil "%s" stepFileName ) "\",\n"
                "\t\t\"rotation_x\": " sprintf( nil "%f" rotation_x ) ",\n"
                "\t\t\"rotation_y\": " sprintf( nil "%f" rotation_y ) ",\n"
                "\t\t\"rotation_z\": " sprintf( nil "%f" rotation_z ) ",\n"
                "\t\t\"offset_x\": " sprintf( nil "%f" offset_x ) ",\n"
                "\t\t\"offset_y\": " sprintf( nil "%f" offset_y ) ",\n"
                "\t\t\"offset_z\": " sprintf( nil "%f" offset_z ) "\n"
                "\t},\n"
                ; MFRPN DISABLED (kept for future). The "},\n" above already ends
                ; step_mapping with a comma, so dropping mfr_pn keeps valid JSON:
                ; "\t\"mfr_pn\": " if( mfrPn then
                ;                      strcat( "\"" s3dJsonEscape( mfrPn ) "\"" )
                ;                  else
                ;                      "null" ) ",\n"
                ; Which stackup zone this part stands on. On a rigid-flex board
                ; a part on a 2.44 mm stiffener and one on 0.365 mm flex sit at
                ; very different heights, so the reader needs to know which
                ; surface to place it on. nil on an ordinary board, and the
                ; reader then falls back to the single board surface.
                "\t\"zone\": " if( zoneName then
                                   strcat( "\"" zoneName "\"" )
                               else
                                   "null" ) ",\n"
                "\t\"is_mirrored\": " isMirrored ",\n"
                "\t\"x\": " sprintf( nil "%f" xCoord( xy ) ) ",\n"
                "\t\"y\": " sprintf( nil "%f" yCoord( xy ) ) ",\n"
                "\t\"angle\": " sprintf( nil "%f" angle ) "\n"
                "}"
            )
        )

        stepPackageMapping
    )
)

procedure( symbolReturnPinHoles()
    let( ( symbols sym hole padstack xy element ( holes 'unbound ) )
        symbols = axlDBGetDesign()->symbols

        foreach( sym symbols
            ; export pin holes
            foreach( pin sym->pins
                when( pin->isThrough
                    ; reset hole
                    hole = nil

                    ; retrieve padstack information
                    padstack = axlLoadPadstack( pin->name )

                    ; get position - the DRILL's. It is the pad's only when the
                    ; padstack carries no drill offset; see s3dDrillXY.
                    xy = s3dDrillXY( pin padstack )

                    if( padstack->usage == "Slot" then
                        element = makeSlot( pin padstack )

                        hole = strcat(
                            "[\n"
                                s3dAddIndent( buildString( element ",\n" ) )
                            "\n]"
                        )
                    else
                        ; make a simple drill hole
                        hole = makeCircle( xy padstack->drillDiameter )

                        hole = strcat(
                            "[\n"
                                s3dAddIndent( hole )
                            "\n]"
                        )
                    )

                    when( hole
                        if( boundp( 'holes ) then
                            tconc( holes hole )
                        else
                            holes = tconc( nil hole )
                        )
                    )
                )
            )
        )

        if( boundp( 'holes ) then
            holes = car( holes )
            holes = buildString( holes ",\n" )
        else
            holes = nil
        )

        ; return holes
        holes
    )
)

procedure( makePcb( thicknesses edges cuts color )
    let( ( colorJson )
        ; colorJson, not pcbColor: that is the caller's parameter name, and an
        ; undeclared assignment to it here rebound the caller's variable
        ; (round 75, D2).
        colorJson = strcat(
          "\"color\": {\n"
          "\t\"r\": " sprintf( nil "%f" car( color ) ) ",\n"
          "\t\"g\": " sprintf( nil "%f" cadr( color ) ) ",\n"
          "\t\"b\": " sprintf( nil "%f" caddr( color ) ) "\n"
          "}"
        )
        ; FIX (simple3d 2026-07-22): was  if( boundp( 'cuts ) ...).
        ; cuts is a FORMAL PARAMETER, so it is bound the moment the call
        ; succeeds - boundp is always t here and the else branch below was dead
        ; code. Test the value instead, so a board that really has nothing to
        ; cut takes the no-cuts branch and emits a valid "edges" array. With the
        ; boundp test, nil cuts produced a trailing comma:
        ;     "edges": [ [ ...outline... ],  ]
        ; which is not JSON. See also the call site, which must not evaluate an
        ; unbound cuts in the first place.
        if( cuts then
            edges = strcat(
                "\"pcb\": {\n"
                "\t\"thickness\": {\n"
                "\t\t\"soldermask_top\": " sprintf( nil "%f" car( thicknesses ) ) ",\n"
                "\t\t\"board\": " sprintf( nil "%f" cadr( thicknesses ) ) ",\n"
                "\t\t\"soldermask_bottom\": " sprintf( nil "%f" caddr( thicknesses ) ) "\n"
                "\t},\n"
                s3dAddIndent(
                    colorJson
                )
                ",\n"
                "\t\"edges\": [\n"
                "\t\t[\n"
                s3dAddIndent(
                    buildString( car( edges ) ",\n" ),
                    3
                )
                "\n\t\t],\n"
                s3dAddIndent(
                    buildString( car( cuts ) ",\n" ),
                    2
                )
                "\n\t]\n}"
            )

        else
            ; FIX (simple3d): the original emitted  "thickness": 1.67  as a bare
            ; scalar here (reached on a board with no cutouts and no through
            ; pins, when 'cuts stays unbound), which the reader rejects. Emit
            ; the real thickness object, same as the other branch.
            edges = strcat(
                "\"pcb\": {\n"
                "\t\"thickness\": {\n"
                "\t\t\"soldermask_top\": " sprintf( nil "%f" car( thicknesses ) ) ",\n"
                "\t\t\"board\": " sprintf( nil "%f" cadr( thicknesses ) ) ",\n"
                "\t\t\"soldermask_bottom\": " sprintf( nil "%f" caddr( thicknesses ) ) "\n"
                "\t},\n"
                s3dAddIndent( 
                    colorJson
                )
                ",\n"
                "\t\"edges\": [\n"
                "\t\t[\n"
                s3dAddIndent(
                    buildString( car( edges ) ",\n" ),
                    3
                )
                "\n\t\t]\n\t]\n}"
            )
        )
    )
)

;=====================================================================
;  SILKSCREEN  (NEW - simple3d)
;
;  Exports the silkscreen as filled regions so the Python side can extrude
;  them into thin solids sitting on the board faces.
;
;  The whole "line + width -> filled outline" problem is handed to Allegro:
;  axlPolyFromDB turns any line/cline/shape/rect dbid into o_polygon objects
;  with the width already applied and the requested end caps, and
;  axlText2Lines + axlPolyFromDB(?line2poly t) does the same for text (this is
;  the idiom the axlText2Lines documentation itself recommends). Nothing here
;  offsets or strokes geometry by hand.
;
;  Each polygon is written out in the SAME primitive vocabulary the board
;  outline already uses (segment / arc / circle), so the Python reader needs no
;  new geometry parser - build_contour() handles both.
;
;  VARIANTS: silkscreen is deliberately variant-INDEPENDENT. The bare board is
;  manufactured once for every assembly variant, so the printed legend of a
;  component that is not installed in a given variant is still physically on
;  the board. It is therefore collected once per design, not per variant.
;=====================================================================

; Built-in defaults, used when no config file is found (or it fails to parse).
; Mirrors simple3d_config.json - keep the two in step.
S3D_SilkDefaultTop = list(
    "BOARD GEOMETRY/SILKSCREEN_TOP"
    "PACKAGE GEOMETRY/SILKSCREEN_TOP"
    "REF DES/SILKSCREEN_TOP"
    "COMPONENT VALUE/SILKSCREEN_TOP"
)
S3D_SilkDefaultBottom = list(
    "BOARD GEOMETRY/SILKSCREEN_BOTTOM"
    "PACKAGE GEOMETRY/SILKSCREEN_BOTTOM"
    "REF DES/SILKSCREEN_BOTTOM"
    "COMPONENT VALUE/SILKSCREEN_BOTTOM"
)
; Ink thickness in mm. 25 um is a typical cured screen-printed legend.
S3D_SilkDefaultThickness = 0.025

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

;---------------------------------------------------------------------
;  Silkscreen configuration
;---------------------------------------------------------------------

; Read the config file and return
;   list( l_topLayers l_bottomLayers f_thickness g_clip s_endCap g_export )
; Any missing piece falls back to the built-in default, and a file that cannot
; be read or parsed degrades to all defaults with a message - a broken config
; must never cost the user the whole export.
procedure( s3dSilkConfig( @optional ( t_file nil ) )
    let( ( cfg silk settings top bottom thickness clip endCap doExport )
        top = S3D_SilkDefaultTop
        bottom = S3D_SilkDefaultBottom
        thickness = S3D_SilkDefaultThickness
        clip = t
        endCap = 'ROUND
        doExport = t

        ; The two settings that live in GLOBALS get their defaults back here,
        ; with the locals above and before anything is read - these files load
        ; once per Allegro session, so a global left as the previous export set
        ; it outlives the design that set it (the round-42 trap). Restoring them
        ; further down, inside the branch that parses the file, covered a config
        ; with the key removed but not a board exported with NO config beside it
        ; at all: that one kept the last board's values.
        S3D_ExportFullBoard = t
        S3D_NegativeLayers = S3D_NegativeLayersDefault

        unless( t_file  t_file = "simple3d_config.json" )

        if( isFile( t_file ) then
            ; The tracked defaults with the local file merged over them - see
            ; s3dConfigRead. Reading the base alone would ignore whatever this
            ; installation set for itself.
            cfg = s3dConfigRead( t_file )
            if( cfg then
                printf( "Simple 3D: silkscreen config: %s\n" t_file )
                silk = s3dJsonGet( cfg "silkscreen" )
                settings = s3dJsonGet( cfg "settings" )

                when( s3dJsonList( silk "top" )     top = s3dJsonList( silk "top" ) )
                when( s3dJsonList( silk "bottom" )  bottom = s3dJsonList( silk "bottom" ) )

                when( s3dJsonGet( settings "silkscreenThickness" )
                    thickness = s3dJsonGet( settings "silkscreenThickness" )
                )
                when( s3dJsonHas( settings "clipToBoardOutline" )
                    clip = s3dJsonGet( settings "clipToBoardOutline" )
                )
                when( s3dJsonHas( settings "exportSilkscreen" )
                    doExport = s3dJsonGet( settings "exportSilkscreen" )
                )

                ; Which stackup layers are drawn as openings. Read here rather
                ; than left hardcoded because it is fabricator/site convention,
                ; not something the database states: negativeArtwork reads nil
                ; on every layer even where the polarity is unambiguous.
                ; Its default is restored at the top of this procedure, with
                ; S3D_ExportFullBoard's - see the note there.
                when( s3dJsonList( settings "negativeLayers" )
                    S3D_NegativeLayers = s3dJsonList( settings "negativeLayers" )
                    printf( "Simple 3D: negative (opening) layers: %L\n"
                            S3D_NegativeLayers )
                )

                ; Default restored at the top of this procedure, every time -
                ; see the note there.
                when( s3dJsonHas( settings "exportFullBoard" )
                    S3D_ExportFullBoard = s3dJsonGet( settings "exportFullBoard" )
                )
                when( stringp( s3dJsonGet( settings "endCapType" ) )
                    ; only the three Allegro end-cap keywords are accepted; a
                    ; typo silently becoming 'SQUARE would be hard to notice.
                    case( upperCase( s3dJsonGet( settings "endCapType" ) )
                        ( "ROUND"    endCap = 'ROUND )
                        ( "SQUARE"   endCap = 'SQUARE )
                        ( "OCTAGON"  endCap = 'OCTAGON )
                        ( t
                            s3dWarn( sprintf( nil "Simple 3D: unknown endCapType %L in %s; using ROUND."
                                              s3dJsonGet( settings "endCapType" ) t_file ) )
                        )
                    )
                )
            else
                s3dWarn( sprintf( nil "Simple 3D: could not parse %s; using built-in silkscreen defaults."
                                  t_file ) )
            )
        else
            printf( "Simple 3D: no silkscreen config at %s; using built-in defaults.\n" t_file )
        )
        list( top bottom thickness clip endCap doExport )
    )
)

;---------------------------------------------------------------------
;  Polygon -> JSON vertices
;
;  The polygon boundary goes into the JSON as Allegro's own vertex list -
;  (x, y, signed_radius) per point - and the arcs are rebuilt on the Python
;  side. It used to be rebuilt here, into segment/arc primitives; that put the
;  one genuinely ambiguous decision in the file format, where nothing could
;  check it. See PROJECT_NOTES round 10b: the doc sentence describing the sign
;  of the radius admits two readings, and an arc built on the wrong side of its
;  chord still closes, so the mistake is invisible until someone measures area.
;
;  Python can measure area - every polygon carries Allegro's own poly->area -
;  so it resolves the reading itself, per board, and says which one won. This
;  side therefore reports what the database holds and decides nothing.
;---------------------------------------------------------------------

; Write one vertex list as  [x, y, radius]  rows, indented x_indent tabs.
procedure( s3dWriteVertexList( p_port l_vertices x_indent )
    let( ( pad ( isFirst t ) xy rad )
        pad = ""
        for( i 1 x_indent
            pad = strcat( pad "	" )
        )
        foreach( vertex l_vertices
            if( isFirst then
                isFirst = nil
            else
                fprintf( p_port ",\n" )
            )
            xy = car( vertex )
            rad = cadr( vertex )
            unless( rad  rad = 0.0 )
            fprintf( p_port "%s[%f, %f, %f]" pad xCoord( xy ) yCoord( xy ) rad )
        )
    )
)

;---------------------------------------------------------------------
;  Collecting the silkscreen
;---------------------------------------------------------------------

; Every dbid on a silkscreen layer -> filled polygons.
;
; Text is the only special case. Allegro draws text as strokes, so a text dbid
; is vectorised with axlText2Lines and each resulting r_path is widened into a
; polygon with ?line2poly (verbatim the idiom in the axlText2Lines docs).
; True-type text has no text block and is converted directly instead - that is
; how exportJson tells the two apart as well.
; Messages about objects that were found but could not be exported. Collected
; while sweeping and carried into the JSON so the Python side can show them too
; - the Allegro console scrolls away, the GUI log does not, and it colors a
; line beginning with "warning" orange.
;
; A module-level accumulator rather than a return value: the collector already
; returns layer groups, and threading a second channel through it and through
; the clipper would obscure both for the sake of a message.
S3D_SilkWarnings = nil

; t if this object has no plotted width, and so would vanish in the artwork.
;
; A zero-width line or a text block with zero pen width is a design mistake -
; Allegro's own plot has nothing to draw with either - but axlPolyFromDB does
; not object: it returns nil, or a degenerate polygon that fails later with a
; message about geometry rather than about width. Catching it here lets the
; report name the layer and the place.
;
; Shapes are filled areas with no width to speak of, and true-type text is a
; filled outline with no pen, so neither can be zero-width.
procedure( s3dZeroWidth( o_dbid )
    let( ( w tb ( allZero nil ) segments )
        cond(
            ( o_dbid->objType == "text"
                tb = nil
                when( o_dbid->textBlock
                    errset( tb = axlGetParam( strcat( "paramTextBlock:" o_dbid->textBlock ) ) )
                )
                when( tb
                    w = tb->photoWidth
                    w && (abs( w ) < 1.0e-9)
                )
            )
            ( o_dbid->objType == "shape"  nil )
            ( t
                w = nil
                errset( w = o_dbid->width )
                if( w then
                    abs( w ) < 1.0e-9
                else
                    ; A path can carry its width per segment instead. Only
                    ; call it zero when there ARE segments and every one of
                    ; them is zero - with nothing to look at, say nothing.
                    segments = nil
                    errset( segments = o_dbid->segments )
                    when( segments
                        allZero = t
                        foreach( seg segments
                            when( seg->width && (abs( seg->width ) > 1.0e-9)
                                allZero = nil
                            )
                        )
                        allZero
                    )
                )
            )
        )
    )
)

; "text on REF DES/SILKSCREEN_TOP at (12.500, 4.000)" - enough to find it.
procedure( s3dDescribeObject( o_dbid t_layer )
    let( ( box corner )
        box = nil
        errset( box = o_dbid->bBox )
        corner = when( box  car( box ) )
        if( corner then
            sprintf( nil "%s on %s at (%.3f, %.3f)"
                     o_dbid->objType t_layer xCoord( corner ) yCoord( corner ) )
        else
            sprintf( nil "%s on %s" o_dbid->objType t_layer )
        )
    )
)

; A multi-segment path is converted ONE SEGMENT AT A TIME, and that is the
; whole point rather than an optimisation.
;
; axlPolyFromDB on a whole line/cline MITRES the joins between its segments: on
; a real board, a 0.15 wide line turning a right angle came back with a square
; outer corner whose diagonal offset was exactly 0.075*sqrt(2) - a textbook
; mitre - where the artwork has a round join, because a plot sweeps a round
; aperture along the path. The 3D model then showed sharp corners on some turns
; while others (junctions of two separate lines, where the round END CAPS
; overlap) came out round, which is exactly the inconsistency reported.
;
; Converting each segment separately gives each one round caps, and the union of
; those overlapping stadiums IS a round join. The documentation says the same
; thing from the other direction: of ?line2poly it notes "typically one poly is
; returned for each segment in the r_path" - which is why text, which goes
; through that path, never had the problem.
;
; They are deliberately NOT merged here. The Python side draws a compound of
; overlapping solids anyway, and when clipping is on axlPolyOperation unions
; them as a side effect of the AND.
procedure( s3dPolysFromDbid( o_dbid s_endCap )
    let( ( polys lines flat segments )
        polys = nil
        cond(
            ( o_dbid->objType == "text"
                ; Allegro draws text as strokes, so a text dbid is vectorised
                ; with axlText2Lines and each r_path widened with ?line2poly -
                ; verbatim the idiom in the axlText2Lines docs. True-type text
                ; has no text block and converts directly instead; that is how
                ; exportJson tells the two apart as well.
                if( o_dbid->textBlock then
                    errset( lines = axlText2Lines( o_dbid ) )
                    when( lines
                        flat = foreach( mapcan x lines x )
                        foreach( path flat
                            errset(
                                polys = append( polys
                                    axlPolyFromDB( path ?endCapType s_endCap ?line2poly t ) )
                            )
                        )
                    )
                    ; A font that does not vectorise still has an outline form.
                    unless( polys
                        errset( polys = axlPolyFromDB( o_dbid ?endCapType s_endCap ) )
                    )
                else
                    errset( polys = axlPolyFromDB( o_dbid ?endCapType s_endCap ) )
                )
            )
            ( o_dbid->objType == "path"
                segments = nil
                errset( segments = o_dbid->segments )
                foreach( segment segments
                    errset(
                        polys = append( polys
                            axlPolyFromDB( segment ?endCapType s_endCap ) )
                    )
                )
                ; A segment that will not convert on its own drops a piece of
                ; the line silently, and the area check downstream cannot see a
                ; missing stroke - each surviving polygon is still consistent
                ; with its own area. So say it here. One segment may yield more
                ; than one polygon, hence "fewer than".
                when( segments && (length( polys ) < length( segments ))
                    s3dWarn( sprintf( nil "Simple 3D: a silkscreen line has %d segment(s) but produced only %d polygon(s)."
                                      length( segments ) length( polys ) ) )
                )
                ; Single-segment paths, or a path whose segments will not
                ; convert on their own, still have to come out somehow.
                unless( polys
                    errset( polys = axlPolyFromDB( o_dbid ?endCapType s_endCap ) )
                )
            )
            ( t
                ; shapes, rects, filled areas: a boundary already, nothing to
                ; sweep, so convert whole.
                errset( polys = axlPolyFromDB( o_dbid ?endCapType s_endCap ) )
            )
        )
        polys
    )
)

; All silkscreen polygons on the given layers, GROUPED BY LAYER.
;
; Grouping is what lets the GUI offer the layers as checkboxes: the exporter
; collects every layer the config lists, and which of them actually reach the
; model is then chosen per build, with no re-export. The config answers "what
; exists", the checkboxes answer "what to draw".
;
; One sweep covers both component legends and free board geometry: with the
; silkscreen layers as the only visible ones, axlAddSelectAll returns the
; figures owned by symbols as well as the loose ones (which is why exportJson
; has to filter on elem->parent->refdes - here both are wanted).
;
; The sweep is s3dSelectVisibleOn, which puts the visibility and find-filter
; state back before the conversion below starts.
procedure( s3dCollectSilkByLayer( l_layers s_endCap )
    let( ( elems polys out key groups order zero message ( nBad 0 ) )
        out = nil
        groups = makeTable( "s3dSilkGroups" nil )
        order = tconc( nil nil )
        when( l_layers
            elems = s3dSelectVisibleOn( l_layers list( "noall" "lines" "shapes" "text" )
                                        "Simple 3D: no such layer: %s" )

            foreach( elem elems
                ; Bucket by the SOURCE object's layer, before conversion: a
                ; polygon has no layer of its own, and text loses even the dbid
                ; once axlText2Lines has vectorised it. Still one sweep per
                ; side - sweeping once per layer would multiply the visibility
                ; churn for nothing.
                key = nil
                errset( key = elem->layer )
                unless( stringp( key )  key = sprintf( nil "%L" key ) )

                ; Zero-width objects are reported and skipped rather than fed
                ; to the converter, which would either drop them silently or
                ; fail later with a message about geometry instead of width.
                zero = nil
                errset( zero = s3dZeroWidth( elem ) )
                when( zero
                    message = strcat( "zero width: " s3dDescribeObject( elem key )
                                      " - skipped, it cannot be plotted" )
                    s3dWarn( sprintf( nil "Simple 3D: %s." message ) )
                    S3D_SilkWarnings = cons( message S3D_SilkWarnings )
                )

                ; Per element, so one object the converter cannot handle costs
                ; that object and not the whole side. Before this, a single
                ; failure anywhere in the sweep propagated out of
                ; s3dMakeSilkscreen, was swallowed by the errset at the call
                ; site, and the export finished with no silkscreen at all and
                ; nothing on screen to say why.
                polys = nil
                unless( zero || errset( polys = s3dPolysFromDbid( elem s_endCap ) )
                    nBad = nBad + 1
                    when( nBad == 1
                        s3dWarn( sprintf( nil "Simple 3D: a %s object on %s could not be converted; skipping it (further ones are counted only)."
                                          elem->objType key ) )
                    )
                )
                foreach( poly polys
                    when( poly && !poly->isHole
                        unless( groups[key]
                            groups[key] = tconc( nil nil )
                            tconc( order key )
                        )
                        tconc( groups[key] poly )
                    )
                )
            )
        )

        when( nBad > 0
            s3dWarn( sprintf( nil "Simple 3D: %d silkscreen object(s) could not be converted and were skipped." nBad ) )
        )

        ; -> ( (layer polys) (layer polys) ... ), layers in the order Allegro
        ; first mentioned them, which keeps the GUI's list stable between runs.
        out = tconc( nil nil )
        foreach( key cdr( car( order ) )
            tconc( out list( key cdr( car( groups[key] ) ) ) )
        )
        cdr( car( out ) )
    )
)

; Total polygon count across a side's groups, for the console summary.
procedure( s3dGroupCount( l_groups )
    let( ( ( n 0 ) )
        foreach( group l_groups
            n = n + length( cadr( group ) )
        )
        n
    )
)

;---------------------------------------------------------------------
;  Clipping to the board
;---------------------------------------------------------------------

; The board area as polygons: the design outline minus every cutout - the same
; two sources makePcbContour() uses for the solid, so the silkscreen is clipped
; to exactly the material that exists.
procedure( s3dBoardPoly()
    let( ( dsn outline polys cutouts cutPolys res )
        dsn = axlDBGetDesign()
        outline = dsn->designOutline
        if( outline then
            errset( polys = axlPolyFromDB( outline ) )
            if( polys then
                cutPolys = nil
                cutouts = axlDBGetShapes( "BOARD GEOMETRY/CUTOUT" )
                foreach( cutout cutouts
                    errset( cutPolys = append( cutPolys axlPolyFromDB( cutout ) ) )
                )
                when( cutPolys
                    res = nil
                    errset( res = axlPolyOperation( polys cutPolys 'ANDNOT ) )
                    if( res then
                        polys = remd( nil res )
                    else
                        s3dWarn( "Simple 3D: could not subtract cutouts from the board outline; silkscreen is clipped to the outline only." )
                    )
                )
                polys
            else
                s3dWarn( "Simple 3D: could not convert the design outline to a polygon; silkscreen will not be clipped." )
                nil
            )
        else
            s3dWarn( "Simple 3D: no design outline; silkscreen will not be clipped." )
            nil
        )
    )
)

; t if bounding box l_inner lies entirely within l_outer.
procedure( s3dBBoxInside( l_inner l_outer )
    let( ( ( eps 1.0e-9 ) )
        when( l_inner && l_outer
            (xCoord( car( l_inner ) ) >= xCoord( car( l_outer ) ) - eps) &&
            (yCoord( car( l_inner ) ) >= yCoord( car( l_outer ) ) - eps) &&
            (xCoord( cadr( l_inner ) ) <= xCoord( cadr( l_outer ) ) + eps) &&
            (yCoord( cadr( l_inner ) ) <= yCoord( cadr( l_outer ) ) + eps)
        )
    )
)

; One batch through axlPolyOperation. That API is documented as best-effort
; ("provided as-is ... may fail", returns nil on failure), so a failed batch
; keeps its geometry unclipped and says so, rather than dropping legend that
; is almost certainly on the board anyway.
procedure( s3dClipChunk( l_chunk l_board )
    let( ( res )
        res = nil
        errset( res = axlPolyOperation( l_chunk l_board 'AND ) )
        if( res then
            remd( nil res )
        else
            s3dWarn( sprintf( nil "Simple 3D: silkscreen clip failed for %d polygon(s); kept unclipped."
                              length( l_chunk ) ) )
            l_chunk
        )
    )
)

; Clip silkscreen polygons to the board area.
;
; Two things keep this affordable. Polygons whose bounding box is inside the
; board's are passed through untouched when the board is a plain rectangle with
; no cutouts (the common case, and then correct by construction). The rest go
; through axlPolyOperation in batches: its documentation warns about time and
; memory beyond ~10000 polygons, and batching also contains a failure to the
; batch it happened in.
procedure( s3dClipPolys( l_polys l_board )
    let( ( ( batchSize 400 ) out batch ( n 0 ) fast boardBBox ( inside 0 ) )
        if( !l_board || !l_polys then
            l_polys
        else
            out = tconc( nil nil )
            batch = nil
            fast = (length( l_board ) == 1) && car( l_board )->isRect &&
                   !car( l_board )->holes
            when( fast  boardBBox = car( l_board )->bBox )

            foreach( poly l_polys
                if( fast && s3dBBoxInside( poly->bBox boardBBox ) then
                    inside = inside + 1
                    tconc( out poly )
                else
                    batch = cons( poly batch )
                    n = n + 1
                    when( n >= batchSize
                        foreach( clipped s3dClipChunk( batch l_board )
                            tconc( out clipped )
                        )
                        batch = nil
                        n = 0
                    )
                )
            )
            when( batch
                foreach( clipped s3dClipChunk( batch l_board )
                    tconc( out clipped )
                )
            )
            when( fast
                printf( "Simple 3D: %d silkscreen polygon(s) were wholly inside the board outline (clip skipped).\n"
                        inside )
            )
            cdr( car( out ) )
        )
    )
)

;---------------------------------------------------------------------
;  Top level
;---------------------------------------------------------------------

; Clip each layer's polygons separately.
;
; Clipping a whole side at once would be marginally cheaper, but axlPolyOperation
; unions overlapping polygons, so polygons from different layers would come back
; merged into single regions with no layer left to speak of. Groups that clip to
; nothing are dropped, so a layer that lies entirely off the board does not
; appear in the GUI as an empty choice.
procedure( s3dClipGroups( l_groups l_board )
    let( ( out clipped )
        out = tconc( nil nil )
        foreach( group l_groups
            clipped = s3dClipPolys( cadr( group ) l_board )
            when( clipped
                tconc( out list( car( group ) clipped ) )
            )
        )
        cdr( car( out ) )
    )
)

; Collect the whole silkscreen once for the design.
; -> list( f_thickness l_topPolys l_bottomPolys )  or nil if disabled/empty.
procedure( s3dMakeSilkscreen( l_config )
    let( ( top bottom thickness clip endCap doExport topPolys botPolys board )
        top = nth( 0 l_config )
        bottom = nth( 1 l_config )
        thickness = nth( 2 l_config )
        clip = nth( 3 l_config )
        endCap = nth( 4 l_config )
        doExport = nth( 5 l_config )

        when( doExport
            printf( "Simple 3D: collecting silkscreen...\n" )
            ; Cleared per export, not per side, so both sides report together.
            S3D_SilkWarnings = nil
            ; Both sides come back as ( (layer polys) ... ), so everything from
            ; here on works in groups: s3dGroupCount to count across them and
            ; s3dClipGroups to clip each layer on its own.
            topPolys = s3dCollectSilkByLayer( top endCap )
            botPolys = s3dCollectSilkByLayer( bottom endCap )
            printf( "Simple 3D: silkscreen polygons - top %d, bottom %d\n"
                    s3dGroupCount( topPolys ) s3dGroupCount( botPolys ) )
            foreach( group append( topPolys botPolys )
                printf( "Simple 3D:   %s - %d polygon(s)\n"
                        car( group ) length( cadr( group ) ) )
            )

            when( clip && (topPolys || botPolys)
                board = s3dBoardPoly()
                when( board
                    printf( "Simple 3D: clipping silkscreen to the board outline...\n" )
                    topPolys = s3dClipGroups( topPolys board )
                    botPolys = s3dClipGroups( botPolys board )
                    printf( "Simple 3D: after clipping - top %d, bottom %d\n"
                            s3dGroupCount( topPolys ) s3dGroupCount( botPolys ) )
                )
            )

            when( S3D_SilkWarnings
                s3dWarn( sprintf( nil "Simple 3D: %d silkscreen object(s) were skipped; see the warnings above and the GUI log."
                                  length( S3D_SilkWarnings ) ) )
            )

            when( topPolys || botPolys
                list( thickness topPolys botPolys reverse( S3D_SilkWarnings ) )
            )
        )
    )
)

; Stream one side's polygons into the open file.
;
; Streamed rather than accumulated into one string: a dense board's legend runs
; to tens of thousands of primitives, and building that with repeated strcat is
; quadratic and hits the same "insufficient memory" wall the component section
; already has a note about.
procedure( s3dWriteSilkPolys( p_port l_groups )
    let( ( ( firstPoly t ) holes ( firstHole t ) area layer )
        foreach( group l_groups
        layer = car( group )
        foreach( poly cadr( group )
            if( firstPoly then
                firstPoly = nil
            else
                fprintf( p_port ",\n" )
            )
            fprintf( p_port "\t\t\t{\n" )

            ; Which layer this polygon came from. The array stays FLAT - one
            ; object per polygon, exactly as before - so a reader that ignores
            ; this key still builds the whole legend.
            fprintf( p_port "\t\t\t\t\"layer\": \"%s\",\n" layer )

            ; Allegro's own area for this polygon, already net of its holes.
            ; This is the reference the Python side resolves the arc convention
            ; against and then verifies every polygon by, so it is not optional
            ; bookkeeping - without it the reconstruction has nothing to check
            ; itself against. Costs one float per polygon.
            area = nil
            errset( area = poly->area )
            when( area
                fprintf( p_port "\t\t\t\t\"area\": %f,\n" area )
            )

            fprintf( p_port "\t\t\t\t\"vertices\": [\n" )
            s3dWriteVertexList( p_port poly->vertices 5 )
            fprintf( p_port "\n\t\t\t\t]" )

            holes = poly->holes
            when( holes
                fprintf( p_port ",\n\t\t\t\t\"holes\": [\n" )
                firstHole = t
                foreach( hole holes
                    if( firstHole then
                        firstHole = nil
                    else
                        fprintf( p_port ",\n" )
                    )
                    fprintf( p_port "\t\t\t\t\t[\n" )
                    s3dWriteVertexList( p_port hole->vertices 6 )
                    fprintf( p_port "\n\t\t\t\t\t]" )
                )
                fprintf( p_port "\n\t\t\t\t]" )
            )
            fprintf( p_port "\n\t\t\t}" )
        )
        )
    )
)

; The whole "silkscreen" object, written straight to the open file.
procedure( s3dWriteSilkscreen( p_port l_silk )
    let( ( thickness topPolys botPolys warnings ( firstWarn t ) )
        thickness = nth( 0 l_silk )
        topPolys = nth( 1 l_silk )
        botPolys = nth( 2 l_silk )
        warnings = nth( 3 l_silk )

        fprintf( p_port "\t\"silkscreen\": {\n" )
        fprintf( p_port "\t\t\"thickness\": %f,\n" thickness )

        ; What was found and could not be exported. Carried across so the GUI
        ; can repeat it: the Allegro console has scrolled past by the time
        ; anyone looks at the model.
        when( warnings
            fprintf( p_port "\t\t\"warnings\": [\n" )
            foreach( message warnings
                if( firstWarn then
                    firstWarn = nil
                else
                    fprintf( p_port ",\n" )
                )
                fprintf( p_port "\t\t\t\"%s\"" message )
            )
            fprintf( p_port "\n\t\t],\n" )
        )
        fprintf( p_port "\t\t\"top\": [\n" )
        s3dWriteSilkPolys( p_port topPolys )
        fprintf( p_port "\n\t\t],\n" )
        fprintf( p_port "\t\t\"bottom\": [\n" )
        s3dWriteSilkPolys( p_port botPolys )
        fprintf( p_port "\n\t\t]\n" )
        fprintf( p_port "\t}\n" )
    )
)

; g_fullBoard: this file is the WHOLE board with variants ignored, and says so
; in the JSON. An explicit argument rather than a global, because a global read
; at write time is the round-42 shape - it would describe whatever the previous
; call set if this one ever forgot to.
procedure( create3dIntermediateFormat( thicknesses edgeCuts pcbColor symbols variantName fileName @optional ( silk nil ) ( g_fullBoard nil ) )
    let( ( ( stepModelPlacements 'unbound ) ( edges 'unbound ) ( cut 'unbound ) ( cuts 'unbound ) baseCut body
           placement name pcb outFile outPort lines )   ; the last six: declared here, not in the caller (round 75, D2)
        ; Number each variant's no-refdes mechanicals from 1 (see symbolReturn3DElements).
        S3D_MechSeq = 0
        ; Rebuilt per export: a shape added between two runs in one session
        ; must be picked up, and it is one query.
        S3D_RigidFlexShapes = nil

        ; reset base board contour
        when( car( edgeCuts )
            edges = car( edgeCuts )
        )

        ; The cutouts are collected ONCE, by makePcbContour, and the SAME list
        ; is handed to every export of this run - one per variant, plus the
        ; whole-board file. So it has to be COPIED here, not aliased.
        ;
        ; FIX (simple3d 2026-08-11): was  cuts = cadr( edgeCuts ), an alias.
        ; The tconc below appends IN PLACE, so each export's pin holes stayed
        ; in the caller's list and the next file got them a second time. The
        ; first file written was correct and every one after it carried one
        ; more copy of every through-hole - with one variant, that is the
        ; whole-board file; with two, the second variant already. A duplicated
        ; cutout is not cosmetic: two coincident prisms make OCC's boolean
        ; return an empty result, and the board body disappears from the STEP
        ; with no error anywhere. Found on 8231-a2, whose two slot holes came
        ; out twice.
        when( cadr( edgeCuts )
            foreach( baseCut car( cadr( edgeCuts ) )
                if( boundp( 'cuts ) then
                    tconc( cuts baseCut )
                else
                    cuts = tconc( nil baseCut )
                )
            )
        )

        ; export step package mapping information
        foreach( symbol symbols
            placement = symbolReturn3DElements( symbol )

            when( placement
                if( boundp( 'stepModelPlacements ) then
                    tconc( stepModelPlacements placement )
                else
                    stepModelPlacements = tconc( nil placement )
                )
            )
        )

        ; export symbol pin holes
        cut = symbolReturnPinHoles()
        when( cut
            if( boundp( 'cuts ) then
                tconc( cuts cut )
            else
                cuts = tconc( nil cut )
            )
        )

        ; add name + a format marker so the Python side can tell a Simple 3D
        ; intermediate from any other .json that happens to sit in the folder.
        ; Files without "format": "simple3d" are ignored by the GUI.
        ; NOTE: no embedded \t here - the line writer below prefixes every line
        ; with one tab, so embedding another would double-indent these keys
        ; (still valid JSON, but inconsistent with the rest of the file).
        ; format_version 2 added the optional "silkscreen" object; 3 tags every
        ; silkscreen polygon with the layer it came from, so the layers can be
        ; switched on and off when the model is built instead of at export
        ; time; 4 adds the optional "embedded_models" list; 5 adds "zones" plus
        ; a per-component "zone", for multi-stackup and rigid-flex boards; 6
        ; gives every stackup layer its own extent and shapes; 7 adds "bends";
        ; 8 gives every stackup a "silkscreen" object saying which of its sides
        ; is printed on, which is how a zone says it carries no legend.
        ; All of them are optional to a reader - an older file simply has no
        ; layers to choose from, nothing to say about embedded models, an empty
        ; zone list, which means "ordinary single-stackup board", and no bends,
        ; which means a board that is exported flat.
        ;
        ; NOTE: every top-level key added here must also be listed in the RESERVED
        ; tuple of stepbuilder/intermediate.py, or the reader walks it as if it
        ; were a component.
        name = strcat(
            "\"format\": \"simple3d\",\n"
            "\"format_version\": 8,\n"
            "\"name\": \"" variantName "\",\n"
            ; Optional, and only ever true: the whole board, variants ignored.
            ; A reader that does not know the key sees an ordinary intermediate,
            ; which is what every version before this one will do.
            if( g_fullBoard then "\"full_board\": true,\n" else "" )
            s3dEmbeddedModelsJson() ",\n"
            s3dStackupsJson() ",\n"
            s3dZonesJson() ",\n"
            s3dBendsJson()
        )

        ; make pcb (including all cutouts and holes)
        ;
        ; FIX (simple3d 2026-07-22): "*Error* eval: unbound variable - cuts",
        ; and no JSON written at all, on a board with NO cutouts and NO
        ; through-hole pins. Both `when`s above then leave `cuts` holding the
        ; 'unbound marker, and passing it here evaluates it. An all-SMD board
        ; without a CUTOUT shape is perfectly ordinary; it just had not been
        ; exported before. Same for `edges` if a design somehow has no outline
        ; segments - nil reaches the Python reader, which says "pcb.edges is
        ; empty" instead of dying in SKILL.
        pcb = makePcb( thicknesses
                       if( boundp( 'edges ) then edges else nil )
                       if( boundp( 'cuts ) then cuts else nil )
                       pcbColor )

        ; write step model placement informations
        ; FIX (simple3d): guard the unbound case. If no component has a STEP
        ; mapping, stepModelPlacements is still the 'unbound marker and car()
        ; on it faults. That used to be an odd corner; with silkscreen a bare
        ; board is a legitimate thing to export, so it has to work.
        if( boundp( 'stepModelPlacements ) then
            stepModelPlacements = buildString( car( stepModelPlacements ) ",\n" )
        else
            stepModelPlacements = nil
        )

        ; write to file
        outFile = fileName
        printf( "Simple 3D: writing -> %s\n" outFile )
        outPort = outfile( outFile )

        ; FIX (simple3d): outfile returns nil if the path could not be opened
        ; (missing folder, permissions, etc). Without this guard the following
        ; fprintf's silently do nothing and the caller still prints
        ; "Export complete!", leaving an empty/absent .json that the GUI then
        ; cannot find. Fail loudly instead.
        unless( outPort
            error( "Simple 3D: outfile() returned nil for: %s\n(check the folder exists and the path/permissions)\n" outFile )
        )

        ; to prevent fprintf insufficient memory error
        body = strcat( name ",\n" pcb )
        when( stepModelPlacements
            body = strcat( body ",\n" stepModelPlacements )
        )
        ; the silkscreen object follows, so the last line needs its comma
        when( silk
            body = strcat( body "," )
        )
        lines = parseString( body "\n" )

        fprintf( outPort "{\n")

        foreach( line lines
            fprintf( outPort strcat( "\t" line ) )
            fprintf( outPort "\n" )
        )

        ; Streamed straight to the port instead of being folded into the string
        ; above - see s3dWriteSilkPolys for why.
        when( silk
            s3dWriteSilkscreen( outPort silk )
        )

        fprintf( outPort "}\n")

        close( outPort )

        ; confirm the file actually landed on disk
        if( isFile( outFile ) then
            printf( "Simple 3D: wrote %s\n" outFile )
        else
            error( "Simple 3D: file was NOT created after close: %s\n" outFile )
        )

        t
    )
)

procedure( makeVariant3dIntermediates( dir, @optional ( pcbColor list( 0.0 0.4 0.0) ) ( configFile nil ) )
    let( (  ( variantFile s3dVariantFilePath() ) dsnName dsn thicknesses edgeCuts silk variantInformation variantSymbolList alternateParts variant variantCount symbols variantName fileName )
        ; The list used to go on: a second `thicknesses`, and `elements placement
        ; outFile outPort pcb lines` - names this procedure never touches. They
        ; were create3dIntermediateFormat's, reaching its let through SKILL's
        ; dynamic scope; since round 75 (D2) it declares them itself.

        ; get design and design name
        dsnName = axlCurrentDesign()
        dsn = axlDBGetDesign()

        ; Both of these are per-DESIGN caches, and the SKILL files are loaded
        ; once per Allegro session - so without this they survive from one
        ; board to the next and the second export gets the FIRST board's
        ; shapes and bend lines, as dbids belonging to a database that may not
        ; even be open any more. Nothing says so: the JSON simply describes the
        ; wrong board. S3D_MechSeq and S3D_SilkWarnings are already reset the
        ; same way, one level down; these two were missed.
        S3D_RigidFlexShapes = nil
        S3D_BendLines = nil

        ; create dir (recursively - createDir makes only one level at a time,
        ; so walk the path and create each missing segment).
        s3dMakeDirs( dir )

        ; calculate pcb thickness
        thicknesses = calculateBoardThickness()

        ; make pcb contour
        edgeCuts = makePcbContour( dsn )

        ; Collect the silkscreen ONCE, outside the variant loop. The bare board
        ; is manufactured once and serves every assembly variant, so its printed
        ; legend does not change when a component is not installed - the legend
        ; of a DNP part is still physically on the board. Every variant JSON
        ; therefore carries the same silkscreen (and, like edgeCuts, it costs
        ; one collection pass no matter how many variants there are).
        ; errset with a second argument PRINTS the SKILL error before
        ; returning nil, and errset itself returns nil only on failure. The
        ; bare errset this replaces hid every silkscreen fault behind an empty
        ; legend: the export finished, the JSON had no "silkscreen" key, and
        ; the console said nothing at all. A swallowed error is worse than a
        ; loud one - the board still exports either way.
        silk = nil
        unless( errset( silk = s3dMakeSilkscreen( s3dSilkConfig( configFile ) ) t )
            s3dErr( "Simple 3D: silkscreen collection failed (message above)." )
            s3dErr( "Simple 3D: the board and its components are still exported; only the legend is missing." )
            silk = nil
        )

        if( isFile( variantFile ) then
            ; Read / parse variant list
            variantInformation = gdsysGetVariantInfo()

            if( variantInformation then
                variantSymbolList = car( variantInformation )
                alternateParts = cadr( variantInformation )

                ; FIX (simple3d): variantSymbolList is a table (from makeTable),
                ; not a list - it is always truthy and length() does not apply,
                ; so count its keys by iterating. If a Variants.lst is present
                ; but yields zero variants for THIS board, the foreach below
                ; runs zero times, no JSON is written, yet "Export complete!"
                ; still prints. That usually means the Variants.lst in the
                ; working folder belongs to a DIFFERENT project. Surface it.
                variantCount = 0
                foreach( variant variantSymbolList
                    variantCount = variantCount + 1
                )
                printf( "Simple 3D: %d variant(s) parsed from %s\n"
                        variantCount variantFile )
                when( variantCount == 0
                    error( strcat(
                        "Simple 3D: a Variants.lst was found but no matching "
                        "variants were parsed for this board.\n"
                        "The file likely belongs to a different project. "
                        "Delete or replace the Variants.lst in the design "
                        "folder, or remove it to export all components.\n" ) )
                )

                ; Does the table describe THIS board? A file that parses but
                ; names another project's components, or none at all, exports
                ; the whole board under variant names and says nothing.
                s3dVariantFit( variantSymbolList variantFile )

                foreach( variant variantSymbolList
                    printf( "Exporting .json for variant: %s\n" variant )

                    ; FIX (simple3d 2026-07-21): was
                    ;   symbols = append( variantSymbolList[variant]
                    ;                     alternateParts[variant]~>? )
                    ; The ~>? half was actually FINE - alternateParts[variant] is
                    ; a table (dumps as "table:parts") keyed by refdes, so ~>?
                    ; returned (C43 C44) and those components were placed. The
                    ; junk came from the OTHER side: gdsysGetVariantInfo's parser
                    ; appended the first property token instead of the refdes to
                    ; the variant's symbol list (fixed above, both branches), so
                    ; variantSymbolList carried two bogus "VALUE=12pF" entries.
                    ;
                    ; With the parser fixed, variantSymbolList[variant] holds every
                    ; installed refdes - base parts AND alternate parts - so the
                    ; append is now redundant and would duplicate C43/C44.
                    ; alternateParts stays available for its actual purpose: the
                    ; per-part property overrides, which a 3D export does not need.
                    ;
                    ; (The old boundp('alternateParts) test was dead anyway - a
                    ; plain let local assigned unconditionally above, so always
                    ; bound. Noted as "Minor" back in round 2.)
                    ;
                    ; FIX (simple3d 2026-07-22): was
                    ;   symbols = variantSymbolList[variant]
                    ; i.e. the parsed variant list WAS the export list, so a
                    ; symbol the parser did not return could not be exported at
                    ; all - which is how mechanical components went missing.
                    ; The list now comes from the design and the variant table
                    ; only removes from it. See s3dSymbolsToExport.
                    symbols = s3dSymbolsToExport( variantSymbolList variant )

                    variantName = lowerCase( strcat( dsnName "_" variant ) )
                    fileName = lowerCase( strcat( dir "/" variantName ".json" ) )
                    create3dIntermediateFormat( thicknesses edgeCuts pcbColor symbols variantName fileName silk )
                )

                ; And the whole board, variants ignored, as one more file. Same
                ; routine with no variant table - so NO_STEP_EXPORT still
                ; excludes, and nothing else does. The name is the one the
                ; no-variant export uses, which cannot collide with
                ; <design>_<variant>.json; the window tells it apart by the
                ; "full_board" marker rather than by guessing from the name.
                when( S3D_ExportFullBoard
                    symbols = s3dSymbolsToExport( nil nil )
                    variantName = lowerCase( dsnName )
                    fileName = strcat( dir "/" variantName ".json" )
                    create3dIntermediateFormat( thicknesses edgeCuts pcbColor
                                                symbols variantName fileName
                                                silk t )
                    printf( "Simple 3D: plus the whole board (variants ignored) -> %s.json\n"
                            variantName )
                )

                ; print() quotes its argument and adds no newline; this is a
                ; message to a person, not a value being dumped.
                ;
                ; No green: axlUIWPrint's severities are info0, info1, warn,
                ; error and fatal, and none of them is "success". A completion
                ; line therefore prints in the console's ordinary color. The
                ; GUI log does color its own completion line green, and that
                ; is where the result is actually judged.
                printf( "Simple 3D: export complete - %d variant(s) written.\n"
                        variantCount )
            else
                error( "No variant information could be read!" )
            )
        else
            ; export all symbols, if no variant.lst can be found
            ; Name the path it looked at. "No variant information present" on
            ; its own is indistinguishable from "your Variants.lst was not
            ; found", and those need different things done about them.
            warn( "No variant information present!\n Exporting all components!" )
            printf( "Simple 3D: no Variants.lst beside the board (looked for %s)\n"
                    variantFile )

            ; Same routine as the variant path, with no variant table: every
            ; symbol that has a refdes and is not marked NO_STEP_EXPORT.
            symbols = s3dSymbolsToExport( nil nil )

            variantName = lowerCase( dsnName )
            fileName = strcat( dir "/" variantName ".json" )
            create3dIntermediateFormat( thicknesses edgeCuts pcbColor symbols variantName fileName silk )
        )
    )
)
