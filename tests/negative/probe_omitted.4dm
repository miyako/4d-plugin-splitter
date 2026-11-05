//%attributes = {"invisible":true}
var $result : Collection
$result:=Splitter_probe("a,b"; ",")
If (Splitter_equal($result; Split string("a,b"; ","))=1)
	LOG EVENT:C667(Into system standard outputs:K38:9; "SPLITTER_OMITTED_INTERPRETED_OK"; Information message:K38:1)
End if
