//%attributes = {"invisible":true}
#DECLARE($actual : Collection; $expected : Collection) : Boolean
var $left; $right : Text
var $index : Integer
$0:=False
If ($actual#Null)
	If ($expected#Null)
		If ($actual.length=$expected.length)
			$0:=True
			For ($index; 0; $actual.length-1)
				If (Value type($actual[$index])#Is text)
					$0:=False
				Else
					$left:=$actual[$index]
					$right:=$expected[$index]
					If (Length:C16($left)#Length:C16($right))
						$0:=False
					Else
						If (Length:C16($left)>0)
							If (Position:C15($left; $right; *)#1)
								$0:=False
							End if
						End if
					End if
				End if
			End for
		End if
	End if
End if
