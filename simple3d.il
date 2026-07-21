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
;  SETTINGS  - edit these to taste.
;
;  Plain assignment (=), NOT defvar: defvar only sets a value the first time
;  and is ignored on reload or if the variable already exists, so a user edit
;  would silently not take effect. With = the value in this file always wins
;  when the file is loaded.
;=====================================================================

; The Simple 3D project folder - the ONE folder that holds this whole tool:
; both .il files AND the "stepbuilder" package sit here together. Used to launch
; Python without depending on the current directory (which is what caused the
; "No module named stepbuilder" error). This is the single path to match to
; wherever you unpacked the project; the load() lines in the header above use
; the same folder. If you named the folder something other than "Simple3D",
; change it here (and in those two load lines).
S3D_ScriptDir = "d:/Projects/OrCAD/Scripts/Simple3D"

; Python launcher. "python" if it is on PATH; otherwise a full path such as
; "c:/Python312/python.exe".
S3D_Python = "python"

; Console-less Python launcher (pythonw.exe). When set, the GUI opens with NO
; console window and the launching cmd window closes immediately. Leave "" to
; use S3D_Python instead (still detached, but a brief console may flash).
; Typical value: "c:/Python312/pythonw.exe", or just "pythonw" if on PATH.
S3D_PythonW = "pythonw"

; Folder that holds the footprint STEP models referenced by PKGDEF_STEP_FILE.
; This is a shared 3D-model library, so it intentionally sits OUTSIDE the
; project folder above - it is not part of this tool. If empty, the GUI
; defaults it to the output folder; set it if your models live in a fixed spot.
S3D_ModelLibDir = "d:/Projects/OrCAD/CIS/3D"

; Default board colour pre-selected in the GUI. Must be one of the theme names
; in colors.py: Black Blue Dark_green Green Purple Red White Yellow.
S3D_DefaultColor = "Dark_green"

; MFRPN DISABLED (property attachment unreliable); kept for future re-enable.
; If t, abort the export when an exportable component (one that has a STEP
; model) has no MFRPN property. If nil, warn and continue - mechanicals and
; fiducials legitimately lack MFRPN, so nil is the safe default.
; S3D_StrictMfrPn = nil

; Menu label and internal command name.
S3D_CommandVisible = "Simple 3D"
S3D_CommandName = "simple_3d_export"

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

