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
;  ONE folder, so both loads share the same base - match it to S3D_ScriptDir:
;      load("d:/Projects/OrCAD/Scripts/Simple3D/makeVariant3dIntermediates.il")  ; incl. fixes + MFRPN helpers
;      load("d:/Projects/OrCAD/Scripts/Simple3D/simple3d.il")                    ; this file
;
;  Follows the menu-insertion idiom from the user's own addeskd_v30.il
;  (idempotent find/insert + menu trigger + TriggerClear before TriggerSet).
;
;  version 1.0
;=====================================================================

;=====================================================================
;  SETTINGS
;
;  ONE setting lives here. Everything else is in simple3d_config.json, next to
;  this file - Python paths, the model library, the menu label, every GUI
;  default, and the silkscreen layer lists. Editing settings in three places
;  (this file, the GUI's own store, the layer config) was the arrangement
;  before; it is now one file that both halves of the tool read.
;
;  Why this one cannot move: the config is found relative to the project
;  folder, so the project folder has to be known before the config can be read.
;  That is the whole bootstrap, and it is why S3D_ScriptDir stays in source.
;
;  Plain assignment (=), NOT defvar: defvar only sets a value the first time
;  and is ignored on reload, so a user edit would silently not take effect.
;=====================================================================

; The Simple 3D project folder - the ONE folder that holds this whole tool:
; both .il files, simple3d_config.json AND the "stepbuilder" package sit here
; together. Used to launch Python without depending on the current directory
; (which is what caused the "No module named stepbuilder" error). This is the
; single path to match to wherever you unpacked the project; the load() lines
; in the header above use the same folder. If you named the folder something
; other than "Simple3D", change it here (and in those two load lines).
S3D_ScriptDir = "d:/Projects/OrCAD/Scripts/Simple3D"

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
            errset( cfg = s3dJsonRead( S3D_ConfigFile ) )
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
            else
                s3dWarn( sprintf( nil "Simple 3D: could not parse %s; using built-in settings."
                                  S3D_ConfigFile ) )
            )
        )
        t
    )
)

s3dLoadSettings()

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
;  the form on screen. s3dMeterOn therefore destroys any stale meter before
;  creating its own, which clears one away at the next export.
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

        ; Pick up config edits without reloading the SKILL files.
        errset( s3dLoadSettings() )

        designName = axlCurrentDesign()
        unless( designName
            axlUIWPrint( nil "Simple 3D: no design is open." )
            return( nil )
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
        makeVariant3dIntermediates( cadDir list( 0.0 0.4 0.0 )
                                    if( (S3D_ConfigFile != "") then S3D_ConfigFile else nil ) )

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
; Returns t to proceed, nil to abort. A fault in the check itself still cannot
; block a working setup: s3dExportCommand wraps this call in errset and launches
; anyway if it errors. There is no separate fail-open branch here any more - the
; one that existed was for a pre-flight file that could not be written, and
; nothing is written now.
procedure( s3dPreflight( t_workDir )
    ; prog locals must be bare symbols - the (var value) init form is let-only
    ; syntax and prog rejects it with "local vars must be symbol". Hence the
    ; explicit assignments below.
    prog( ( exe logFile port line ok pySpoke out )
        ok      = nil
        pySpoke = nil
        out     = ""
        exe = if( (S3D_Python != "") then S3D_Python else S3D_PythonW )
        logFile = strcat( t_workDir "/_simple3d_preflight.txt" )

        ; Importing stepbuilder.core pulls in OCP, the heavy dependency that is
        ; usually the missing one; tkinter is what the GUI itself needs.
        errset( system( strcat(
            "cmd /c start /B /WAIT \"\" /D \"" S3D_ScriptDir "\" \"" exe
            "\" -c \"import stepbuilder.core, tkinter; print('S3D_OK')\" > \""
            logFile "\" 2>&1" ) ) )

        port = infile( logFile )
        when( port
            while( gets( line port )
                out = strcat( out line )
                when( rexMatchp( "S3D_OK" line )  ok = t )
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
                printf( "It reported:\n%s\n" out )
            )
            ( t
                printf( "Windows could not run the interpreter at all:\n    %s\n\n" exe )
                printf( "That name is not on PATH and is not a valid full path -\n" )
                printf( "or it died before it could say anything.\n" )
            )
        )
        printf( "\nCheck, in this order:\n" )
        printf( "  1. Python is installed and the paths at the top of simple3d.il\n" )
        printf( "     are right:  S3D_Python = \"%s\"   S3D_PythonW = \"%s\"\n"
                S3D_Python S3D_PythonW )
        printf( "  2. The dependency is installed:   pip install cadquery-ocp\n" )
        printf( "  3. The stepbuilder folder sits in S3D_ScriptDir = \"%s\"\n" S3D_ScriptDir )
        printf( "=====================================================================\n\n" )
        axlUIWPrint( nil
            "Simple 3D: JSON written OK - but Python could not start. See the console." )
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
