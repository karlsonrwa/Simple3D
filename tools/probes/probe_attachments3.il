;=====================================================================
;  probe_attachments3.il - DIAGNOSTIC. Reads the design; writes only into
;  the folder you pass in.
;
;  Settles the one question left by probe 2. Asked with 'string, the 3D
;  model attachments came back with size 6904 / 20934 but the data string
;  PRINTED as about 31 characters:
;
;      data "1;40024;A;0;0;f1fafa6a40136011;"
;
;  Two possible readings, and they lead to opposite conclusions:
;    a) %L truncated the PRINT and the whole payload is in the string
;       -> it can be written out, and extracting ACIS is buildable
;    b) the string really ends at the first NUL byte
;       -> the payload cannot be got out through this API at all
;
;  strlen() answers it: if strlen == size, the data is all there.
;  The file is then written so the bytes on disk can be checked too.
;
;  Usage:
;      load("<path>/probe_attachments3.il")
;      s3dProbeExtract( "d:/temp/acis" )     ; folder must already exist
;=====================================================================

procedure( s3dProbeExtract( t_dir )
    let( ( names att data n sz port outFile ( idx 0 ) )
        names = axlGetAllAttachmentNames()
        unless( names
            printf( "PROBE3: no attachments at all.\n" )
        )

        when( names
            printf( "PROBE3: writing into %s\n" t_dir )

            foreach( id names
                when( stringp( id ) && (strlen( id ) > 3) &&
                      (substring( id 1 3 ) == "3D:")
                    idx = idx + 1
                    printf( "\n[%d] %s\n" idx id )

                    att = nil
                    errset( att = axlGetAttachment( id 'string ) )

                    if( att then
                        data = nil
                        sz   = nil
                        errset( data = att->data )
                        errset( sz   = att->size )

                        if( stringp( data ) then
                            n = strlen( data )
                            printf( "    size attribute : %L\n" sz )
                            printf( "    strlen( data ) : %d\n" n )
                            if( sz && (n == sz) then
                                printf( "    ==> FULL PAYLOAD IS IN THE STRING\n" )
                            else
                                printf( "    ==> TRUNCATED - the string stops early\n" )
                            )

                            ; Write it out regardless, so the bytes that DID
                            ; arrive can be looked at on disk.
                            outFile = strcat( t_dir "/embedded_"
                                              sprintf( nil "%d" idx ) ".bin" )
                            port = nil
                            errset( port = outfile( outFile "w" ) )
                            if( port then
                                fprintf( port "%s" data )
                                close( port )
                                printf( "    written to ... : %s\n" outFile )
                            else
                                printf( "    could NOT open : %s\n" outFile )
                            )
                        else
                            printf( "    no data attribute came back\n" )
                        )
                    else
                        printf( "    axlGetAttachment returned nil\n" )
                    )
                )
            )

            when( idx == 0
                printf( "PROBE3: no 3D model attachments found.\n" )
            )
        )
        t
    )
)
