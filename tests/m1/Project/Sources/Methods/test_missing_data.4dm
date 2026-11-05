//%attributes = {"invisible":true}
var $native; $regex; $graphemes : Collection
var $report : Object
$native:=Split_string_Ex("a,b"; ",")
$regex:=Split_string_Ex("a,b"; ","; 0; {mode: "regex"})
$graphemes:=Split_string_Ex("😀"; ""; 0; {mode: "graphemes"})
$report:=New object:C1471("nativeWorks"; check_collection($native; New collection:C1472("a"; "b")); "regexIsNull"; $regex=Null; "graphemesIsNull"; $graphemes=Null)
LOG EVENT:C667(Into system standard outputs:K38:9; "SPLITTER_MISSING="+JSON Stringify:C1217($report); Information message:K38:1)
