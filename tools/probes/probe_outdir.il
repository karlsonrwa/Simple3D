;=====================================================================
;  probe_outdir.il - DIAGNOSTIC for R2-3 of the 23.10.2026 review
;  (round 115): where the export command writes when Allegro's working
;  directory is not the folder of the open board - the state File > Open
;  leaves with "Change directory" unticked (browser_nodircheck).
;
;  s3dProbeOutDir - writes nothing but what the export command itself
;      writes. Loads simple3d.il from the tree named by S3D_PROBE_TREE,
;      prints Allegro's working directory, the drawing's path and its folder,
;      moves the working directory to S3D_PROBE_WD (changeWorkingDir) and
;      prints it again, points S3D_ConfigFile at S3D_PROBE_CONFIG, replaces
;      s3dPreflight with a stub that starts nothing and answers nil, and runs
;      s3dExportCommand: it writes the JSON and stops where a failed check
;      stops it, before s3dLaunch. No program is started at all - the real
;      check runs cmd through system(), and on a machine whose default
;      terminal is Windows Terminal a console started by Allegro (a GUI
;      program, no console of its own to lend) opens a Terminal window on the
;      user's screen whatever desktop Allegro is on (round 115). If the stub
;      does not take, the command is not run. The console says where the
;      command wrote; the runner (build/fix-2026-10-31/r115/scene.py) lists
;      where the JSON landed.
;
;    set S3D_PROBE_TREE=<a whole checkout>
;    set S3D_PROBE_WD=<the folder to make the working directory>
;    set S3D_PROBE_CONFIG=<a config for the export>
;    allegro -nograph -s <a .scr that loads this and calls s3dProbeOutDir()> <board>
;  REQUIRES: simple3d.il
;  REQUIRES: makeVariant3dIntermediates.il
;=====================================================================

procedure( s3dProbeOutDir()
    prog( ( tree wd config cwd drawing )
        tree = getShellEnvVar( "S3D_PROBE_TREE" )
        wd = getShellEnvVar( "S3D_PROBE_WD" )
        config = getShellEnvVar( "S3D_PROBE_CONFIG" )
        printf( "S3DOUT tree %L, wd %L, config %L\n" tree wd config )
        printf( "S3DOUT noconfirm set: %L\n" axlSetVariable( "noconfirm" t ) )
        drain( poport )
        ; errset: the file's last lines put a menu item in, which a session
        ; with no window may refuse - the procedures above them are defined
        ; by then all the same.
        printf( "S3DOUT load: %L\n" errset( load( strcat( tree "/simple3d.il" ) ) t ) )
        S3D_ProbeStubbed = nil
        errset( putd( 's3dPreflight
                      lambda( ( t_workDir )
                          S3D_ProbeStubbed = t
                          printf( "S3DOUT pre-flight check stubbed (%L): nothing started\n" t_workDir )
                          nil ) ) t )
        errset( s3dPreflight( "the stub's own test" ) t )
        unless( S3D_ProbeStubbed
            printf( "S3DOUT the stub did not take: the export command is NOT run\n" )
            return( nil )
        )
        S3D_ProbeStubbed = nil
        cwd = nil
        errset( cwd = getWorkingDir() )
        drawing = nil
        errset( drawing = axlGetDrawingName() )
        printf( "S3DOUT at start: working directory %L, drawing %L, its folder %L\n"
                cwd drawing s3dDesignFolder() )
        printf( "S3DOUT changeWorkingDir: %L\n" errset( changeWorkingDir( wd ) t ) )
        cwd = nil
        errset( cwd = getWorkingDir() )
        printf( "S3DOUT now: working directory %L; s3dDesignDir says %L\n"
                cwd s3dDesignDir() )
        drain( poport )
        S3D_ConfigFile = config
        printf( "S3DOUT s3dExportCommand: %L\n" errset( s3dExportCommand() t ) )
        drain( poport )
        return( t )
    )
)
