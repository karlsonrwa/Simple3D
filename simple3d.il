;=====================================================================
;  simple3d.il   v1.0
;
;  Adds  File -> Export -> Simple 3D  to Allegro PCB Editor.
;
;  On selection it:
;    1. resolves the design's rev/pcb  ->  rev/cad  output folder,
;    2. runs the (fixed) makeVariant3dIntermediates to write the
;       intermediate JSON(s) into  cad,  one per variant,
;    3. launches the Python GUI with the JSON path, the output (cad)
;       path and the dated output filename already filled in.
;
;  Silkscreen, when enabled, is collected by makeVariant3dIntermediates into
;  the same JSON and extruded into thin solids by the Python side. Which
;  Allegro layers count as silkscreen (and the ink thickness) is set in
;  simple3d_config.json, next to these two files - see S3D_ConfigFile.
;
;  LOAD ORDER (e.g. from allegro.ilinit or manually). The whole tool lives in
;  ONE folder; put yours in place of the example below:
;      load("d:/Tools/Simple3D/makeVariant3dIntermediates.il")  ; incl. fixes + MFRPN helpers
;      load("d:/Tools/Simple3D/simple3d.il")                    ; this file
;
;  Nothing in these files needs editing to match. Where the tool is installed
;  comes from the Allegro variable SIMPLE3D_DIR (in your own pcbenv/env), or
;  from the folder this file was loaded from - see s3dResolveScriptDir.
;
;  Follows the menu-insertion idiom from the user's own addeskd_v30.il
;  (idempotent find/insert + menu trigger + TriggerClear before TriggerSet).
;
;  version 1.0
;=====================================================================

;=====================================================================
;  SETTINGS
;
;  NO setting needs editing here any more. Everything the user chooses is in
;  simple3d_config.json (shipped defaults, tracked) with
;  simple3d_config.local.json on top (yours, gitignored) - Python paths, the
;  model library, the menu label, every GUI default and the silkscreen layer
;  lists. Editing settings in three places was the arrangement before.
;
;  The one thing that cannot live in the config is where the tool itself is:
;  the config is found relative to it. That comes from the environment or from
;  the load path instead of from a literal - see s3dResolveScriptDir.
;
;  Plain assignment (=), NOT defvar: defvar only sets a value the first time
;  and is ignored on reload, so a user edit would silently not take effect.
;=====================================================================

; The Simple 3D project folder - the ONE folder that holds this whole tool:
; both .il files, simple3d_config.json AND the "stepbuilder" package sit here
; together. It is needed for two things: the config is found relative to it,
; and it is the working directory Python is started in, which is what makes
; "-m stepbuilder" resolve.
;
; DELIBERATELY EMPTY, and no path belongs here. This file is under version
; control, so a path written here is one installation's path shipped to
; everyone and overwritten in everyone's working copy on the next update.
; s3dResolveScriptDir fills it in, from - in order:
;
;   1. the Allegro variable SIMPLE3D_DIR, set in your own pcbenv/env;
;   2. the folder this file was loaded from, when SKILL will say.
;
; If both come up empty the tool says so and does nothing, which is the honest
; outcome: it cannot find its own Python package, and guessing would only move
; the failure somewhere less obvious.
S3D_ScriptDir = ""

; Captured at LOAD time, while the port reading this file still exists - it is
; the only moment SKILL can be asked. errset because `piport` and
; `get_filename` are core-language names this project has not verified against
; its Allegro; nil simply means the second source above is unavailable.
S3D_LoadedFrom = nil
errset( S3D_LoadedFrom = get_filename( piport ) )

; The settings file. Only change this if you deliberately keep the config
; somewhere other than the project folder. "" falls back to the built-in
; defaults below and in makeVariant3dIntermediates.il.
S3D_ConfigFile = strcat( S3D_ScriptDir "/simple3d_config.json" )

; MFRPN DISABLED (property attachment unreliable); kept for future re-enable.
; If t, abort the export when an exportable component (one that has a STEP
; model) has no MFRPN property. If nil, warn and continue - mechanicals and
; fiducials legitimately lack MFRPN, so nil is the safe default.
; S3D_StrictMfrPn = nil

;=====================================================================
;  SETTINGS READ FROM simple3d_config.json
;
;  Defaults here are what applies when the file is missing, unreadable, or
;  simply does not mention a key - so a deleted config degrades to a working
;  tool rather than a broken one.
;=====================================================================

S3D_Python = "python"
S3D_PythonW = "pythonw"
S3D_CommandVisible = "Simple 3D"
S3D_CommandName = "simple_3d_export"

; Define ALWAYS_STEP_EXPORT in the design's property dictionary, so it can be
; attached from Allegro's own Properties dialog. See s3dEnsureAlwaysProp for
; what it is for and why it has to be created rather than simply used.
; Set allegro.defineAlwaysExportProp to false to leave the design alone.
S3D_DefineAlwaysProp = t

