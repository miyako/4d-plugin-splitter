//%attributes = {"invisible":true}
var $state; $report : Object
var $index; $process; $poll : Integer
$state:=New shared object("ready"; 0; "start"; False; "done"; 0; "preemptive"; 0; "passed"; 0; "failures"; 0)
For ($index; 1; 8)
	$process:=New process("split_worker"; 0; "Splitter preemptive "+String($index); $state)
	If ($process=0)
		Use ($state)
			$state.failures:=$state.failures+1
		End use
	End if
End for
$poll:=0
While (($state.ready<8) & ($poll<1800))
	DELAY PROCESS(Current process; 1)
	$poll:=$poll+1
End while
Use ($state)
	$state.start:=True
End use
$poll:=0
While (($state.done<8) & ($poll<1800))
	DELAY PROCESS(Current process; 1)
	$poll:=$poll+1
End while
Use ($state)
	$report:=New object("compiled"; Is compiled mode:C492; "ready"; $state.ready; "done"; $state.done; "preemptive"; $state.preemptive; "passed"; $state.passed; "failures"; $state.failures)
End use
LOG EVENT:C667(Into system standard outputs:K38:9; "SPLITTER_PREEMPTIVE="+JSON Stringify:C1217($report); Information message:K38:1)
