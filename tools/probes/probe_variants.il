;=====================================================================
;  probe_variants.il - DIAGNOSTIC ONLY. Reads the design, changes nothing.
;
;  "The Variants.lst export does not work" has four different causes and they
;  look identical from outside: one JSON where several were expected, or none.
;  This prints the four answers separately.
;
;    1. WHERE the exporter looks: beside the board, the folder holding the
;       .brd, which is where Variants.lst always lives. (Until round 47 it was
;       opened by its bare name and so resolved against Allegro's WORKING
;       directory; when the two differed the file was invisible and the export
;       quietly exported every component. The working directory is still printed
;       below, because other relative reads use it.)
;    2. WHETHER gdsysGetVariantInfo could parse it, and into how many variants.
;       A Variants.lst belonging to a different project parses into zero, and
;       the export then stops with a message rather than writing nothing.
;    3. WHICH refdes each variant installs, as the parser returns them.
;    4. WHAT the export would actually write: one JSON per variant, named
;       <design>_<variant>.json, lower-cased, into the cad folder.
;
;  This probe reports ON the exporter, so it calls into it rather than
;  re-implementing what it is meant to be checking. The line below is what tells
;  tools/skill_checks.py to expect that.
;
;  REQUIRES: makeVariant3dIntermediates.il
;
;  Usage:  load("<path>/probe_variants.il")   then   s3dProbeVariants()
;=====================================================================

procedure( s3dProbeVariants()
    let( ( cwd here info symbolList altParts count names installed nSyms )

        printf( "\n===== 1. WHERE THE EXPORTER LOOKS =====\n" )
        printf( "  current design            : %L\n" axlCurrentDesign() )
        errset( here = axlGetDrawingName() )
        printf( "  board file                : %L\n" here )
        printf( "  its folder                : %L\n" s3dDesignFolder() )
        ; The one that decides. Asked through the exporter's own helper, so the
        ; probe cannot answer a question the export would answer differently.
        printf( "  Variants.lst path         : %L\n" s3dVariantFilePath() )
        printf( "  found there               : %L\n" isFile( s3dVariantFilePath() ) )
        ; Still worth printing: the config file and other relative reads resolve
        ; against it, and it is what Variants.lst used to be resolved against.
        cwd = nil
        errset( cwd = getWorkingDir() )
        printf( "  (working directory        : %L, Variants.lst there: %L)\n"
                cwd isFile( "Variants.lst" ) )
        unless( isFile( s3dVariantFilePath() )
            printf( "\n  -> The export takes its NO-VARIANT path: one JSON, every\n" )
            printf( "     component. That is what the console line \"No variant\n" )
            printf( "     information present!\" means. Put Variants.lst beside\n" )
            printf( "     the .brd; nowhere else is looked at.\n" )
            return( t )
        )

        printf( "\n===== 2. WHAT THE PARSER MAKES OF IT =====\n" )
        info = nil
        errset( info = gdsysGetVariantInfo() )
        unless( info
            printf( "  gdsysGetVariantInfo() returned nothing - the export stops\n" )
            printf( "  here with \"No variant information could be read!\"\n" )
            return( t )
        )
        symbolList = car( info )
        altParts = cadr( info )
        printf( "  variant table : %L\n" symbolList )
        printf( "  alternates    : %L\n" altParts )

        ; A table is always truthy and length() does not apply to it, so the
        ; keys have to be counted by iterating - the same way the export does.
        count = 0
        names = nil
        foreach( v symbolList
            count = count + 1
            names = cons( v names )
        )
        printf( "  variants parsed: %d  %L\n" count reverse( names ) )
        when( count == 0
            printf( "\n  -> Zero variants for THIS board. The export stops with a\n" )
            printf( "     message: the Variants.lst almost certainly belongs to a\n" )
            printf( "     different project. Delete or replace it, or remove it to\n" )
            printf( "     export every component.\n" )
            return( t )
        )

        printf( "\n===== 3. WHAT EACH VARIANT INSTALLS =====\n" )
        foreach( v reverse( names )
            installed = symbolList[v]
            printf( "  %s: %d refdes from the parser\n"
                    v if( listp( installed ) then length( installed ) else 0 ) )
            printf( "     %L\n" installed )
            ; What the export would really place: the design's own symbols, minus
            ; the ones this variant does not install. The list comes from the
            ; DESIGN - the variant table only subtracts - so this number is
            ; normally larger than the one above.
            nSyms = nil
            errset( nSyms = length( s3dSymbolsToExport( symbolList v ) ) )
            printf( "     -> %L symbol(s) would be exported\n" nSyms )
        )

        printf( "\n===== 4. WHAT WOULD BE WRITTEN =====\n" )
        foreach( v reverse( names )
            printf( "  %s.json\n" lowerCase( strcat( axlCurrentDesign() "_" v ) ) )
        )
        printf( "  (into the design's cad folder, one per variant; the GUI then\n" )
        printf( "   builds every tagged .json it finds there)\n" )
        printf( "\n" )
        t
    )
)
