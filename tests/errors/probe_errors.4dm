//%attributes = {"invisible":true}
var $previous : Boolean
var $result : Collection
var $report : Object
$previous:=Get assert enabled
SET ASSERT ENABLED:C1131(True; *)
ON ERR CALL:C155("probe_error_handler")
Splitter_assert
LOG EVENT:C667(Into system standard outputs:K38:9; "SPLITTER_ASSERT_NATIVE_DONE"; Information message:K38:1)
ASSERT:C1129(False; "Splitter direct assertion")
LOG EVENT:C667(Into system standard outputs:K38:9; "SPLITTER_ASSERT_DIRECT_DONE"; Information message:K38:1)
ON ERR CALL:C155("")
SET ASSERT ENABLED:C1131($previous; *)
$result:=Splitter_null
$report:=New object:C1471("compiled"; Is compiled mode:C492; "resultIsNull"; $result=Null)
LOG EVENT:C667(Into system standard outputs:K38:9; "SPLITTER_NULL="+JSON Stringify:C1217($report); Information message:K38:1)
