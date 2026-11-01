;=====================================================================
;  probe_units.il - round 128, R1-3 of the 23.10.2026 review: the
;  export refuses a design in any unit but millimetres, before anything
;  is written.
;
;  s3dProbeUnits - on the runner's scratch copy of a board: the units as
;      Allegro reports them, the export into S3D_PROBE_OUT/mm with the
;      board as it is, then the copy's units changed to mils (the copy is
;      never saved) and the export into S3D_PROBE_OUT/mils; each export
;      inside errset, so a refusal prints its message and the probe goes
;      on. What landed in each folder is listed by the caller.
;
;    set S3D_PROBE_OUT=<a folder>
;    python tools/run_probe.py --with-exporter tools/probes/probe_units.il s3dProbeUnits <board>
;  REQUIRES: makeVariant3dIntermediates.il
;=====================================================================

procedure( s3dProbeUnits()
    let( ( out res )
        out = getShellEnvVar( "S3D_PROBE_OUT" )
        printf( "S3DUNITS out %L\n" out )
        printf( "S3DUNITS units before: %L\n" axlDBGetDesignUnits() )
        drain( poport )
        res = errset( makeVariant3dIntermediates( strcat( out "/mm" ) ) t )
        printf( "S3DUNITS export as it is: %L\n" res )
        res = errset( axlDBChangeDesignUnits( "mils" 2 ) t )
        printf( "S3DUNITS change to mils: %L\n" res )
        printf( "S3DUNITS units after: %L\n" axlDBGetDesignUnits() )
        drain( poport )
        res = errset( makeVariant3dIntermediates( strcat( out "/mils" ) ) t )
        printf( "S3DUNITS export in mils: %L\n" res )
        drain( poport )
        t
    )
)
