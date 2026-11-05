//%attributes = {"invisible":true}
ON ERR CALL:C155("probe_error_handler")
Splitter_throw
ON ERR CALL:C155("")
LOG EVENT:C667(Into system standard outputs:K38:9; "SPLITTER_ERROR_RETURNED"; Information message:K38:1)
