;=====================================================================
;  probe_launch.il - DIAGNOSTIC for R2n-14, R2n-15, R2n-17 and R2n-18 of
;  the 28.10.2026 review (round 129): what the pre-flight check reads in
;  the logs Python leaves, which programs Windows can find, and where a
;  board on a UNC path writes - in Allegro's own SKILL, and with NO
;  system(): nothing is started. A console program started from Allegro
;  gets a console of its own, which Windows Terminal opens on the owner's
;  desktop (round 115), so the logs are made beforehand by
;  build/fix-2026-10-31/r129/launch_cases.py, on a desktop of its own.
;
;  s3dProbeLaunch - loads simple3d.il from S3D_PROBE_TREE (HEAD's copy or
;      the working tree; the file's last lines put a menu item in, which a
;      session with no window may refuse - hence errset), then prints:
;      * every log named in S3D_PROBE_LOGS (";" between paths): each line as
;        gets hands it back (%L), the verdict of the rule round 128 had - a
;        line holding S3D_OK anywhere is success - and, where the tree has
;        it, s3dPreflightRead's;
;      * isFile and isDir of every path in S3D_PROBE_FILES, and, where the
;        tree has it, s3dProgramFile of every name in S3D_PROBE_PROGRAMS;
;      * s3dSlashes, s3dFolderOf, s3dExporterFolderOf and s3dResolveCadDir of
;        every folder in S3D_PROBE_DIRS, then whether a folder named after the
;        first part of a UNC path appeared in the working directory -
;        s3dMakeDirs walks the path it is given, and a walk that lost the "//"
;        makes a relative one; then s3dMakeDirs of every folder in
;        S3D_PROBE_MAKE, folders that do not exist yet;
;      * s3dDesignFolder, s3dDesignDir and s3dResolveCadDir( s3dDesignDir() )
;        of the board it runs on - opened by a UNC path, the case at hand;
;      * s3dPreflightDialog's text for each case, where the tree has it.
;
;    set S3D_PROBE_TREE=<tree>
;    set S3D_PROBE_LOGS=<log>;<log>
;    set S3D_PROBE_FILES=<path>;<path>
;    set S3D_PROBE_PROGRAMS=<name>;<name>
;    set S3D_PROBE_DIRS=<folder>;<folder>
;    set S3D_PROBE_MAKE=<folder>;<folder>
;    python build/fix-2026-10-31/r129/run_unc.py ...   (opens the board by its UNC path)
;  REQUIRES: simple3d.il, which loads makeVariant3dIntermediates.il, and
;  REQUIRES: s3d_userprop_test.il, which s3dProbeUserProp loads
;=====================================================================

procedure( s3dProbeLaunchList( t_var )
    let( ( value )
        value = getShellEnvVar( t_var )
        if( stringp( value ) && (value != "") then parseString( value ";" ) else nil )
    )
)

