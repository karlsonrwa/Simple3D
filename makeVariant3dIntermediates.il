;=====================================================================
;  makeVariant3dIntermediates.il - loads the Simple 3D exporter
;
;  The exporter itself lives in nine parts under skill/ since round 76
;  (plan D6), cut from this file with every procedure and comment as it was:
;
;    skill/s3d_util.il       console messages, folders, the subclass sweep
;    skill/s3d_json.il       s3dJsonQuote, the JSON reader, the config pair
;    skill/s3d_props.il      NO_STEP_EXPORT / ALWAYS_STEP_EXPORT, embedded models
;    skill/s3d_variants.il   Variants.lst (the upstream parser), what a variant exports
;    skill/s3d_geometry.il   segments, arcs, slots, the board contour, pin holes
;    skill/s3d_stackup.il    board thickness, stackups, zones, layer shapes
;    skill/s3d_bends.il      bend lines and bend areas
;    skill/s3d_silk.il       the silkscreen: config, collection, clipping, writer
;    skill/s3d_export.il     symbolReturn3DElements, makePcb, the JSON writer
;
;  This file stays, so an allegro.ilinit or a by-hand session that loads it
;  keeps working; simple3d.il loads it itself when it has not been loaded yet,
;  so a single  load("<folder>/simple3d.il")  is enough.
;
;  USAGE (unchanged)
;    makeVariant3dIntermediates( outputDir [ pcbColor ] [ configFile ] )
;
;  Where the parts are, in order: S3D_ExporterDir when the session set it
;  before loading (the headless runner and the tests do), else the folder this
;  file was loaded from, else the Allegro variable SIMPLE3D_DIR. No path lives
;  in this file - see simple3d.il for why.
;=====================================================================

S3D_ExporterParts = list( "s3d_util" "s3d_json" "s3d_props" "s3d_variants" "s3d_geometry"
                          "s3d_stackup" "s3d_bends" "s3d_silk" "s3d_export" )

; Captured at LOAD time, while the port reading this file still exists - the
; only moment SKILL can be asked. errset: piport / get_filename are core
; names, and nil simply means "not this way".
S3D_ExporterLoadedFrom = nil
errset( S3D_ExporterLoadedFrom = get_filename( piport ) )

; The folder part of a path, scanning for the last separator - the same rule
; as s3dFolderOf in simple3d.il, which is not loaded yet when this runs.
procedure( s3dExporterFolderOf( t_path )
    let( ( ( cut 0 ) c )
        unless( stringp( t_path )  t_path = "" )
        for( i 1 strlen( t_path )
            c = substring( t_path i 1 )
            when( (c == "/") || (c == "\\")  cut = i )
        )
        if( cut > 1 then
            buildString( parseString( substring( t_path 1 cut - 1 ) "\\" ) "/" )
        else
            ""
        )
    )
)

procedure( s3dLoadExporter()
    let( ( dir value )
        dir = ""
        when( boundp( 'S3D_ExporterDir ) && stringp( S3D_ExporterDir ) && (S3D_ExporterDir != "")
            dir = S3D_ExporterDir
        )
        when( dir == ""  dir = s3dExporterFolderOf( S3D_ExporterLoadedFrom ) )
        when( dir == ""
            value = nil
            errset( value = axlGetVariable( "SIMPLE3D_DIR" ) )
            when( stringp( value ) && (value != "")
                dir = buildString( parseString( value "\\" ) "/" )
            )
        )
        if( dir == "" then
            printf( "Simple 3D: cannot tell where makeVariant3dIntermediates.il was loaded from. Put   set SIMPLE3D_DIR = <the folder holding it>   in your pcbenv/env and reload; nothing is loaded until then.\n" )
            nil
        else
            foreach( part S3D_ExporterParts
                load( strcat( dir "/skill/" part ".il" ) )
            )
            S3D_ExporterLoaded = t
            t
        )
    )
)

s3dLoadExporter()