; The property name itself lives in makeVariant3dIntermediates.il, which is
; loaded first. Defined here too if that load order was not followed, so this
; file cannot fail on an unbound name - and never redefined, so there is only
; ever one value of it in the session.
unless( boundp( 'S3D_AlwaysExportProp )
    S3D_AlwaysExportProp = "ALWAYS_STEP_EXPORT"
)

; Re-read on every export as well as at load time, so editing the config takes
; effect without reloading the SKILL files. The menu label is the exception -
; the menu is built at load time, so a changed label needs a reload.
; Only the "allegro" section is read here. The "gui" section is the Python
; side's, and it reads it directly from the same file - the launcher forwards
; nothing, so the two cannot drift apart.
procedure( s3dLoadSettings()
    let( ( cfg allegro value )
        when( (S3D_ConfigFile != "") && isFile( S3D_ConfigFile )
            cfg = nil
            ; Defaults plus simple3d_config.local.json on top - see
            ; s3dConfigRead in makeVariant3dIntermediates.il, which loads first.
            errset( cfg = s3dConfigRead( S3D_ConfigFile ) )
            if( cfg then
                allegro = s3dJsonGet( cfg "allegro" )

                value = s3dJsonGet( allegro "python" )
                when( stringp( value )  S3D_Python = value )

                ; pythonw may legitimately be "" (meaning: use S3D_Python), so
                ; presence decides here, not truthiness.
                when( s3dJsonHas( allegro "pythonw" )
                    value = s3dJsonGet( allegro "pythonw" )
                    when( stringp( value )  S3D_PythonW = value )
                )

                value = s3dJsonGet( allegro "menuLabel" )
                when( stringp( value )  S3D_CommandVisible = value )

                value = s3dJsonGet( allegro "commandName" )
                when( stringp( value )  S3D_CommandName = value )

                ; Presence decides, not truthiness: the value is a boolean and
                ; false is a meaningful setting, which a plain `when( value )`
                ; would read as "not set" and quietly turn back on.
                when( s3dJsonHas( allegro "defineAlwaysExportProp" )
                    value = s3dJsonGet( allegro "defineAlwaysExportProp" )
                    S3D_DefineAlwaysProp = if( value == nil then nil else t )
                )
            else
                s3dWarn( sprintf( nil "Simple 3D: could not parse %s; using built-in settings."
                                  S3D_ConfigFile ) )
            )
        )
        t
    )
)

; NOT CALLED HERE. The settings live in a file found relative to
; S3D_ScriptDir, and S3D_ScriptDir can be overridden by the environment - so
; the folder has to be settled first. The call is a few lines below, after
; s3dResolveScriptDir.

;=====================================================================
;  PATH HELPERS
;=====================================================================

; Normalise back-slashes to forward slashes (SKILL and the shell both accept
; forward slashes on Windows, and it avoids escaping headaches).
procedure( s3dSlashes( t_path )
    when( t_path
        buildString( parseString( t_path "\\" ) "/" )
    )
)

; The folder part of a path, by SCANNING for the last separator.
;
; Not parseString: it collapses consecutive separators, so a UNC path
; \\server\share\tools\x.il would come back as the relative server/share. The
; same reason s3dDesignFolder in the exporter scans rather than splits.
; Returns "" when there is no separator at all - a bare file name says nothing
; about where it is, and pretending otherwise would point the tool at whatever
; the working directory happens to be.
procedure( s3dFolderOf( t_path )
    let( ( ( cut 0 ) c )
        unless( stringp( t_path )  t_path = "" )
        for( i 1 strlen( t_path )
            c = substring( t_path i 1 )
            when( (c == "/") || (c == "\\")  cut = i )
        )
        if( cut > 1 then s3dSlashes( substring( t_path 1 cut - 1 ) ) else "" )
    )
)

; Where this tool is installed. Two sources, in order, and no path in the file.
;
; 1. SIMPLE3D_DIR, an Allegro variable set in the user's own pcbenv/env:
;
;        set SIMPLE3D_DIR = d:/Tools/Simple3D
;
;    Explicit, per machine, and in a file no update touches. It wins, because
;    someone who sets it means it.
;
; 2. The folder this file was loaded from, captured at load in S3D_LoadedFrom.
;    Costs the user nothing when it works - the tool finds itself - but it
;    depends on core-SKILL names this project has not verified in Allegro, so
;    it can only ever be the second answer, never the only one.
;
; Nothing else. A literal here would be one installation's path shipped to
; every other, and overwritten in every working copy by the next update - which
; is the whole problem this replaced.
;
; S3D_ConfigFile follows the folder, but only while it is still the path
; derived from it: someone who pointed it elsewhere by hand meant that.
procedure( s3dResolveScriptDir()
    let( ( value wasDefault ( source nil ) )
        wasDefault = (S3D_ConfigFile == strcat( S3D_ScriptDir "/simple3d_config.json" ))

        value = nil
        errset( value = axlGetVariable( "SIMPLE3D_DIR" ) )
        if( stringp( value ) && (value != "") then
            source = "SIMPLE3D_DIR"
        else
            value = s3dFolderOf( S3D_LoadedFrom )
            when( value != ""  source = "the folder it was loaded from" )
        )

        when( source
            S3D_ScriptDir = s3dSlashes( value )
            when( wasDefault
                S3D_ConfigFile = strcat( S3D_ScriptDir "/simple3d_config.json" )
            )
            printf( "Simple 3D: script folder from %s: %s\n" source S3D_ScriptDir )
        )

        unless( source
            s3dWarn( "Simple 3D: I do not know where I am installed. Put   set SIMPLE3D_DIR = <folder holding simple3d.il>   in your pcbenv/env and reload. Nothing will run until then." )
        )
        S3D_ScriptDir
    )
)

errset( s3dResolveScriptDir() )

; The exporter lives in nine parts under skill/, loaded by
; makeVariant3dIntermediates.il (round 76, D6). An allegro.ilinit that loads
; that file first has done this already; a single load("…/simple3d.il")
; does it here, from the install folder just resolved - and BEFORE the
; settings are read, since the config reader is one of the parts.
unless( boundp( 'S3D_ExporterLoaded ) && S3D_ExporterLoaded
    when( S3D_ScriptDir != ""
        load( strcat( S3D_ScriptDir "/makeVariant3dIntermediates.il" ) )
    )
)
s3dLoadSettings()

; Decide where the JSON and STEP go, given the design's own folder.
;
; The author's historical layout is  root/rev/pcb  for the .brd and
; root/rev/cad  for the mechanical / 3D output, so when the design sits in a
; "pcb" folder that has a sibling "cad", output goes to "cad". For any other
; layout - no "pcb" folder, or a "pcb" folder without a "cad" sibling - output
; goes into the SAME folder as the .brd, so the tool works regardless of how
; the project is organised. The output folder is always created if missing.
;
; nil in means the working directory could not be read at all, which is what
; the load-time self-test at the bottom of this file warns about. Say the same
; thing here rather than letting parseString fail on nil: a raw SKILL trace is
; exactly what that self-test exists to prevent.
; NOTE: if/else, not an early return - return() is legal only inside a prog,
; and this is a let. (The same trap s3dExportCommand's own note describes.)
procedure( s3dResolveCadDir( t_designDir )
    let( ( parts n leaf parent cad )
        if( !stringp( t_designDir ) then
            s3dWarn( "Simple 3D: could not read the design's folder - getWorkingDir() answered nothing. Edit s3dDesignDir() in simple3d.il to use your install's working-directory function." )
            nil
        else
            t_designDir = s3dSlashes( t_designDir )
            parts = parseString( t_designDir "/" )
            n = length( parts )
            leaf = if( n >= 1 then nth( n - 1 parts ) else nil )

            if( leaf && (upperCase( leaf ) == "PCB") then
                ; …/rev/pcb -> candidate …/rev/cad
                parent = buildString( s3dHeadList( parts n - 1 ) "/" )
                cad = strcat( parent "/cad" )
                if( isDir( cad ) then
                    ; sibling cad exists -> use it (author's standard layout)
                    printf( "Simple 3D: output folder (cad): %s\n" cad )
                    cad
                else
                    ; pcb layout but no cad sibling -> write beside the brd
                    printf( "Simple 3D: no 'cad' folder next to 'pcb'; output goes beside the brd: %s\n" t_designDir )
                    s3dMakeDirs( t_designDir )
                    t_designDir
                )
            else
                ; not a pcb folder -> write in the design's own folder
                printf( "Simple 3D: output folder (beside brd): %s\n" t_designDir )
                s3dMakeDirs( t_designDir )
                t_designDir
            )
        )
    )
)

; s3dHeadList( lst n ) -> first n elements of lst (helper; SKILL has no builtin).
;
; PREFIXED, like everything else this project defines. SKILL has one global
; namespace and these files are loaded into a session alongside whatever else
; the user runs, so a helper called "headList" is a name collision waiting to
; happen - and the winner is decided by load order, silently.
procedure( s3dHeadList( lst x_n )
    let( ( out ( i 0 ) )
        out = tconc( nil nil )
        foreach( e lst
            when( i < x_n  tconc( out e ) )
            i = i + 1
        )
        cdr( car( out ) )
    )
)

; The dated output filename (<brd>_simple_DD_MM_YYYY, trailing _ on collision)
; is produced by the Python side (--dated-name), which has a tested date
; formatter and can check for existing files. Nothing here needs the date.

; Return the design directory. When a board is open, getWorkingDir() is that
; directory. (If getWorkingDir is spelled differently in your install, this is
; the ONE line to adjust - see the load-time self-test at the bottom.)
procedure( s3dDesignDir()
    let( ( dir )
        errset( dir = getWorkingDir() )
        when( dir  s3dSlashes( dir ) )
    )
)

;=====================================================================
;  ALWAYS_STEP_EXPORT - the one property this tool has to create
;
;  NO_STEP_EXPORT is Allegro's own: it is on every symbol's property list
;  already, and the export only reads it. ALWAYS_STEP_EXPORT does not exist
;  anywhere until something defines it, and until it is defined it cannot be
;  attached to anything - not from SKILL and not from the Properties dialog.
;  So the tool defines it, and then stays out of the way: WHAT it goes on is
;  entirely the user's business, done the ordinary Allegro way.
;
;  WHY THE PROPERTY EXISTS. Since the variant rule was settled on the refdes,
;  anything carrying one obeys Variants.lst - which is right for a connector
;  housing (it should vanish with the connector it belongs to) and wrong for a
;  wire-solder pad (it is part of the bare board and belongs in every variant).
;  In the database the two are indistinguishable: refdes, a STEP model, no BOM
;  line, named in no variant. The difference is intent, so it is written on the
;  part.
;
;  WHY AT LOAD TIME, AND ALSO AT EXPORT TIME. A property dictionary belongs to
;  a DESIGN, not to the installation - axlDBGetPropDict reports "entries in the
;  current design" - so defining it once at startup would only ever reach the
;  board that happened to be open then. It is therefore done at load AND at the
;  top of every export, which between them cover a board opened at any point.
;  Both calls are cheap: they read the dictionary and return.
;
;  It is created as BOOLEAN because Allegro's own documentation says a BOOLEAN
;  property has no value - it either exists on the object or it does not - and
;  that is exactly the test the export makes. A STRING property could carry the
;  word "FALSE" while its presence said yes.
;
;  THE DESIGN IS CHANGED BY THIS. A dictionary entry is stored in the board, so
;  Allegro will want the design saved. Set allegro.defineAlwaysExportProp to
;  false to switch it off entirely; the export then reads the property if some
;  other board already has it, and never writes anything.
;=====================================================================

; Is a REAL board open - as opposed to the empty placeholder Allegro sometimes
; comes up with?
;
; The user's observation, and it matches what happened here: starting the editor
; from its own icon (rather than by opening a .brd) sometimes lands in "nothing"
; - a design that is open as far as the API is concerned but is not a board, and
; editing it produces errors that make no sense. Anything this tool writes must
; be able to tell the two apart.
;
; The test is the drawing FILE. axlCurrentDesign gives a name whether or not
; there is anything behind it; axlGetDrawingName gives the path, and a real
; board has one that exists on disk. A brand-new board that has never been saved
; also fails this test, which is the conservative side to fail on: it gets the
; property at export time instead.
procedure( s3dRealDesign()
    let( ( name path )
        name = nil
        errset( name = axlCurrentDesign() )
        path = nil
        errset( path = axlGetDrawingName() )
        stringp( name ) && (name != "") &&
        stringp( path ) && (path != "") && isFile( path )
    )
)

procedure( s3dEnsureAlwaysProp()
    ; prog locals are BARE SYMBOLS - the (var value) init form is let-only and
    ; prog rejects the whole procedure with "local vars must be symbol". The
    ; same trap s3dPreflight documents; it cost this feature a live round,
    ; because both call sites wrap this in errset and the failure was silent.
    prog( ( dict found name made )
        found = nil
        unless( S3D_DefineAlwaysProp  return( nil ) )
        ; No board, nothing to write to. Silent: this is the ordinary state
        ; while the editor is starting, and the state of the placeholder design
        ; it sometimes opens instead of a board.
        unless( s3dRealDesign()       return( nil ) )

        dict = nil
        errset( dict = axlDBGetPropDict( 'user ) )
        foreach( entry dict
            name = if( stringp( entry ) then entry else sprintf( nil "%L" entry ) )
            when( upperCase( name ) == upperCase( S3D_AlwaysExportProp )  found = t )
        )
        when( found  return( t ) )

        made = nil
        errset( made = axlDBCreatePropDictEntry( S3D_AlwaysExportProp "BOOLEAN" t ) )
        if( made then
            printf( "Simple 3D: defined the %s property in this design.\n"
                    S3D_AlwaysExportProp )
            printf( "Simple 3D: attach it to a symbol (Edit - Properties) to keep that part\n" )
            printf( "  in EVERY variant, whatever Variants.lst says. The design now has an\n" )
            printf( "  unsaved change; set allegro.defineAlwaysExportProp to false to stop this.\n" )
            return( t )
        else
            ; Not fatal, and not even necessarily wrong: a design that already
            ; has the name from somewhere else lands here too, and the export
            ; reads the property either way.
            s3dWarn( sprintf( nil "Simple 3D: could not define %s in this design; it can still be attached if it is already defined."
                              S3D_AlwaysExportProp ) )
            return( nil )
        )
    )
)

; Called by Allegro when a design has been OPENED. `open` is one of the nine
; triggers this release supports (axlTriggerSet(nil nil) answers: open save
; close exit menu xprobe select window xsection), and it is the right hook for
; this: the property is then in place before the first export rather than after
; it, which is what "the pads are missing from my drawing" needs.
;
; A trigger function takes ONE argument and must keep its work short - the
; documented restrictions - and it must not be able to stop a board from
; opening, hence errset. Everything it does is guarded again inside
; s3dEnsureAlwaysProp: no switch, no real board, entry already there -> return.
;
; This is the second attempt at defining the property automatically. The first
; ran at LOAD time and coincided with Allegro crashing on startup; the design it
; would have written to was most likely the empty placeholder the editor
; sometimes comes up with instead of a board. s3dRealDesign is what tells the
; two apart now, and the switch below turns all of it off.
procedure( s3dOpenTrigger( g_arg )
    errset( s3dEnsureAlwaysProp() )
    t
)

;=====================================================================
;  PROGRESS METER
;
;  Why this exists: pressing Export looked like nothing happening. The board is
;  read, the JSON written and Python started before any window appears - seconds
;  on a real board - and Allegro's own Ready/Busy light stays green through all
;  of it, so there was nothing to watch. axlMeterCreate is Allegro's own
;  progress form: a title, one line of about 28 characters, and an optional Stop
;  button.
;
;  Stop is NOT enabled. Nothing here can be interrupted once it is running -
;  makeVariant3dIntermediates is one call - and a button that does not stop
;  anything is worse than no button.
;
;  Every call is wrapped in errset. The meter is a courtesy: a release that
;  lacks it, or a form that refuses to open, must not be able to fail an export
;  that would otherwise work.
;
;  SKILL has no unwind-protect, so a hard error inside the export would leave
;  the form on screen. Since 2026-09-03 the export call is wrapped in errset
;  and the command takes the meter down itself when it fails; for anything
;  else, s3dMeterOn destroys any stale meter before creating its own, which
;  clears one away at the next export.
;=====================================================================

procedure( s3dMeterOn( t_text )
    errset( axlMeterDestroy() )
    errset( axlMeterCreate( "Simple 3D export" t_text nil ) )
    t
)

procedure( s3dMeterStep( x_percent t_text )
    errset( axlMeterUpdate( x_percent t_text ) )
    t
)

procedure( s3dMeterOff()
    errset( axlMeterDestroy() )
    t
)

;=====================================================================
;  THE COMMAND
;=====================================================================

; NOTE: prog, not let. SKILL's return() is only legal inside a prog block - in a
; let it raises "return can only be used within a prog". prog also means the
; body's last value is NOT the result: every exit has to be an explicit return().
procedure( s3dExportCommand()
    prog( ( designName designDir cadDir check noMfrPn noModel argTail pyOk )

        ; The folder may have been set since this file loaded - and if it still
        ; is not known, everything below would fail somewhere less obvious: the
        ; config would not be found, and Python would be started in a directory
        ; where "-m stepbuilder" means nothing.
        errset( s3dResolveScriptDir() )
        when( S3D_ScriptDir == ""
            printf( "\n===== Simple 3D: I do not know where I am installed =====\n" )
            printf( "Put this in your Allegro environment file (%%HOME%%/pcbenv/env):\n" )
            printf( "    set SIMPLE3D_DIR = <the folder holding simple3d.il>\n" )
            printf( "then reload the SKILL files or restart Allegro.\n" )
            printf( "=========================================================\n\n" )
            axlUIWPrint( nil "Simple 3D: SIMPLE3D_DIR is not set - see the console." )
            return( nil )
        )

        ; Pick up config edits without reloading the SKILL files.
        errset( s3dLoadSettings() )

        designName = axlCurrentDesign()
        unless( designName
            axlUIWPrint( nil "Simple 3D: no design is open." )
            return( nil )
        )

        ; A NAME is not a BOARD. Started from its own icon, Allegro sometimes
        ; comes up on an empty placeholder rather than on the previous design -
        ; the API answers every question about it, and editing it produces
        ; errors that make no sense. Say so here rather than exporting a board
        ; that is not there and leaving the user to interpret whatever comes out
        ; the far end.
        unless( s3dRealDesign()
            printf( "Simple 3D: %L is open, but there is no board file behind it (%L).\n"
                    designName errset( axlGetDrawingName() ) )
            printf( "  This is the empty design Allegro sometimes starts on instead of a board.\n" )
            printf( "  Open the .brd itself and run the export again.\n" )
            axlUIWPrint( nil
                "Simple 3D: no board file behind this design - see the console." )
            return( nil )
        )

        ; The board open now may not be the one that was open at load time, and
        ; the property dictionary belongs to the design - so this is the call
        ; that actually reaches every board the user exports. It returns at once
        ; when the entry is already there.
        ;
        ; errset returns nil ONLY when the call errored - a legitimate nil
        ; return comes back as (nil). So this says so instead of swallowing it:
        ; a silent errset is exactly how the first version of this went missing.
        unless( errset( s3dEnsureAlwaysProp() )
            s3dWarn( "Simple 3D: s3dEnsureAlwaysProp() failed - ALWAYS_STEP_EXPORT was not defined in this design." )
        )

        designDir = s3dDesignDir()
        cadDir = s3dResolveCadDir( designDir )
        printf( "Simple 3D: JSON + STEP output -> %s\n" cadDir )

        ; From here on the command has work to do that takes visible time, so
        ; the meter goes up before the first of it and comes down on every path
        ; out - including the pre-flight's refusal below.
        s3dMeterOn( "Checking components..." )

        ; --- pre-flight: components with no 3D model ------------------
        ; s3dCheckMfrPn still returns the no-model list (2nd element); its MFRPN
        ; half is disabled - property attachment unreliable - but kept for future.
        check = s3dCheckMfrPn()
        ; noMfrPn = car( check )                        ; MFRPN DISABLED (future)
        noModel = cadr( check )

        when( noModel
            printf( "Simple 3D: %d component(s) have no 3D model, not exported: %L\n"
                    length( noModel ) noModel )
        )
        ; --- MFRPN pre-flight DISABLED (kept for future) --------------
        ; when( noMfrPn
        ;     printf( "Simple 3D: %d exported component(s) have no MFRPN: %L\n"
        ;             length( noMfrPn ) noMfrPn )
        ;     when( S3D_StrictMfrPn
        ;         axlUIWPrint( nil
        ;             "Simple 3D: aborting - components without MFRPN (see console)." )
        ;         return( nil )
        ;     )
        ; )

        ; --- generate the intermediate JSON(s) into cad ---------------
        ; makeVariant3dIntermediates takes the output dir as its first arg and
        ; createDir's it, so pointing it at cad needs no patch. With a
        ; Variants.lst present it writes one JSON per variant.
        s3dMeterStep( 20 "Reading the board..." )
        printf( "Simple 3D: writing intermediate JSON...\n" )
        ; nil for the colour: the JSON's colour is a placeholder the window
        ; overrides from the config, so the exporter's own default serves
        ; (round 80, G4; this used to pass a green of its own).
        ; errset with t prints the error. A failed export takes the meter down
        ; and says so; it used to leave the form at 20% for the user to read as
        ; a hang (2026-09-03, seen with a Variants.lst the parser refused).
        unless( errset( makeVariant3dIntermediates( cadDir nil
                                                    if( (S3D_ConfigFile != "") then S3D_ConfigFile else nil ) )
                        t )
            s3dMeterOff()
            printf( "Simple 3D: the export stopped on the error above; the 3D window was not opened.\n" )
            s3dErr( "Simple 3D: export failed - see the console." )
            return( nil )
        )

        ; --- can Python actually start? -------------------------------
        ; Done AFTER the JSON exists, so a broken Python install still leaves the
        ; user with a usable export, and the message can say so. Costs a few
        ; seconds (importing OCP is slow) - worth it against a silent no-op.
        s3dMeterStep( 70 "Checking the Python side..." )
        printf( "Simple 3D: checking the Python side...\n" )
        ; The check must never be able to break the export it is reporting on:
        ; wrapped in errset so a fault inside it degrades to "skipped" instead
        ; of replacing the diagnosis with a raw SKILL error trace.
        pyOk = 'failed
        errset( pyOk = s3dPreflight( cadDir ) )
        when( pyOk == 'failed
            printf( "Simple 3D: the Python check itself errored - skipping it and launching anyway.\n" )
            printf( "  If no window appears, that is why nothing explained it: the GUI runs\n" )
            printf( "  under pythonw, which has no console to fail in.\n" )
            ; Fail-open is right - a broken check must not block a working
            ; setup - but it must not be quiet about it either, or the silent
            ; no-op it was written to prevent comes back through this door.
            s3dWarn( "Simple 3D: the Python check errored - launching unchecked. See the console." )
            pyOk = t
        )
        unless( pyOk
            s3dMeterOff()
            return( nil )
        )

        ; --- launch the GUI, prefilled --------------------------------
        ; Open the GUI with paths already set. The GUI lets the user pick color
        ; and z-datum and press Generate; with several variant JSONs it builds
        ; all of them. step_dir is the model library (or cad if unset).
        ; Build the argument tail (everything AFTER the interpreter). The
        ; launcher prepends python/pythonw and hands the whole line to cmd in
        ; one piece; see s3dLaunch for the quoting rules that keep a path with
        ; a space intact.
        ;
        ; Only design-derived values are passed. Colors, the STEP folder and
        ; the silkscreen options used to be passed here as well; the GUI now
        ; reads them from simple3d_config.json itself, so passing them would be
        ; a second copy of the same settings and a chance for the two to drift.
        argTail = strcat(
            "-m stepbuilder --gui "
            "--config \"" S3D_ConfigFile "\" "
            "--json-dir \"" cadDir "\" "
            "--output-dir \"" cadDir "\" "
            "--brd-name \"" designName "\" "
            "--dated-name"
        )

        s3dMeterStep( 95 "Starting the 3D window..." )
        printf( "Simple 3D: launching GUI (%s)\n" argTail )
        s3dLaunch( argTail )

        ; The GUI is detached, so this is the end of the command's own work -
        ; the meter must not sit there implying otherwise.
        s3dMeterOff()
        return( t )
    )
)

; Check that the Python side can actually start, BEFORE launching it detached.
;
; Why this exists: the GUI is started with "start" (detached) and normally with
; pythonw.exe, which has NO console. So when Python is missing from PATH, or
; cadquery-ocp / tkinter are not installed, the interpreter dies instantly and
; the error goes nowhere - the user sees the JSON get written, no window opens,
; and nothing explains why. Here the interpreter is run ONCE, synchronously,
; with stdout+stderr captured to a file, so the real ImportError can be shown in
; the Allegro console together with the fact that the JSON itself is fine.
;
; The command goes to cmd in one piece, in the shape s3dLaunch explains - the
; quoting rules there are the same ones here. "start /B /WAIT" is what makes it
; synchronous with no console of its own, and /D sets the working directory so
; "stepbuilder" resolves exactly as it will at launch time. Nothing is chained
; with && on purpose: a chain binds to the OUTER shell, so the /D would be lost
; if system() wraps the string in a cmd of its own. Redirection does not have
; that problem - the child inherits the handles either way.
;
; Success is signalled by a sentinel the check prints, not by an empty log: some
; installs emit deprecation warnings on stderr even when the import succeeds.
;
; THE SENTINEL IS SPLIT IN THE SOURCE - print('S3D' '_OK') - AND THAT IS NOT A
; TYPO. From Python 3.13 the interpreter keeps the text of a -c command and
; echoes the offending SOURCE LINE in a traceback. So a check written as
; print('S3D_OK') puts its own success sentinel into its own failure output:
;
;     Traceback (most recent call last):
;       File "<string>", line 1, in <module>
;         import stepbuilder.core, tkinter; print('S3D_OK')
;         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
;     ModuleNotFoundError: No module named 'OCP'
;
; and the scan below reads that echo as success. That is exactly what happened
; on 2026-08-21: a Python 3.14 arrived ahead of the user's on PATH with no OCP
; in it, the check passed itself, the GUI was launched with pythonw - which has
; no console - and it died on the same ImportError with nothing shown anywhere.
; The whole point of this procedure, defeated by its own sentinel. Two adjacent
; string literals concatenate at compile time, so the process still prints
; S3D_OK while the source text cannot contain it. A sentinel must not be
; forgeable by the output it is looking for.
;
; The check also prints S3D_PY with sys.executable and the version, first and
; unbuffered (-u), so a failure names the interpreter that actually ran rather
; than the word "python" we asked for. Which Python answered is the thing that
; is hard to see from Allegro and was the whole of this diagnosis.
;
; Returns t to proceed, nil to abort. A fault in the check itself still cannot
; block a working setup: s3dExportCommand wraps this call in errset and launches
; anyway if it errors. There is no separate fail-open branch here any more - the
; one that existed was for a pre-flight file that could not be written, and
; nothing is written now.
procedure( s3dPreflight( t_workDir )
    ; prog locals must be bare symbols - the (var value) init form is let-only
    ; syntax and prog rejects it with "local vars must be symbol". Hence the
    ; explicit assignments below.
    prog( ( exe logFile port line ok pySpoke out whichPy )
        ok      = nil
        pySpoke = nil
        out     = ""
        whichPy = ""
        exe = if( (S3D_Python != "") then S3D_Python else S3D_PythonW )
        logFile = strcat( t_workDir "/_simple3d_preflight.txt" )

        ; Importing stepbuilder.core pulls in OCP, the heavy dependency that is
        ; usually the missing one; tkinter is what the GUI itself needs. The
        ; sentinels are split literals on purpose - see the note above.
        errset( system( strcat(
            "cmd /c start /B /WAIT \"\" /D \"" S3D_ScriptDir "\" \"" exe
            "\" -u -c \"import sys; print('S3D' '_PY', sys.executable, sys.version.split()[0]); "
            "import stepbuilder.core, tkinter; print('S3D' '_OK')\" > \""
            logFile "\" 2>&1" ) ) )

        port = infile( logFile )
        when( port
            while( gets( line port )
                out = strcat( out line )
                when( rexMatchp( "S3D_OK" line )  ok = t )
                ; Which interpreter answered. Printed before the imports, so it
                ; is there on the failing run too - and that is the run where it
                ; matters, because "python" is a name and PATH decides what it
                ; means today.
                when( rexMatchp( "S3D_PY " line )  whichPy = line )
                ; Who spoke decides what may be printed. Python's own failures
                ; are ASCII and safe to echo; Windows' "cannot find the file" is
                ; localised AND written in the OEM codepage (866 on a Russian
                ; Windows), which the Allegro console renders as mojibake. Two
                ; plain substrings rather than one alternation: rexMatchp's
                ; regex dialect is not worth betting a diagnosis on.
                when( rexMatchp( "Traceback" line )  pySpoke = t )
                when( rexMatchp( "Error" line )      pySpoke = t )
            )
            close( port )
        )
        errset( deleteFile( logFile ) )

        when( ok  return( t ) )

        ; Not OK. Lead with the good news so the user does not go hunting in the
        ; wrong place: the export itself worked, only the viewer failed to start.
        printf( "\n" )
        printf( "===== Simple 3D: the JSON was written, but Python did not start =====\n" )
        printf( "The intermediate JSON(s) ARE in:\n    %s\n" t_workDir )
        printf( "Nothing is wrong with the board or the export.\n\n" )
        ; Two cases, and only the first one prints the captured text - it is the
        ; one where Python itself answered, in ASCII. Anything else (an empty
        ; log, or Windows' own localised complaint in the OEM codepage) is
        ; reported in our own words instead of echoed as mojibake.
        cond(
            ( pySpoke
                printf( "Python (%s) failed this check:\n" exe )
                printf( "    import stepbuilder.core, tkinter\n\n" )
                ; Name the interpreter that actually answered. "python" is a
                ; name, not a program: installing anything that ships a Python
                ; (node.js does) can put a different one ahead of yours on PATH,
                ; and then the packages are missing because it is a different
                ; interpreter, not because they were uninstalled.
                when( whichPy != ""
                    printf( "The interpreter that ran was:\n    %s\n" whichPy )
                )
                printf( "It reported:\n%s\n" out )
            )
            ( t
                printf( "Windows could not run the interpreter at all:\n    %s\n\n" exe )
                printf( "That name is not on PATH and is not a valid full path -\n" )
                printf( "or it died before it could say anything.\n" )
            )
        )
        printf( "\nCheck, in this order:\n" )
        printf( "  1. Is that the Python you meant? A bare name is resolved by\n" )
        printf( "     PATH, so a newly installed Python can shadow the one your\n" )
        printf( "     packages are in. Pin it by FULL PATH in the \"allegro\"\n" )
        printf( "     section of simple3d_config.local.json, beside\n" )
        printf( "     simple3d_config.json - that file is yours and is never\n" )
        printf( "     overwritten by an update:\n" )
        printf( "         \"allegro\": { \"python\": \"C:/Python312/python.exe\",\n" )
        printf( "                      \"pythonw\": \"C:/Python312/pythonw.exe\" }\n" )
        printf( "     In use now:  python = \"%s\"   pythonw = \"%s\"\n"
                S3D_Python S3D_PythonW )
        printf( "  2. The dependency is installed FOR THAT INTERPRETER:\n" )
        printf( "         <that python.exe> -m pip install cadquery-ocp\n" )
        printf( "  3. The stepbuilder folder sits in S3D_ScriptDir = \"%s\"\n" S3D_ScriptDir )
        printf( "=====================================================================\n\n" )
        axlUIWPrint( nil
            "Simple 3D: JSON written OK - but Python could not start. See the console." )
        ; And say it where it cannot be missed. The console line above is the
        ; whole diagnosis, but the console can be closed, scrolled away or
        ; simply not looked at, and the failure it is reporting looks from the
        ; outside exactly like nothing happening - no window, no error, no
        ; clue. A blocking confirmer is what axlUIConfirm is for; errset because
        ; a courtesy dialog must never be able to fail the report itself, and
        ; Allegro's own "noconfirm" variable turns it into an immediate return
        ; for anyone running unattended.
        errset( axlUIConfirm( strcat(
            "Simple 3D: the JSON was exported, but the 3D window could not start.\n\n"
            "Python ran, but could not import what it needs (cadquery-ocp / tkinter).\n"
            "The full message, and how to fix it, are in the Allegro console." ) 'error ) )
        return( nil )
    )
)

; Launch the GUI without leaving a console window behind, and robustly for
; paths containing spaces.
;
; ONE line is handed to cmd, and every part of its shape is load-bearing. This
; used to be written into a throwaway .bat; it no longer needs to be, and the
; reasons are worth keeping because each one is a bug that was paid for:
;
;   1. The line must NOT begin with a quote. cmd strips the first and the last
;      quote of a /c command line, so a line starting with "python" loses its
;      quoting and a path with a space is split in two. That - not start - is
;      what broke a design path with a space (round 5); beginning with the bare
;      word "start" leaves every quote inside untouched. Measured, both ways.
;   2. start's FIRST argument is the window title. Passing "" for it is what
;      stops it from taking the quoted interpreter path as the title.
;   3. /D sets the working directory, which is what makes "-m stepbuilder"
;      resolve - it replaces the "cd /d" that used to need the file. Unlike a
;      "cd /d ... &&" chain it also survives if system() wraps the string in a
;      cmd of its own: a chain binds to the OUTER shell and the /D would be
;      silently lost.
;   4. start returns at once, so Allegro is not blocked, no console lingers,
;      and nothing has to be cleaned up afterwards.
;
; S3D_PythonW (pythonw.exe) runs with no console at all; if it is empty we fall
; back to S3D_Python but still detach so nothing stays on screen.
procedure( s3dLaunch( t_argTail )
    prog( ( exe )                           ; prog: return() below needs it
        exe = if( (S3D_PythonW != "") then S3D_PythonW else S3D_Python )
        errset( system( strcat(
            "cmd /c start \"\" /D \"" S3D_ScriptDir "\" \"" exe "\" " t_argTail ) ) )
        return( t )
    )
)

;=====================================================================
;  MENU INSERTION  (idiom from addeskd_v30.il, proven on this machine)
;=====================================================================

; Idempotent: without the guard, every re-load would add another copy. On a
; genuine menu rebuild our item is gone, the find fails, and it is re-inserted.
procedure( s3dMenuTrigger( t_menufile )
    let( ( anchor ( found nil ) )
        errset( found = axlUIMenuFind( nil S3D_CommandVisible ) )
        unless( found
            ; anchor on the existing "3D..." export item (command 3d_export_ui)
            anchor = axlUIMenuFind( nil "3d_export_ui" )
            when( anchor
                axlUIMenuInsert( anchor S3D_CommandVisible S3D_CommandName )
            )
        )
    )
)

axlCmdRegister( S3D_CommandName 's3dExportCommand ?cmdType "interactive" )
s3dMenuTrigger( "none" )
errset( axlTriggerClear( 'menu 's3dMenuTrigger ) )
axlTriggerSet( 'menu 's3dMenuTrigger )

; NO CALL AT LOAD TIME, deliberately. There was one here, and after it was
; installed Allegro crashed on startup, repeatedly, offering to recover a .sav
; (2026-08-04). Loading these files defines procedures and sets variables and
; does nothing else: a tool that can stop the editor from starting cannot be
; debugged from.
;
; Registering the open trigger is not doing work - it is asking to be called
; later, when a board is open and the database is in a state to be written to.
; TriggerClear first, like the menu trigger above, so a re-load does not stack
; up registrations.
errset( axlTriggerClear( 'open 's3dOpenTrigger ) )
errset( axlTriggerSet( 'open 's3dOpenTrigger ) )

when( axlVersion( 'version ) != 24.1
    s3dWarn( "Simple 3D: simple3d.il was tested under Allegro 24.1" )
)

; Self-test: confirm we can read the working directory. getWorkingDir is the
; one function not present in the project's API reference; if your install
; spells it differently, this prints exactly what to change and where.
let( ( ( ok nil ) )
    errset( ok = getWorkingDir() )
    unless( ok
        s3dWarn( "Simple 3D: getWorkingDir() failed. Edit s3dDesignDir() to use your install's working-directory function." )
    )
)

printf( "*** simple3d.il v1.0 loaded  (File -> Export -> %s) ***\n" S3D_CommandVisible )