; Decide where the JSON and STEP go.
;
; Historically the script author keeps brd files in a  pcb  folder and puts
; mechanical output in a sibling  cad  folder (…/rev/pcb -> …/rev/cad). So:
;   * if the design sits in a  pcb  folder AND a sibling  cad  folder exists,
;     use  cad ;
;   * otherwise (any other structure, or no  cad  folder) write next to the brd
;     itself, in the design's own folder - not everyone uses the pcb/cad layout.
; The output folder is always created if missing.
; Decide where the JSON and STEP go, given the design's own folder.
;
; The author's historical layout is  root/rev/pcb  for the .brd and
; root/rev/cad  for the mechanical / 3D output, so when the design sits in a
; "pcb" folder that has a sibling "cad", output goes to "cad". For any other
; layout - no "pcb" folder, or a "pcb" folder without a "cad" sibling - output
; goes into the SAME folder as the .brd, so the tool works regardless of how
; the project is organised.
procedure( s3dResolveCadDir( t_designDir )
    let( ( parts n leaf parent cad )
        t_designDir = s3dSlashes( t_designDir )
        parts = parseString( t_designDir "/" )
        n = length( parts )
        leaf = if( n >= 1 then nth( n - 1 parts ) else nil )

        if( leaf && (upperCase( leaf ) == "PCB") then
            ; …/rev/pcb -> candidate …/rev/cad
            parent = buildString( headList( parts n - 1 ) "/" )
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

; headList( lst n ) -> first n elements of lst (helper; SKILL has no builtin).
procedure( headList( lst x_n )
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
;  THE COMMAND
;=====================================================================

; NOTE: prog, not let. SKILL's return() is only legal inside a prog block - in a
; let it raises "return can only be used within a prog". prog also means the
; body's last value is NOT the result: every exit has to be an explicit return().
procedure( s3dExportCommand()
    prog( ( designName designDir cadDir check noMfrPn noModel modelDir argTail pyOk )

        designName = axlCurrentDesign()
        unless( designName
            axlUIWPrint( nil "Simple 3D: no design is open." )
            return( nil )
        )

        designDir = s3dDesignDir()
        cadDir = s3dResolveCadDir( designDir )
        printf( "Simple 3D: JSON + STEP output -> %s\n" cadDir )

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
        printf( "Simple 3D: writing intermediate JSON...\n" )
        makeVariant3dIntermediates( cadDir )

        ; --- can Python actually start? -------------------------------
        ; Done AFTER the JSON exists, so a broken Python install still leaves the
        ; user with a usable export, and the message can say so. Costs a few
        ; seconds (importing OCP is slow) - worth it against a silent no-op.
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
            return( nil )
        )

        ; --- launch the GUI, prefilled --------------------------------
        ; Open the GUI with paths already set. The GUI lets the user pick colour
        ; and z-datum and press Generate; with several variant JSONs it builds
        ; all of them. step_dir is the model library (or cad if unset).
        modelDir = if( (S3D_ModelLibDir != "") then S3D_ModelLibDir else cadDir )

        ; Build the argument tail (everything AFTER the interpreter). The
        ; launcher prepends python/pythonw and writes it into a .bat so cmd
        ; parses the quoted paths natively (no nesting through "start", which
        ; mangled paths containing spaces).
        argTail = strcat(
            "-m stepbuilder --gui "
            "--step-dir \"" modelDir "\" "
            "--json-dir \"" cadDir "\" "
            "--output-dir \"" cadDir "\" "
            "--brd-name \"" designName "\" "
            "--dated-name "
            "--color \"" S3D_DefaultColor "\""
        )

        printf( "Simple 3D: launching GUI (%s)\n" argTail )
        s3dLaunch( argTail )

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
; Success is signalled by a sentinel the check prints, not by an empty log: some
; installs emit deprecation warnings on stderr even when the import succeeds.
;
; Returns t to proceed, nil to abort. Fails OPEN: if the check itself cannot be
; written or run, it says so and returns t rather than blocking a working setup.
procedure( s3dPreflight( t_workDir )
    ; prog locals must be bare symbols - the (var value) init form is let-only
    ; syntax and prog rejects it with "local vars must be symbol". Hence the
    ; explicit assignments below.
    prog( ( exe batPath logFile port line ok noExe out )
        ok    = nil
        noExe = nil
        out   = ""
        exe = if( (S3D_Python != "") then S3D_Python else S3D_PythonW )
        batPath = strcat( t_workDir "/_simple3d_preflight.bat" )
        logFile = strcat( t_workDir "/_simple3d_preflight.txt" )

        port = outfile( batPath )
        unless( port
            printf( "Simple 3D: cannot write the preflight check to %s - skipping it.\n" batPath )
            return( t )
        )
        ; cd /d so "stepbuilder" resolves exactly as it will at launch time.
        ; Importing stepbuilder.core pulls in OCP, the heavy dependency that is
        ; usually the missing one; tkinter is what the GUI itself needs.
        fprintf( port "@echo off\r\n" )
        fprintf( port "cd /d \"%s\"\r\n" S3D_ScriptDir )
        fprintf( port "\"%s\" -c \"import stepbuilder.core, tkinter; print('S3D_OK')\" > \"%s\" 2>&1\r\n"
                 exe logFile )
        ; cmd returns 9009 for "command not found", and its message for that is
        ; localised AND written in the OEM codepage (866 on a Russian Windows),
        ; which the Allegro console renders as mojibake. Flag the case with an
        ; ASCII marker instead and print our own English text for it below.
        fprintf( port "if errorlevel 9009 echo S3D_NOEXE>>\"%s\"\r\n" logFile )
        close( port )

        errset( system( strcat( "cmd /c \"" batPath "\"" ) ) )
        errset( deleteFile( batPath ) )

        port = infile( logFile )
        when( port
            while( gets( line port )
                out = strcat( out line )
                when( rexMatchp( "S3D_OK" line )     ok = t )
                when( rexMatchp( "S3D_NOEXE" line )  noExe = t )
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
        ; Three cases, and only the last one prints the captured text. Windows'
        ; own error messages come back localised in the OEM codepage and arrive
        ; here as mojibake, so the case we can identify (interpreter not found)
        ; is reported in our own words. Python's own tracebacks are ASCII.
        cond(
            ( noExe
                printf( "Windows could not run the interpreter at all:\n    %s\n\n" exe )
                printf( "That name is not on PATH and is not a valid full path.\n" )
            )
            ( (out == "")
                printf( "The check produced no output at all, which usually also\n" )
                printf( "means the interpreter was not found:\n    %s\n" exe )
            )
            ( t
                printf( "Python (%s) failed this check:\n" exe )
                printf( "    import stepbuilder.core, tkinter\n\n" )
                printf( "It reported:\n%s\n" out )
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
; Two problems the naive "cmd /c start ... python ..." had:
;   1. start treats the first quoted token as the window title, so a quoted
;      path with a space got mis-split. Fixed by writing a .bat and running it,
;      so cmd parses the quoted args from the file natively.
;   2. python -m stepbuilder --gui blocks until the window closes, so the cmd
;      window stayed open the whole time. Fixed by having the .bat "start" the
;      interpreter detached and then exit, which closes the console.
;
; S3D_PythonW (pythonw.exe) runs with no console at all; if it is empty we fall
; back to S3D_Python but still detach so the launching window closes promptly.
procedure( s3dLaunch( t_argTail )
    prog( ( batPath port launchLine )       ; prog: return() below needs it
        batPath = strcat( S3D_ScriptDir "/_simple3d_launch.bat" )
        port = outfile( batPath )
        unless( port
            ; Read-only or unreachable install dir. Without this the whole
            ; procedure was a silent no-op: JSON on disk, no window, no message.
            printf( "\nSimple 3D: the JSON was written, but the launcher could not be created:\n" )
            printf( "    %s\n" batPath )
            printf( "S3D_ScriptDir is not writable. Point it at a writable folder,\n" )
            printf( "or start the GUI by hand:\n    cd /d \"%s\"\n    %s %s\n\n"
                    S3D_ScriptDir S3D_Python t_argTail )
            axlUIWPrint( nil
                "Simple 3D: JSON written OK - but the launcher could not be created. See the console." )
            return( nil )
        )
        fprintf( port "@echo off\r\n" )
        fprintf( port "cd /d \"%s\"\r\n" S3D_ScriptDir )
        if( (S3D_PythonW != "") then
            ; pythonw: no console, detached, window closes immediately.
            launchLine = strcat( "start \"\" \"" S3D_PythonW "\" " t_argTail )
        else
            ; plain python, but detached via start so this window still exits.
            launchLine = strcat( "start \"\" \"" S3D_Python "\" " t_argTail )
        )
        fprintf( port "%s\r\n" launchLine )
        ; The GUI is launched detached (start ...), so by the time this line
        ; runs the interpreter already has its own arguments and no longer
        ; needs the .bat. Delete it so it does not linger. The
        ; "(goto) 2>nul & del" idiom lets cmd release its handle on the file
        ; before deleting, avoiding a "file in use" failure; "%~f0" is this
        ; batch file's own full path.
        fprintf( port "(goto) 2>nul & del \"%%~f0\"\r\n" )
        close( port )
        errset( system( strcat( "cmd /c \"" batPath "\"" ) ) )
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
    printf( "!WARNING - simple3d.il was tested under Allegro 24.1\n" )
)

; Self-test: confirm we can read the working directory. getWorkingDir is the
; one function not present in the project's API reference; if your install
; spells it differently, this prints exactly what to change and where.
let( ( ( ok nil ) )
    errset( ok = getWorkingDir() )
    unless( ok
        printf( "!WARNING - simple3d.il: getWorkingDir() failed. Edit s3dDesignDir()\n" )
        printf( "           to use your install's working-directory function.\n" )
    )
)

printf( "*** simple3d.il v1.0 loaded  (File -> Export -> %s) ***\n" S3D_CommandVisible )
