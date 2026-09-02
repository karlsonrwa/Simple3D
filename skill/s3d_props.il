;=====================================================================
;  skill/s3d_props.il - NO_STEP_EXPORT / ALWAYS_STEP_EXPORT, embedded models, what has a STEP model
;
;  Part 3 of 9 of the Simple 3D exporter, cut from
;  makeVariant3dIntermediates.il in round 76 (plan D6) with every procedure
;  and comment as it was; that file loads the parts in order. Load it, or
;  simple3d.il, never a part on its own.
;=====================================================================


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
    let( ( models out ( first t ) )
        models = s3dEmbeddedModels()
        out = "\"embedded_models\": ["
        foreach( m models
            ; Quoted like every other string that reaches the file (round 76,
            ; D4). A name with a quote or backslash used to be left out with a
            ; warning, from the days this file had no escaper of its own.
            unless( first  out = strcat( out ", " ) )
            first = nil
            out = strcat( out s3dJsonQuote( m ) )
        )
        strcat( out "]" )
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
