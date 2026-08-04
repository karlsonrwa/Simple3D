;=====================================================================
;  s3d_userprop_test.il  -  HAND TEST, run from the Allegro console.
;
;  *** THIS IS THE ONE FILE IN THE PROJECT THAT WRITES TO THE DESIGN. ***
;  Everything else - the exporter, the launcher, every probe under
;  tools/probes - only reads. This one creates a property dictionary entry
;  and attaches a property to an object, so read the usage below before
;  running it, and run it on a board you can afford to close without saving.
;
;  It answers one question before any export code is changed: can a
;  user-defined property be created and attached to a symbol (or its
;  component, or its component definition), and does axlDBGetProperties -
;  which is what the exporter reads with - hand it back afterwards?
;
;  Usage:
;      load("d:/Projects/OrCAD/Scripts/Simple3D/tools/s3d_userprop_test.il")
;
;      s3dPropDict()                  ; what user properties exist now
;      s3dPropShow( "A4" )            ; every property on that symbol today
;      s3dPropAdd( "A4" )             ; define if needed + attach to the SYMBOL
;      s3dPropAdd( "A4" 'component )  ; ... to the component instance instead
;      s3dPropAdd( "A4" 'compdef )    ; ... to the component definition
;      s3dPropShow( "A4" )            ; read it back - the point of the test
;      s3dPropRemove( "A4" )          ; take it off again (same 3rd argument)
;
;  Nothing is saved. The board on disk is untouched until you save it, so
;  closing without saving undoes everything here; Allegro's own undo should
;  also cover it, and s3dPropRemove is the explicit way back.
;
;  WHAT TO LOOK FOR. The interesting outcomes are, in order:
;    1. the dictionary entry is created (or already exists);
;    2. axlDBAddProp returns non-nil - the attach was accepted;
;    3. s3dPropShow then LISTS the property. That third one is what the
;       export would read, and it is the answer we actually need.
;  If 3 fails on the compdef but works on the symbol, the flag belongs on
;  the symbol - which is also the level that survives a netlist import.
;
;  The property is created as BOOLEAN on purpose. Cadence's own
;  documentation: a BOOLEAN property has no value, it either exists on the
;  object or it does not, and querying it returns t when it is there. That
;  is exactly the "presence is the test" the exporter already uses for
;  NO_STEP_EXPORT, and it rules out the trap a STRING would bring - a
;  property whose value says "FALSE" while its presence says yes.
;=====================================================================

; The property under test. Change it here to try a different name.
S3D_TestProp = "ALWAYS_STEP_EXPORT"
S3D_TestPropType = "BOOLEAN"

; --------------------------------------------------------------------
; helpers
; --------------------------------------------------------------------

; Every user-defined property in this design, printed. Names come back as
; strings, but coerce anything else with %L rather than assuming - the same
; care s3dObjectHasProp takes, and for the same reason: a symbol printed as
; a string compares false against the string.
procedure( s3dPropDict()
    let( ( dict ( n 0 ) name )
        dict = nil
        errset( dict = axlDBGetPropDict( 'user ) )
        printf( "\n=== user-defined properties in this design ===\n" )
        foreach( entry dict
            name = if( stringp( entry ) then entry else sprintf( nil "%L" entry ) )
            n = n + 1
            printf( "  %s\n" name )
        )
        printf( "  %d in total\n" n )
        printf( "  (Allegro's own list: Setup - Property Definitions)\n" )
        dict
    )
)

; t if the dictionary already knows this name.
procedure( s3dPropDictHas( t_name )
    let( ( dict ( found nil ) name )
        dict = nil
        errset( dict = axlDBGetPropDict( 'user ) )
        foreach( entry dict
            name = if( stringp( entry ) then entry else sprintf( nil "%L" entry ) )
            when( upperCase( name ) == upperCase( t_name )  found = t )
        )
        found
    )
)

; The placed symbol carrying this refdes, or nil. Case-insensitive, because
; the refdes typed at the console and the one in the database need not agree
; on case.
procedure( s3dPropFindSym( t_refdes )
    let( ( ( hit nil ) refdes )
        foreach( sym axlDBGetDesign()->symbols
            refdes = nil
            errset( refdes = sym->refdes )
            when( stringp( refdes ) && (upperCase( refdes ) == upperCase( t_refdes ))
                unless( hit  hit = sym )
            )
        )
        unless( hit
            printf( "Simple 3D test: no placed symbol with refdes %s\n" t_refdes )
        )
        hit
    )
)

; The dbid one level asks for: 'symbol (default), 'component or 'compdef.
; Each read is guarded - a symbol with no logical component has neither of
; the last two, and that is an answer, not an error.
procedure( s3dPropTarget( o_sym s_level )
    let( ( dbid )
        dbid = nil
        cond(
            ( s_level == 'component
                errset( dbid = o_sym->component )
                unless( dbid
                    printf( "  this symbol has no component (it is not in the netlist)\n" ) )
            )
            ( s_level == 'compdef
                errset( dbid = o_sym->component->compdef )
                unless( dbid
                    printf( "  this symbol has no component definition\n" ) )
            )
            ( t  dbid = o_sym )
        )
        dbid
    )
)

; --------------------------------------------------------------------
; the three commands
; --------------------------------------------------------------------

; Print every property on a symbol, its component and its compdef, exactly as
; axlDBGetProperties hands them back. Raw output on purpose: this is the call
; the exporter reads with, so what it prints here is what the export sees.
procedure( s3dPropShow( t_refdes )
    let( ( sym dbid props )
        sym = s3dPropFindSym( t_refdes )
        when( sym
            printf( "\n=== properties on %s ===\n" t_refdes )
            foreach( level list( 'symbol 'component 'compdef )
                printf( "  --- %L ---\n" level )
                dbid = s3dPropTarget( sym level )
                when( dbid
                    props = nil
                    errset( props = axlDBGetProperties( dbid ) )
                    if( props then
                        foreach( entry props
                            printf( "    %L\n" entry )
                        )
                    else
                        printf( "    (none)\n" )
                    )
                )
            )
            printf( "  looking for %s: symbol %L  component %L  compdef %L\n"
                    S3D_TestProp
                    s3dPropHasHere( s3dPropTarget( sym 'symbol ) )
                    s3dPropHasHere( s3dPropTarget( sym 'component ) )
                    s3dPropHasHere( s3dPropTarget( sym 'compdef ) ) )
        )
        t
    )
)

; t if the property under test is on this dbid. A local copy of the
; exporter's own test, so this file stands alone and can be loaded before
; anything else - the whole point is to run it BEFORE the export changes.
procedure( s3dPropHasHere( o_dbid )
    let( ( props key ( found nil ) )
        when( o_dbid
            props = nil
            errset( props = axlDBGetProperties( o_dbid ) )
            foreach( entry props
                when( entry
                    key = if( listp( entry ) then car( entry ) else entry )
                    unless( stringp( key )  key = sprintf( nil "%L" key ) )
                    when( upperCase( key ) == upperCase( S3D_TestProp )  found = t )
                )
            )
        )
        found
    )
)

; Define the property if the dictionary does not have it, then attach it.
;
; The dictionary entry is created with object list t - every object type that
; can carry a property - rather than a guessed list of type names, so the call
; cannot fail on a spelling this Allegro does not use.
procedure( s3dPropAdd( t_refdes @optional ( s_level 'symbol ) )
    let( ( sym dbid made result )
        sym = s3dPropFindSym( t_refdes )
        when( sym
            printf( "\n=== adding %s to %s (%L) ===\n" S3D_TestProp t_refdes s_level )

            if( s3dPropDictHas( S3D_TestProp ) then
                printf( "  dictionary: %s already defined\n" S3D_TestProp )
            else
                made = nil
                errset( made = axlDBCreatePropDictEntry( S3D_TestProp
                                                         S3D_TestPropType t ) )
                if( made then
                    printf( "  dictionary: created %s as %s -> %L\n"
                            S3D_TestProp S3D_TestPropType made )
                else
                    printf( "  dictionary: FAILED to create %s.\n" S3D_TestProp )
                    printf( "    A name already used by Allegro cannot be redefined;\n" )
                    printf( "    try another name in S3D_TestProp at the top of this file.\n" )
                )
            )

            dbid = s3dPropTarget( sym s_level )
            when( dbid
                ; A BOOLEAN property carries no value - Cadence's own doc says
                ; the value is ignored and presence is everything - so nil is
                ; passed deliberately, in the single name/value shape the
                ; documentation uses.
                result = nil
                errset( result = axlDBAddProp( list( dbid )
                                               list( S3D_TestProp nil ) ) )
                if( result then
                    printf( "  attach: accepted -> %L\n" result )
                else
                    printf( "  attach: REFUSED (axlDBAddProp returned nil).\n" )
                    printf( "    Either this object type may not carry the property,\n" )
                    printf( "    or the design is open read-only.\n" )
                )
                printf( "  reading it back now: %L\n" s3dPropHasHere( dbid ) )
                printf( "  (Show Element on %s should list it too. Nothing is saved yet.)\n"
                        t_refdes )
            )
        )
        t
    )
)

; Take it off again. The dictionary entry is left in place - it is harmless,
; and axlDBDeletePropDictEntry is a separate decision.
procedure( s3dPropRemove( t_refdes @optional ( s_level 'symbol ) )
    let( ( sym dbid result )
        sym = s3dPropFindSym( t_refdes )
        when( sym
            dbid = s3dPropTarget( sym s_level )
            when( dbid
                result = nil
                errset( result = axlDBDeleteProp( list( dbid )
                                                  list( S3D_TestProp ) ) )
                printf( "\n=== removing %s from %s (%L) -> %L ===\n"
                        S3D_TestProp t_refdes s_level result )
                printf( "  reading it back now: %L\n" s3dPropHasHere( dbid ) )
            )
        )
        t
    )
)

printf( "*** s3d_userprop_test.il loaded. THIS FILE WRITES TO THE DESIGN. ***\n" )
printf( "    s3dPropDict()   s3dPropShow(\"A4\")   s3dPropAdd(\"A4\")   s3dPropRemove(\"A4\")\n" )
printf( "    third argument for the last two: 'symbol (default), 'component, 'compdef\n" )
