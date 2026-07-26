;=====================================================================
;  probe_attachments.il - DIAGNOSTIC ONLY. Reads, never writes.
;
;  Answers the two things the SKILL reference does not say about the 3D
;  models Allegro stores inside the .brd:
;
;    1. What ids does it use for them? (axlGetAllAttachmentNames)
;    2. Is the payload an actual STEP file, or an internal representation?
;       -> a real STEP file begins with the line   ISO-10303-21;
;
;  Usage:  load("<path>/probe_attachments.il")   then   s3dProbeAttachments()
;=====================================================================

; First line of a text file, or nil if it cannot be read as text.
procedure( s3dProbeFirstLine( t_file )
    let( ( port line )
        line = nil
        errset( port = infile( t_file ) )
        when( port
            errset( gets( line port ) )
            close( port )
        )
        line
    )
)

procedure( s3dProbeAttachments()
    let( ( names att data first ( n 0 ) )
        names = axlGetAllAttachmentNames()

        unless( names
            printf( "PROBE: this design has NO attachments at all.\n" )
            printf( "PROBE: so nothing is embedded - models must come from disk.\n" )
        )

        when( names
            printf( "PROBE: %d attachment(s) in this design.\n" length( names ) )
            printf( "PROBE: a payload that is a real STEP file starts with ISO-10303-21;\n" )

            foreach( id names
                n = n + 1
                printf( "\n[%d] id ......: %L\n" n id )

                att = nil
                errset( att = axlGetAttachment( id 'file ) )

                if( att then
                    ; Dump the whole record: the reference lists timeStamp
                    ; TWICE, the second one described as the size, so the real
                    ; attribute name for the size has to be read off the object.
                    printf( "    record ..: %L\n" att->?? )

                    data = nil
                    errset( data = att->data )

                    if( stringp( data ) then
                        printf( "    written to: %s\n" data )
                        first = s3dProbeFirstLine( data )
                        if( stringp( first ) then
                            printf( "    1st line .: %s\n" first )
                        else
                            printf( "    1st line .: (not readable as text - binary payload)\n" )
                        )
                    else
                        printf( "    no 'data' attribute came back\n" )
                    )
                else
                    printf( "    could not be read\n" )
                )
            )
        )
        t
    )
)
