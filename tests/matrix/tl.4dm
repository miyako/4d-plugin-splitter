//%attributes = {"invisible":true}
var $explicit; $omitted; $expected : Collection
var $report : Object
$expected:=Split string:C1554("a,b,"; ",")
$explicit:=Splitter_probe_tl("a,b,"; ","; 0)
$omitted:=Splitter_probe_tl("a,b,"; ",")
$report:=New object:C1471("compiled"; Is compiled mode:C492; "explicitEqual"; Splitter_equal($explicit; $expected); "omittedEqual"; Splitter_equal($omitted; $expected))
LOG EVENT:C667(Into system standard outputs:K38:9; "SPLITTER_MATRIX="+JSON Stringify:C1217($report); Information message:K38:1)
