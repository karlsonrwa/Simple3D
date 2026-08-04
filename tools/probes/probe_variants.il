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
    let( ( cwd here info symbolList altParts count names installed nSyms
           knownTab nKnown nPlaced nCovered instTab r )

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

        printf( "\n===== 2b. DOES IT DESCRIBE THIS BOARD? =====\n" )
        ; The question that a parsed-but-wrong file answers wrongly. A stub
        ; ("dummy" with an empty base) knows nothing, so nothing is subtracted
        ; and every component is exported into every variant file; a file from
        ; another project knows plenty, none of it here, with the same result.
        knownTab = s3dVariantKnownRefdes( symbolList )
        nKnown = 0
        foreach( key knownTab  nKnown = nKnown + 1 )
        nPlaced = 0
        nCovered = 0
        foreach( sym axlDBGetDesign()->symbols
            when( sym->refdes
                nPlaced = nPlaced + 1
                when( knownTab[upperCase( sym->refdes )]  nCovered = nCovered + 1 )
            )
        )
        printf( "  refdes the variant list knows : %d\n" nKnown )
        printf( "  placed components on the board: %d\n" nPlaced )
        printf( "  of those, known to the list   : %d\n" nCovered )
        cond(
            ( nKnown == 0
                printf( "  -> the list installs NOTHING. The export stops on it.\n" ) )
            ( (nPlaced > 0) && (nCovered == 0)
                printf( "  -> NOT this board's file. The export stops on it.\n" ) )
            ( t
                printf( "  -> the list and the board agree.\n" ) )
        )

        ; Which side of the rule each placed part falls on. Everything with a
        ; refdes obeys the list - mechanical or not, since a refdes is what makes
        ; a part nameable there. A symbol WITHOUT one can never appear in the
        ; file, so nothing but NO_STEP_EXPORT can remove it.
        printf( "\n  outside the variant system (no refdes; kept in every variant):\n" )
        printf( "    symbol name           symbol type  compdef class  has model\n" )
        nCovered = 0
        foreach( sym axlDBGetDesign()->symbols
            unless( sym->refdes
                nCovered = nCovered + 1
                when( nCovered <= 15
                    ; The type and class are printed even though they no longer
                    ; decide anything: a part that surprises the user here is
                    ; usually one whose refdes they expected to exist.
                    printf( "    %-20L  %-11L  %-13L  %L\n"
                            sym->name
                            sym->type
                            car( errset( sym->component->compdef->class ) )
                            s3dHasStepModel( sym ) )
                )
            )
        )
        printf( "    %d in total\n" nCovered )

        ; The mirror image, and the one that changed on 2026-08-03: these used to
        ; be kept in every variant on the strength of being mechanical. They now
        ; obey the list like anything else, so a MOLEX housing missing from a
        ; variant will show up in that variant's "dropped" line below.
        printf( "\n  mechanical BUT carrying a refdes (the list governs these):\n" )
        printf( "    refdes            in netlist  symbol type  compdef class\n" )
        nCovered = 0
        foreach( sym axlDBGetDesign()->symbols
            when( sym->refdes && s3dIsMechanical( sym )
                nCovered = nCovered + 1
                when( nCovered <= 15
                    printf( "    %-16L  %-10L  %-11L  %L\n"
                            sym->refdes
                            if( car( errset( sym->component ) ) then t else nil )
                            sym->type
                            car( errset( sym->component->compdef->class ) ) )
                )
            )
        )
        printf( "    %d in total\n" nCovered )

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
            ; and, by name, the ones this variant leaves out - the answer to
            ; "why is R3 in my model"
            ; A table, not member() on a list: SKILL's member compares with eq,
            ; which is not what two equal strings are.
            instTab = makeTable( "probeInstalled" nil )
            foreach( r installed
                when( stringp( r )  instTab[upperCase( r )] = t )
            )
            printf( "     dropped: " )
            foreach( sym axlDBGetDesign()->symbols
                when( sym->refdes && !instTab[upperCase( sym->refdes )] &&
                      !s3dAlwaysStepExport( sym )
                    printf( "%s " sym->refdes )
                )
            )
            printf( "\n     kept by %s: " S3D_AlwaysExportProp )
            foreach( sym axlDBGetDesign()->symbols
                when( sym->refdes && !instTab[upperCase( sym->refdes )] &&
                      s3dAlwaysStepExport( sym )
                    printf( "%s " sym->refdes )
                )
            )
            printf( "\n" )
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
