;=====================================================================
;  probe_stepget.il - round 128, R1-7 of the 23.10.2026 review: what
;  axlStepGet answers for each form of its third argument. The exporter
;  passes a symbol INSTANCE - axlStepGet( nil nil sym ) - where the
;  reference names "a symdef or compdef"; which binding comes back when a
;  part has both was never asked.
;
;  s3dProbeStepGet - on the runner's scratch copy, never saved: the first
;      symbol with a refdes and a STEP model; for it, axlStepGet( 'map nil )
;      and axlStepGet( nil nil ) of the instance, of its symdef
;      (sym->definition) and of its compdef (sym->component->compdef), and
;      axlStepMappedInstance of the refdes; then a second binding is made
;      on the compdef with axlStepSet (the same model, offset_z 1.5) and every
;      form is asked again.
;
;    python tools/run_probe.py --with-exporter tools/probes/probe_stepget.il s3dProbeStepGet <board>
;  REQUIRES: makeVariant3dIntermediates.il
;=====================================================================

procedure( s3dProbeStepGetAsk( t_label o_sym )
    let( ( symdef compdef )
        symdef = nil
        errset( symdef = o_sym->definition )
        compdef = nil
        errset( compdef = o_sym->component->compdef )
        printf( "S3DSTEP %s: refdes %s, symdef %L, compdef %L\n" t_label o_sym->refdes
                when( symdef symdef->name ) when( compdef compdef->name ) )
        printf( "S3DSTEP   the component %L answers %L; its compdef %L answers %L; deviceType %L\n"
                o_sym->component car( errset( o_sym->component->? t ) )
                compdef when( compdef car( errset( compdef->? t ) ) )
                car( errset( o_sym->component->deviceType t ) ) )
        printf( "S3DSTEP   get the deviceType name %L\n"
                car( errset( axlStepGet( nil nil o_sym->component->deviceType ) t ) ) )
        printf( "S3DSTEP   map of the instance %L\n" car( errset( axlStepGet( 'map nil o_sym ) t ) ) )
        printf( "S3DSTEP   map of the symdef   %L\n" car( errset( axlStepGet( 'map nil symdef ) t ) ) )
        printf( "S3DSTEP   map of the compdef  %L\n" car( errset( axlStepGet( 'map nil compdef ) t ) ) )
        printf( "S3DSTEP   get the instance %L\n" car( errset( axlStepGet( nil nil o_sym ) t ) ) )
        printf( "S3DSTEP   get the symdef   %L\n" car( errset( axlStepGet( nil nil symdef ) t ) ) )
        printf( "S3DSTEP   get the compdef  %L\n" car( errset( axlStepGet( nil nil compdef ) t ) ) )
        printf( "S3DSTEP   mapped instance %L\n" car( errset( axlStepMappedInstance( o_sym->refdes ) t ) ) )
        printf( "S3DSTEP   s3dStepMapping %L\n" car( errset( s3dStepMapping( o_sym ) t ) ) )
    )
)

; The export itself into S3D_PROBE_OUT/<t_dir>, when that is set.
procedure( s3dProbeStepGetExport( t_dir )
    when( getShellEnvVar( "S3D_PROBE_OUT" )
        printf( "S3DSTEP export into %s: %L\n" t_dir
                errset( makeVariant3dIntermediates( strcat( getShellEnvVar( "S3D_PROBE_OUT" ) "/" t_dir ) ) t ) )
        drain( poport )
    )
)

procedure( s3dProbeStepGet()
    let( ( found mapping compdef set )
        foreach( s axlDBGetDesign()->symbols
            unless( found
                when( s->refdes
                    mapping = nil
                    errset( mapping = axlStepGet( nil nil s ) )
                    when( mapping && mapping->step_name  found = s )
                )
            )
        )
        unless( found  printf( "S3DSTEP no symbol with a refdes and a STEP model\n" ) )
        when( found
            s3dProbeStepGetAsk( "as the board has it" found )
            compdef = nil
            errset( compdef = found->component->compdef )
            set = nil
            mapping = nil
            errset( mapping = axlStepGet( nil nil found ) )
            ; the same model, its offset_z 1.5 - which binding answers shows
            ; in the offset that comes back
            ; axlStepSet may look the file up: the runner's HOME has no
            ; STEP path, so it is pointed at S3D_PROBE_STEPDIR and the
            ; binding names a model there, S3D_PROBE_STEPFILE
            when( getShellEnvVar( "S3D_PROBE_STEPDIR" )
                printf( "S3DSTEP steppath %L: %L\n" getShellEnvVar( "S3D_PROBE_STEPDIR" )
                        car( errset( axlSetVariable( "steppath" getShellEnvVar( "S3D_PROBE_STEPDIR" ) ) t ) ) )
                mapping->step_name = getShellEnvVar( "S3D_PROBE_STEPFILE" )
            )
            when( compdef && mapping
                errset( set = axlStepSet( 'primary compdef mapping->step_name list( 'offset_z 1.5 ) ) t )
                printf( "S3DSTEP compdef binding made on the dbid: %L\n" set )
                unless( set
                    errset( set = axlStepSet( 'primary found->component->deviceType mapping->step_name
                                              list( 'offset_z 1.5 ) ) t )
                    printf( "S3DSTEP compdef binding made on the deviceType name %L: %L\n"
                            found->component->deviceType set )
                )
            )
            s3dProbeStepGetAsk( "with a compdef binding as well" found )
            s3dProbeStepGetExport( "both" )
            ; and the footprint's binding taken away: does the instance form
            ; find the device's alone?
            printf( "S3DSTEP symdef binding deleted: %L\n"
                    car( errset( axlStepDelete( 'primary found->definition ) t ) ) )
            s3dProbeStepGetAsk( "with the compdef binding alone" found )
            s3dProbeStepGetExport( "device_only" )
        )
        drain( poport )
        t
    )
)
