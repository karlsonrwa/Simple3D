;=====================================================================
;  probe_attachments2.il - DIAGNOSTIC ONLY. Reads, never writes.
;
;  Follow-up to probe_attachments.il. There, the two 3D-model attachments
;  came back as a stub record - (objType "attachment" dataFormat file) -
;  with no id, no size and no data, while the other 19 returned in full.
;  That probe asked ONE way (axlGetAttachment id 'file), so it cannot tell
;  "Allegro will not hand these over" from "the probe asked wrong".
;
;  This asks every documented way and prints the whole record each time.
;  A known-good attachment is probed identically as a CONTROL, so the
;  three calls can be compared against something that is known to work.
;
;  Usage:  load("<path>/probe_attachments2.il")   then   s3dProbeModels()
;=====================================================================

; One retrieval attempt. Never raises: a failure is the result here.
procedure( s3dProbeTry( t_id g_fmt t_label )
    let( ( att ok )
        att = nil
        ok = errset(
            att = if( g_fmt then
                      axlGetAttachment( t_id g_fmt )
                  else
                      axlGetAttachment( t_id )
                  ) )
        cond(
            ( !ok
                printf( "    %-16s -> SKILL error inside the call\n" t_label ) )
            ( att
                printf( "    %-16s -> %L\n" t_label att->?? ) )
            ( t
                printf( "    %-16s -> nil\n" t_label ) )
        )
    )
)

procedure( s3dProbeAll( t_id )
    printf( "\nid: %L   (%d chars, limit is 31)\n" t_id strlen( t_id ) )
    s3dProbeTry( t_id nil       "no format" )
    s3dProbeTry( t_id 'string   "'string" )
    s3dProbeTry( t_id 'file     "'file" )
)

; Alias: loading this file after probe_attachments.il and calling the OLD
; name by habit should run the NEW probe, not silently repeat the old one.
procedure( s3dProbeAttachments()
    s3dProbeModels()
)

procedure( s3dProbeModels()
    let( ( names models control )
        names = axlGetAllAttachmentNames()
        unless( names
            printf( "PROBE2: no attachments at all.\n" )
        )

        when( names
            models  = nil
            control = nil
            foreach( id names
                when( stringp( id )
                    if( (strlen( id ) > 3) && (substring( id 1 3 ) == "3D:") then
                        models = cons( id models )
                    else
                        ; keep one ordinary attachment as the control
                        unless( control  control = id )
                    )
                )
            )

            printf( "PROBE2: %d attachment(s), %d of them 3D models.\n"
                    length( names ) length( models ) )

            when( control
                printf( "\n--- CONTROL (an attachment the first probe read fine) ---" )
                s3dProbeAll( control )
            )

            when( models
                printf( "\n--- 3D MODEL ATTACHMENTS ---" )
                foreach( id models  s3dProbeAll( id ) )
            )
        )
        t
    )
)
