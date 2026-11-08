//%attributes = {"invisible":true,"preemptive":"capable"}
#DECLARE($state : Object)
var $process : Object
var $actual : Collection
var $preemptive : Boolean
var $index; $passed; $failures; $poll : Integer
$preemptive:=False
$process:=Process info:C1843(Current process)
If (Value type($process)=Is object)
	If ($process#Null)
		$preemptive:=($process.preemptive=True)
	End if
End if
Use ($state)
	$state.ready:=$state.ready+1
	If ($preemptive)
		$state.preemptive:=$state.preemptive+1
	End if
End use
$poll:=0
While ((Not($state.start)) & ($poll<1800))
	DELAY PROCESS(Current process; 1)
	$poll:=$poll+1
End while
$passed:=0
$failures:=0
If ($state.start)
	For ($index; 1; 200)
		$actual:=Split_string_Ex(" a , , b "; ","; sk mode regex+3)
		If (check_collection($actual; New collection("a"; "b")))
			$passed:=$passed+1
		Else
			$failures:=$failures+1
		End if
		$actual:=Split_string_Ex(" a , , b "; ","; 3)
		If (check_collection($actual; New collection("a"; "b")))
			$passed:=$passed+1
		Else
			$failures:=$failures+1
		End if
		$actual:=Split_string_Ex(" a -- -- b "; ""; 3; {separators: New collection("-"; "--")})
		If (check_collection($actual; New collection("a"; "b")))
			$passed:=$passed+1
		Else
			$failures:=$failures+1
		End if
		$actual:=Split_string_Ex("A"+Char(769)+"😀"; ""; sk mode graphemes)
		If (check_collection($actual; New collection("A"+Char(769); "😀")))
			$passed:=$passed+1
		Else
			$failures:=$failures+1
		End if
		$actual:=Split_string_Ex("A"+Char(769)+"😀"; "."; sk mode regex+sk mode graphemes)
		If (check_collection($actual; New collection(""; ""; "")))
			$passed:=$passed+1
		Else
			$failures:=$failures+1
		End if
		$actual:=Split_string_Ex("abc"; "["; 0; {mode: "regex"})
		If ($actual=Null)
			$passed:=$passed+1
		Else
			$failures:=$failures+1
		End if
		$actual:=Split_string_Ex("a,b,c"; ","; 0; {maxSplits: 1})
		If (check_collection($actual; New collection("a"; "b,c")))
			$passed:=$passed+1
		Else
			$failures:=$failures+1
		End if
	End for
Else
	$failures:=$failures+1
End if
Use ($state)
	$state.passed:=$state.passed+$passed
	$state.failures:=$state.failures+$failures
	$state.done:=$state.done+1
End use