procedure( s3dProbeLaunch()
    let( ( tree port line ok pySpoke whichPy got dir junk first )
        tree = getShellEnvVar( "S3D_PROBE_TREE" )
        printf( "S3DLAUNCH tree %L\n" tree )
        printf( "S3DLAUNCH load: %L\n" errset( load( strcat( tree "/simple3d.il" ) ) t ) )
        printf( "S3DLAUNCH working directory %L, PATHEXT %L\n" getWorkingDir() getShellEnvVar( "PATHEXT" ) )
        printf( "S3DLAUNCH defined: s3dPreflightRead %L, s3dProgramFile %L, s3dPreflightDialog %L\n"
                if( getd( 's3dPreflightRead ) then t else nil )
                if( getd( 's3dProgramFile ) then t else nil )
                if( getd( 's3dPreflightDialog ) then t else nil ) )
        drain( poport )

        ; R2n-14: the logs, line by line
        foreach( log s3dProbeLaunchList( "S3D_PROBE_LOGS" )
            printf( "S3DLAUNCH ==== log %s\n" log )
            ok = nil
            pySpoke = nil
            whichPy = ""
            port = infile( log )
            when( port
                while( gets( line port )
                    printf( "S3DLAUNCH   line %L\n" line )
                    ; round 128's rule, word for word
                    when( rexMatchp( "S3D_OK" line )  ok = t )
                    when( rexMatchp( "S3D_PY " line )  whichPy = line )
                    when( rexMatchp( "Traceback" line )  pySpoke = t )
                    when( rexMatchp( "Error" line )      pySpoke = t )
                )
                close( port )
            )
            printf( "S3DLAUNCH   round 128's rule: ok %L, pySpoke %L, whichPy %L\n" ok pySpoke whichPy )
            when( getd( 's3dPreflightRead )
                got = nil
                errset( got = s3dPreflightRead( log ) t )
                printf( "S3DLAUNCH   s3dPreflightRead: ok %L, pySpoke %L, whichPy %L\n"
                        car( got ) cadr( got ) caddr( got ) )
            )
            drain( poport )
        )

        ; R2n-18: what is there to start
        foreach( path s3dProbeLaunchList( "S3D_PROBE_FILES" )
            printf( "S3DLAUNCH file %L: isFile %L, isDir %L\n" path isFile( path ) isDir( path ) )
        )
        when( getd( 's3dProgramFile )
            foreach( name s3dProbeLaunchList( "S3D_PROBE_PROGRAMS" )
                got = 'error
                errset( got = s3dProgramFile( name ) t )
                printf( "S3DLAUNCH program %L -> %L\n" name got )
            )
        )
        drain( poport )

        ; R2n-17: folders, and what s3dMakeDirs leaves in the working directory
        foreach( d s3dProbeLaunchList( "S3D_PROBE_DIRS" )
            printf( "S3DLAUNCH ==== folder %L\n" d )
            printf( "S3DLAUNCH   s3dSlashes %L\n" s3dSlashes( d ) )
            printf( "S3DLAUNCH   s3dFolderOf %L\n" s3dFolderOf( d ) )
            printf( "S3DLAUNCH   s3dExporterFolderOf of a file in it %L\n" s3dExporterFolderOf( strcat( d "/x.il" ) ) )
            got = 'error
            errset( got = s3dResolveCadDir( d ) t )
            printf( "S3DLAUNCH   s3dResolveCadDir %L\n" got )
            first = car( parseString( s3dSlashes( d ) "/" ) )
            junk = when( stringp( first ) && isDir( first ) first )
            printf( "S3DLAUNCH   a relative folder %L in the working directory: %L\n" first junk )
            drain( poport )
        )

        ; R2n-17: s3dMakeDirs on folders that do not exist yet
        foreach( d s3dProbeLaunchList( "S3D_PROBE_MAKE" )
            got = 'error
            errset( got = s3dMakeDirs( d ) t )
            first = car( parseString( s3dSlashes( d ) "/" ) )
            printf( "S3DLAUNCH make %L -> %L, isDir %L; a relative folder %L in the working directory: %L\n"
                    d got isDir( d ) first when( stringp( first ) && isDir( first ) first ) )
        )
        drain( poport )

        ; R2n-17: the board itself, opened by a UNC path
        printf( "S3DLAUNCH ==== the board\n" )
        printf( "S3DLAUNCH   axlGetDrawingName %L\n" axlGetDrawingName() )
        dir = nil
        errset( dir = s3dDesignFolder() t )
        printf( "S3DLAUNCH   s3dDesignFolder %L\n" dir )
        dir = nil
        errset( dir = s3dDesignDir() t )
        printf( "S3DLAUNCH   s3dDesignDir %L\n" dir )
        got = 'error
        errset( got = s3dResolveCadDir( dir ) t )
        printf( "S3DLAUNCH   s3dResolveCadDir( s3dDesignDir() ) %L\n" got )
        first = car( parseString( s3dSlashes( dir ) "/" ) )
        junk = when( stringp( first ) && isDir( first ) first )
        printf( "S3DLAUNCH   a relative folder %L in the working directory: %L\n" first junk )
        drain( poport )

        ; R2n-15: the dialog's words, per case
        when( getd( 's3dPreflightDialog )
            foreach( case '( missing python silent )
                printf( "S3DLAUNCH dialog %L:\n%s\nS3DLAUNCH end of dialog\n"
                        case s3dPreflightDialog( case "C:/Python314/pythonw.exe" ) )
            )
        )
        t
    )
)

; R2-11 of the 23.10.2026 review: what tools/s3d_userprop_test.il writes, in
; a session with a saved board and in one with none. Loads simple3d.il and the
; hand test from S3D_PROBE_TREE, prints what s3dRealDesign answers, the user
; property dictionary, then calls s3dPropAdd and s3dPropRemove on the refdes
; S3D_PROBE_REFDES (C1 when unset) and prints the dictionary again. The board
; is the runner's scratch copy and is never saved.
procedure( s3dProbeUserProp()
    let( ( tree refdes dict )
        tree = getShellEnvVar( "S3D_PROBE_TREE" )
        refdes = getShellEnvVar( "S3D_PROBE_REFDES" )
        unless( stringp( refdes ) && (refdes != "")  refdes = "C1" )
        printf( "S3DPROP tree %L\n" tree )
        printf( "S3DPROP load simple3d.il: %L\n" errset( load( strcat( tree "/simple3d.il" ) ) t ) )
        printf( "S3DPROP axlCurrentDesign %L, axlGetDrawingName %L, s3dRealDesign %L\n"
                axlCurrentDesign() axlGetDrawingName() s3dRealDesign() )
        dict = nil
        errset( dict = axlDBGetPropDict( 'user ) t )
        printf( "S3DPROP user dictionary before: %L\n" dict )
        printf( "S3DPROP load the hand test: %L\n" errset( load( strcat( tree "/tools/s3d_userprop_test.il" ) ) t ) )
        drain( poport )
        printf( "S3DPROP s3dPropAdd( %L ) -> %L\n" refdes errset( s3dPropAdd( refdes ) t ) )
        dict = nil
        errset( dict = axlDBGetPropDict( 'user ) t )
        printf( "S3DPROP user dictionary after the add: %L\n" dict )
        printf( "S3DPROP s3dPropRemove( %L ) -> %L\n" refdes errset( s3dPropRemove( refdes ) t ) )
        drain( poport )
        t
    )
)
