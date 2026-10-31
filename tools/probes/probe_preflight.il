;=====================================================================
;  probe_preflight.il - DIAGNOSTIC for R2-2 of the 23.10.2026 review
;  (round 114): which interpreter s3dPreflight checks, in Allegro's own
;  system(), against the one s3dLaunch would start.
;
;  s3dProbePreflight - read-only. Loads simple3d.il from the tree named by
;      S3D_PROBE_TREE (a whole checkout: it brings its own exporter, config
;      and stepbuilder package, so an older tree can be judged beside this
;      one), points S3D_ScriptDir at that tree, sets Allegro's noconfirm so
;      the failure dialog returns at once, and then for every case in
;      S3D_PROBE_CASES - "label|python|pythonw" joined by ";", an empty
;      pythonw left out - sets S3D_Python and S3D_PythonW, calls
;      s3dPreflight on S3D_PROBE_OUT and prints what it returned and, where
;      the tree has it, the interpreter s3dWindowPython names. s3dLaunch is
;      never called: no window opens.
;
;    set S3D_PROBE_TREE=<tree>
;    set S3D_PROBE_OUT=<folder>
;    set S3D_PROBE_CASES=good|C:/Python314/python.exe|C:/Python314/pythonw.exe;...
;    python tools/run_probe.py tools/probes/probe_preflight.il s3dProbePreflight input/<board>.brd
;  REQUIRES: simple3d.il
;=====================================================================

procedure( s3dProbePreflight()
    let( ( tree out cases fields label py pyw ok which )
        tree = getShellEnvVar( "S3D_PROBE_TREE" )
        out = getShellEnvVar( "S3D_PROBE_OUT" )
        cases = getShellEnvVar( "S3D_PROBE_CASES" )
        printf( "S3DPRE tree %L, out %L\n" tree out )
        drain( poport )
        printf( "S3DPRE noconfirm set: %L\n" axlSetVariable( "noconfirm" t ) )
        ; errset: the file's last lines put a menu item in, which a session
        ; with no window may refuse - the procedures above them are defined
        ; by then all the same.
        printf( "S3DPRE load: %L\n" errset( load( strcat( tree "/simple3d.il" ) ) t ) )
        S3D_ScriptDir = tree
        printf( "S3DPRE S3D_ScriptDir %s; s3dPreflight defined: %L; s3dWindowPython defined: %L\n"
                S3D_ScriptDir if( getd( 's3dPreflight ) then t else nil )
                if( getd( 's3dWindowPython ) then t else nil ) )
        drain( poport )
        foreach( case parseString( cases ";" )
            fields = parseString( case "|" )
            label = nth( 0 fields )
            py = nth( 1 fields )
            pyw = if( length( fields ) > 2 then nth( 2 fields ) else "" )
            S3D_Python = py
            S3D_PythonW = pyw
            which = "-"
            when( getd( 's3dWindowPython )  which = s3dWindowPython() )
            printf( "S3DPRE ==== case %s: python %s, pythonw %L, the window's %L\n"
                    label py pyw which )
            drain( poport )
            ok = 'error
            errset( ok = s3dPreflight( out ) )
            printf( "S3DPRE case %s -> %L\n" label ok )
            drain( poport )
        )
        t
    )
)
