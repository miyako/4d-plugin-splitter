//%attributes = {"invisible":true}
var $sources; $separators; $actual; $expected; $kinds : Collection
var $source; $separator; $astral; $accent; $nul : Text
var $flag; $passed; $failed; $index : Integer
var $integer : Integer
var $real : Real
var $report : Object
$astral:=Char:C90(55357)+Char:C90(56832)
$accent:="e"+Char:C90(769)
$nul:=Char:C90(0)
$sources:=New collection:C1472(""; "a"; "a,b,"; ",,a,,"; "  a  ,   , b "; "a--b---c"; "A"+$astral+"B"; $accent+"-"+Char:C90(233); "a"+Char:C90(13)+Char:C90(10)+"b"; "a"+$nul+"b"; "a"+Char:C90(9)+Char:C90(160)+"b"; "A,a,"+Char:C90(193))
$separators:=New collection:C1472(""; ","; "--"; "-"; "absent"; "a"; $nul; Char:C90(13)+Char:C90(10))
$passed:=0
$failed:=0
For each ($source; $sources)
	For each ($separator; $separators)
		For ($flag; 0; 3)
			$expected:=Split string:C1554($source; $separator; $flag)
			$actual:=Splitter_native($source; $separator; $flag)
			If (Splitter_equal($actual; $expected)=1)
				$passed:=$passed+1
			Else
				$failed:=$failed+1
			End if
			$actual:=Splitter_native($source; $separator; $flag; Null)
			If (Splitter_equal($actual; $expected)=1)
				$passed:=$passed+1
			Else
				$failed:=$failed+1
			End if
			$actual:=Splitter_native($source; $separator; $flag; New object:C1471("mode"; "literal"))
			If (Splitter_equal($actual; $expected)=1)
				$passed:=$passed+1
			Else
				$failed:=$failed+1
			End if
		End for
		$expected:=Split string:C1554($source; $separator)
		$actual:=Splitter_native($source; $separator)
		If (Splitter_equal($actual; $expected)=1)
			$passed:=$passed+1
		Else
			$failed:=$failed+1
		End if
	End for each
End for each
For ($index; 1; 1000)
	$actual:=Splitter_native("a"+$nul+$astral+",b"; ","; 0)
	If (Splitter_equal($actual; New collection:C1472("a"+$nul+$astral; "b"))#1)
		$failed:=$failed+1
	End if
End for
$actual:=Splitter_span("a"+$nul+"b"; 2; 1)
If (Splitter_equal($actual; New collection:C1472($nul))#1)
	$failed:=$failed+1
End if
$integer:=3
$real:=3
$report:=New object:C1471("compiled"; Is compiled mode:C492; "passed"; $passed; "failed"; $failed; "astralLength"; Length:C16($astral); "combiningLength"; Length:C16($accent))
$report.kindsLiteral:=Splitter_kinds(","; 0)
$report.kindsInteger:=Splitter_kinds(","; $integer)
$report.kindsReal:=Splitter_kinds(","; $real)
$report.kindsStructured:=Splitter_kinds(New collection:C1472(","; ";"); New object:C1471("mode"; "literals"))
$report.kindsNull:=Splitter_kinds(Null; Null)
$report.empty:=Split string:C1554(""; "")
$report.whitespace:=Split string:C1554(" , "; ","; 3)
LOG EVENT:C667(Into system standard outputs:K38:9; "SPLITTER_CONTRACT="+JSON Stringify:C1217($report); Information message:K38:1)
