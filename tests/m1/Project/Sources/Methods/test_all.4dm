//%attributes = {"invisible":true}
var $sources; $separators; $actual; $expected; $cases; $failures; $many : Collection
var $source; $separator; $nul; $combining; $family; $skin; $flagEmoji; $crlf; $evil; $private; $before; $whitespace : Text
var $flags; $passed; $index : Integer
var $case; $report; $unchanged : Object
var $ok : Boolean
$failures:=New collection:C1472
$passed:=0
$nul:=Char:C90(0)
$combining:="e"+Char:C90(769)
$family:="👩‍👩‍👧‍👦"
$skin:="👍🏽"
$flagEmoji:="🇫🇷"
$crlf:=Char:C90(13)+Char:C90(10)
$sources:=New collection:C1472(""; "a"; "a,b,"; ",,a,,"; "  a  ,   , b "; "a--b---c"; "A😀B"; $combining+"-é"; "a"+$crlf+"b"; "a"+$nul+"b"; "a"+Char:C90(9)+Char:C90(160)+"b"; "A,a,Á")
$separators:=New collection:C1472(""; ","; "--"; "-"; "absent"; "a"; $nul; $crlf)
For each ($source; $sources)
	For each ($separator; $separators)
		For ($flags; 0; 3)
			$expected:=Split string:C1554($source; $separator; $flags)
			$actual:=Split_string_Ex($source; $separator; $flags)
			If (check_collection($actual; $expected))
				$passed:=$passed+1
			Else
				$failures.push("native three arguments")
			End if
			$actual:=Split_string_Ex($source; $separator; $flags; Null)
			If (check_collection($actual; $expected))
				$passed:=$passed+1
			Else
				$failures.push("native Null fourth")
			End if
			$actual:=Split_string_Ex($source; $separator; $flags; {mode: "literal"})
			If (check_collection($actual; $expected))
				$passed:=$passed+1
			Else
				$failures.push("native literal Object")
			End if
		End for
		$actual:=Split_string_Ex($source; $separator)
		If (check_collection($actual; Split string:C1554($source; $separator)))
			$passed:=$passed+1
		Else
			$failures.push("native omitted options")
		End if
	End for each
End for each
$cases:=New collection:C1472
$cases.push({name: "regex constant"; input: "a,b,c"; separator: "[,]"; flags: sk mode regex; options: Null; expected: New collection:C1472("a"; "b"; "c")})
$cases.push({name: "graphemes constant"; input: $combining+$family+$skin+$flagEmoji+$crlf; separator: ""; flags: sk mode graphemes; options: Null; expected: New collection:C1472($combining; $family; $skin; $flagEmoji; $crlf)})
$cases.push({name: "combined dot"; input: $combining+$family+$skin+$flagEmoji; separator: "."; flags: sk mode regex+sk mode graphemes; options: Null; expected: New collection:C1472(""; ""; ""; ""; "")})
$cases.push({name: "combined quantified dot"; input: $combining+$family+"x"; separator: ".{2}"; flags: sk mode regex+sk mode graphemes; options: Null; expected: New collection:C1472(""; "x")})
$cases.push({name: "combined dot newline"; input: $combining+$crlf+$family; separator: "."; flags: sk mode regex+sk mode graphemes; options: Null; expected: New collection:C1472(""; $crlf; "")})
$cases.push({name: "combined dotAll"; input: $combining+$crlf+$family; separator: "."; flags: sk mode regex+sk mode graphemes; options: {regexFlags: {dotAll: True}}; expected: New collection:C1472(""; ""; ""; "")})
$cases.push({name: "combined inline dotAll"; input: $combining+$crlf+$family; separator: "(?s:.)"; flags: sk mode regex+sk mode graphemes; options: Null; expected: New collection:C1472(""; ""; ""; "")})
$cases.push({name: "combined escaped dot"; input: $combining+"."+ $family; separator: "\\."; flags: sk mode regex+sk mode graphemes; options: Null; expected: New collection:C1472($combining; $family)})
$cases.push({name: "combined class dot"; input: $combining+"."+ $family; separator: "[.]"; flags: sk mode regex+sk mode graphemes; options: Null; expected: New collection:C1472($combining; $family)})
$cases.push({name: "combined quoted dot"; input: $combining+"."+ $family; separator: "\\Q.\\E"; flags: sk mode regex+sk mode graphemes; options: Null; expected: New collection:C1472($combining; $family)})
$cases.push({name: "combined inline comments"; input: $combining+$family; separator: "(?x) # . [ ("+Char:C90(10)+"."; flags: sk mode regex+sk mode graphemes; options: Null; expected: New collection:C1472(""; ""; "")})
$cases.push({name: "combined remainder"; input: $combining+$family+$skin; separator: "."; flags: sk mode regex+sk mode graphemes; options: {maxSplits: 1}; expected: New collection:C1472(""; $family+$skin)})
$cases.push({name: "combined filter"; input: $combining+$family; separator: "."; flags: sk mode regex+sk mode graphemes+sk ignore empty strings; options: Null; expected: New collection:C1472})
$cases.push({name: "regex constant trim filter"; input: " a , , b "; separator: ","; flags: sk mode regex+sk trim spaces+sk ignore empty strings; options: Null; expected: New collection:C1472("a"; "b")})
$cases.push({name: "graphemes constant trim filter"; input: " "+$combining+" "; separator: ""; flags: sk mode graphemes+sk trim spaces+sk ignore empty strings; options: Null; expected: New collection:C1472($combining)})
$cases.push({name: "regex constant matching mode"; input: "a,b"; separator: ","; flags: sk mode regex; options: {mode: "regex"}; expected: New collection:C1472("a"; "b")})
$cases.push({name: "graphemes constant matching mode"; input: $combining; separator: ""; flags: sk mode graphemes; options: {mode: "graphemes"}; expected: New collection:C1472($combining)})
$cases.push({name: "combined matching mode"; input: $combining; separator: "."; flags: sk mode regex+sk mode graphemes; options: {mode: "regex"}; expected: New collection:C1472(""; "")})
$cases.push({name: "regex constant conflict"; input: "a,b"; separator: ","; flags: sk mode regex; options: {mode: "literal"}; failure: True})
$cases.push({name: "graphemes constant conflict"; input: "abc"; separator: ""; flags: sk mode graphemes; options: {mode: "regex"}; failure: True})
$cases.push({name: "combined mode conflict"; input: "abc"; separator: ""; flags: sk mode regex+sk mode graphemes; options: {mode: "graphemes"}; failure: True})
$cases.push({name: "regex constant list conflict"; input: "a,b"; separator: ""; flags: sk mode regex; options: {separators: New collection:C1472(",")}; failure: True})
$cases.push({name: "graphemes constant separator"; input: "a,b"; separator: ","; flags: sk mode graphemes; options: Null; failure: True})
$cases.push({name: "constant unknown extended flags"; input: "abc"; separator: "."; flags: sk mode regex+16; options: Null; failure: True})
$cases.push({name: "constant regex limit"; input: "abc"; separator: "."; flags: sk mode regex; options: {limits: {maxItems: 1}}; failure: True})
$cases.push({name: "combined pattern limit unchanged"; input: $combining; separator: "."; flags: sk mode regex+sk mode graphemes; options: {limits: {maxPatternUnits: 1}}; expected: New collection:C1472(""; "")})
$cases.push({name: "combined invalid regex"; input: "abc"; separator: "["; flags: sk mode regex+sk mode graphemes; options: Null; failure: True})
$cases.push({name: "literal remainder"; input: "a,b,c"; separator: ","; flags: 0; options: {maxSplits: 1}; expected: New collection:C1472("a"; "b,c")})
$cases.push({name: "zero splits"; input: "a,b,c"; separator: ","; flags: 0; options: {maxSplits: 0}; expected: New collection:C1472("a,b,c")})
$cases.push({name: "zero splits empty"; input: ""; separator: ""; flags: 0; options: {maxSplits: 0}; expected: New collection:C1472("")})
$cases.push({name: "longest literal"; input: "a---b"; separator: ""; flags: 0; options: {separators: New collection:C1472("-"; "--"; "---")}; expected: New collection:C1472("a"; "b")})
$cases.push({name: "literal list remainder"; input: "a--b::c"; separator: ""; flags: 0; options: {mode: "literals"; separators: New collection:C1472("--"; "::"); maxSplits: 1}; expected: New collection:C1472("a"; "b::c")})
$cases.push({name: "empty list"; input: "a,b"; separator: ""; flags: 0; options: {separators: New collection:C1472}; expected: New collection:C1472("a,b")})
$cases.push({name: "list trim and filter"; input: " a - - b "; separator: ""; flags: 3; options: {separators: New collection:C1472("-")}; expected: New collection:C1472("a"; "b")})
$cases.push({name: "nul list"; input: "a"+$nul+"b"; separator: ""; flags: 0; options: {separators: New collection:C1472($nul)}; expected: New collection:C1472("a"; "b")})
$cases.push({name: "regex remainder"; input: "a,b,c"; separator: ","; flags: 0; options: {mode: "regex"; maxSplits: 1}; expected: New collection:C1472("a"; "b,c")})
$cases.push({name: "regex flags"; input: "aXbxc"; separator: "x"; flags: 0; options: {mode: "regex"; regexFlags: {caseInsensitive: True}}; expected: New collection:C1472("a"; "b"; "c")})
$cases.push({name: "zero width"; input: "abc"; separator: "(?=b)"; flags: 0; options: {mode: "regex"}; expected: New collection:C1472("a"; "bc")})
$cases.push({name: "empty regex"; input: "A😀B"; separator: ""; flags: 0; options: {mode: "regex"}; expected: New collection:C1472(""; "A"; "😀"; "B"; "")})
$cases.push({name: "zero width remainder"; input: "A😀B"; separator: ""; flags: 0; options: {mode: "regex"; maxSplits: 1}; expected: New collection:C1472(""; "A😀B")})
$cases.push({name: "regex end"; input: "abc"; separator: "$"; flags: 0; options: {mode: "regex"}; expected: New collection:C1472("abc"; "")})
$cases.push({name: "no captured fields"; input: "a,b"; separator: "(,)"; flags: 0; options: {mode: "regex"}; expected: New collection:C1472("a"; "b")})
$cases.push({name: "regex trim filter"; input: " a , , b "; separator: ","; flags: 3; options: {mode: "regex"}; expected: New collection:C1472("a"; "b")})
$cases.push({name: "nul regex"; input: "a"+$nul+"b"; separator: $nul; flags: 0; options: {mode: "regex"}; expected: New collection:C1472("a"; "b")})
$cases.push({name: "names coarse"; input: "Bois-Joli / Morne-à-l’eau"; separator: "\\s*/\\s*"; flags: 0; options: {mode: "regex"}; expected: New collection:C1472("Bois-Joli"; "Morne-à-l’eau")})
$cases.push({name: "names fine"; input: "Bois-Joli Morne-à-l’eau"; separator: "[-’\\s]+"; flags: 0; options: {mode: "regex"}; expected: New collection:C1472("Bois"; "Joli"; "Morne"; "à"; "l"; "eau")})
$cases.push({name: "unicode graphemes"; input: "A😀"+$combining+$family+$skin+$flagEmoji+$crlf; separator: ""; flags: 0; options: {mode: "graphemes"}; expected: New collection:C1472("A"; "😀"; $combining; $family; $skin; $flagEmoji; $crlf)})
$cases.push({name: "empty graphemes"; input: ""; separator: ""; flags: 0; options: {mode: "graphemes"}; expected: New collection:C1472})
$cases.push({name: "grapheme trim filter"; input: " "+$combining+" "; separator: ""; flags: 3; options: {mode: "graphemes"}; expected: New collection:C1472($combining)})
$whitespace:=Char:C90(9)+$crlf+Char:C90(160)+Char:C90(12288)
$cases.push({name: "grapheme whitespace unchanged"; input: $whitespace; separator: ""; flags: 0; options: {mode: "graphemes"}; expected: New collection:C1472(Char:C90(9); $crlf; Char:C90(160); Char:C90(12288))})
$cases.push({name: "grapheme ignore without trim"; input: $whitespace; separator: ""; flags: 1; options: {mode: "graphemes"}; expected: New collection:C1472(Char:C90(9); $crlf; Char:C90(160); Char:C90(12288))})
$cases.push({name: "grapheme whitespace trim only"; input: $whitespace; separator: ""; flags: 2; options: {mode: "graphemes"}; expected: New collection:C1472(""; ""; ""; "")})
$cases.push({name: "grapheme whitespace trim filter"; input: $whitespace; separator: ""; flags: 3; options: {mode: "graphemes"}; expected: New collection:C1472})
$whitespace:=""
For each ($index; New collection:C1472(9; 10; 11; 12; 13; 32; 133; 160; 5760; 8192; 8193; 8194; 8195; 8196; 8197; 8198; 8199; 8200; 8201; 8202; 8232; 8233; 8239; 8287; 12288))
	$whitespace:=$whitespace+Char:C90($index)
End for each
$cases.push({name: "grapheme all Unicode whitespace"; input: $whitespace+"😀"; separator: ""; flags: 3; options: {mode: "graphemes"}; expected: New collection:C1472("😀")})
$flags:=sk mode regex+sk mode graphemes
$cases.push({name: "combined Unicode trim repro"; input: "　やや　。、 ご機嫌　、斜め。"; separator: "[、。]"; flags: $flags+sk trim spaces+sk ignore empty strings; options: Null; expected: New collection:C1472("やや"; "ご機嫌"; "斜め")})
$cases.push({name: "combined Unicode trim repro empty fields"; input: "　やや　。、 ご機嫌　、斜め。"; separator: "[、。]"; flags: $flags+sk trim spaces; options: Null; expected: New collection:C1472("やや"; ""; "ご機嫌"; "斜め"; "")})
$cases.push({name: "combined all Unicode whitespace"; input: $whitespace+"😀"+$whitespace; separator: ","; flags: $flags+2; options: Null; expected: New collection:C1472("😀")})
$cases.push({name: "combined whitespace unchanged"; input: $whitespace+","+Char:C90(160); separator: ","; flags: $flags; options: Null; expected: New collection:C1472($whitespace; Char:C90(160))})
$cases.push({name: "combined ignore without trim"; input: $whitespace+",,"+Char:C90(160); separator: ","; flags: $flags+1; options: Null; expected: New collection:C1472($whitespace; Char:C90(160))})
$cases.push({name: "combined whitespace trim only"; input: $whitespace+","+Char:C90(160); separator: ","; flags: $flags+2; options: Null; expected: New collection:C1472(""; "")})
$cases.push({name: "combined whitespace trim filter"; input: $whitespace+","+Char:C90(160); separator: ","; flags: $flags+3; options: Null; expected: New collection:C1472})
$cases.push({name: "combined internal whitespace"; input: Char:C90(12288)+"a"+$whitespace+"b"+Char:C90(160); separator: ","; flags: $flags+3; options: Null; expected: New collection:C1472("a"+$whitespace+"b")})
$cases.push({name: "combined anchors use original source"; input: Char:C90(12288)+"a,b"+Char:C90(12288); separator: "^a|b$"; flags: $flags+3; options: Null; expected: New collection:C1472("a,b")})
$cases.push({name: "combined lookarounds use original source"; input: Char:C90(12288)+",a,"+Char:C90(160)+"b"+Char:C90(12288); separator: "(?<=\\u3000),|,(?=\\u00a0)"; flags: $flags+3; options: Null; expected: New collection:C1472("a"; "b")})
$cases.push({name: "combined whitespace delimiter"; input: Char:C90(12288)+"a"+Char:C90(12288)+",b"; separator: "\\u3000,"; flags: $flags+2; options: Null; expected: New collection:C1472("a"; "b")})
$cases.push({name: "combined trimmed remainder"; input: Char:C90(12288)+"a,"+Char:C90(160)+"b, c"+Char:C90(12288); separator: ","; flags: $flags+3; options: {maxSplits: 1}; expected: New collection:C1472("a"; "b, c")})
$cases.push({name: "combined zero splits trimmed"; input: Char:C90(12288)+"a,"+Char:C90(160)+"b"+Char:C90(12288); separator: ","; flags: $flags+2; options: {maxSplits: 0}; expected: New collection:C1472("a,"+Char:C90(160)+"b")})
$cases.push({name: "combined zero width trimmed"; input: Char:C90(12288)+"a"+Char:C90(12288); separator: "^|$"; flags: $flags+2; options: Null; expected: New collection:C1472(""; "a"; "")})
$cases.push({name: "combined empty trim"; input: ""; separator: ","; flags: $flags+2; options: Null; expected: New collection:C1472("")})
$cases.push({name: "combined empty trim filter"; input: ""; separator: ","; flags: $flags+3; options: Null; expected: New collection:C1472})
$cases.push({name: "combined trimmed cluster fields"; input: Char:C90(12288)+$combining+", "+$family+Char:C90(160); separator: ","; flags: $flags+3; options: Null; expected: New collection:C1472($combining; $family)})
$cases.push({name: "combined trimmed combining mark"; input: " "+Char:C90(769)+" "+Char:C90(160); separator: ","; flags: $flags+3; options: Null; expected: New collection:C1472(Char:C90(769))})
$cases.push({name: "combined trimmed dot clusters"; input: " "+Char:C90(769)+"x"+Char:C90(12288); separator: "."; flags: $flags+2; options: Null; expected: New collection:C1472(""; ""; ""; "")})
$cases.push({name: "combined non-whitespace preserved"; input: " "+Char:C90(28)+Char:C90(6158)+Char:C90(8203)+Char:C90(8205)+Char:C90(8288)+Char:C90(65279)+Char:C90(160); separator: ","; flags: $flags+3; options: Null; expected: New collection:C1472(Char:C90(28)+Char:C90(6158)+Char:C90(8203)+Char:C90(8205)+Char:C90(8288)+Char:C90(65279))})
$cases.push({name: "combined NUL preserved"; input: " "+$nul+Char:C90(160); separator: ","; flags: $flags+3; options: Null; expected: New collection:C1472($nul)})
$cases.push({name: "combined candidates before trimming"; input: Char:C90(12288)+","+Char:C90(160); separator: ","; flags: $flags+3; options: {limits: {maxItems: 1}}; failure: True})
$cases.push({name: "combined units before trimming"; input: Char:C90(12288)+"a"; separator: ","; flags: $flags+3; options: {limits: {maxOutputUnits: 1}}; failure: True})
$cases.push({name: "combined zero splits units before trimming"; input: Char:C90(12288)+"a"; separator: ","; flags: $flags+3; options: {maxSplits: 0; limits: {maxOutputUnits: 1}}; failure: True})
$cases.push({name: "combined exact output bound"; input: Char:C90(12288)+"a"; separator: ","; flags: $flags+3; options: {limits: {maxOutputUnits: 2}}; expected: New collection:C1472("a")})
$cases.push({name: "combined trimmed matching mode"; input: Char:C90(12288)+"a"+Char:C90(160); separator: ","; flags: $flags+3; options: {mode: "regex"}; expected: New collection:C1472("a")})
For ($flags; 0; 3)
	$source:=$whitespace+"a,"+$whitespace
	$expected:=Split string:C1554($source; ","; $flags)
	$cases.push({name: "ordinary regex host whitespace compatibility"; input: $source; separator: ","; flags: sk mode regex+$flags; options: Null; expected: $expected})
	$cases.push({name: "literal remainder host whitespace compatibility"; input: $source; separator: ","; flags: $flags; options: {maxSplits: 1}; expected: $expected})
	$cases.push({name: "literal list host whitespace compatibility"; input: $source; separator: ""; flags: $flags; options: {separators: New collection:C1472(",")}; expected: $expected})
End for
$cases.push({name: "grapheme trimmed combining cluster"; input: " "+Char:C90(769)+"😀"; separator: ""; flags: 3; options: {mode: "graphemes"}; expected: New collection:C1472(Char:C90(769); "😀")})
$cases.push({name: "grapheme non-whitespace preserved"; input: Char:C90(28)+Char:C90(6158)+Char:C90(8203)+Char:C90(8288)+Char:C90(65279); separator: ""; flags: 3; options: {mode: "graphemes"}; expected: New collection:C1472(Char:C90(28); Char:C90(6158); Char:C90(8203); Char:C90(8288); Char:C90(65279))})
$cases.push({name: "grapheme mixed whitespace filter"; input: Char:C90(9)+$combining+$crlf+$family+Char:C90(160); separator: ""; flags: 3; options: {mode: "graphemes"}; expected: New collection:C1472($combining; $family)})
$cases.push({name: "grapheme candidates before trimming"; input: Char:C90(9)+" "; separator: ""; flags: 3; options: {mode: "graphemes"; limits: {maxItems: 1}}; failure: True})
$cases.push({name: "grapheme units before trimming"; input: $crlf; separator: ""; flags: 3; options: {mode: "graphemes"; limits: {maxOutputUnits: 1}}; failure: True})
$cases.push({name: "invalid regex"; input: "abc"; separator: "*"; flags: 0; options: {mode: "regex"}; failure: True})
$cases.push({name: "invalid regex zero max"; input: "abc"; separator: "*"; flags: 0; options: {mode: "regex"; maxSplits: 0}; failure: True})
$cases.push({name: "unknown mode"; input: "abc"; separator: ","; flags: 0; options: {mode: "csv"}; failure: True})
$cases.push({name: "unknown option"; input: "abc"; separator: ","; flags: 0; options: {typo: True}; failure: True})
$cases.push({name: "wrong mode type"; input: "abc"; separator: ","; flags: 0; options: {mode: 1}; failure: True})
$cases.push({name: "empty separator member"; input: "abc"; separator: ""; flags: 0; options: {separators: New collection:C1472("")}; failure: True})
$cases.push({name: "nontext separator member"; input: "abc"; separator: ""; flags: 0; options: {separators: New collection:C1472(1)}; failure: True})
$cases.push({name: "list conflict"; input: "abc"; separator: ","; flags: 0; options: {separators: New collection:C1472("-")}; failure: True})
$cases.push({name: "flags conflict"; input: "abc"; separator: ","; flags: 0; options: {regexFlags: {multiline: True}}; failure: True})
$cases.push({name: "wrong regex flag"; input: "abc"; separator: ","; flags: 0; options: {mode: "regex"; regexFlags: {multiline: 1}}; failure: True})
$cases.push({name: "grapheme remainder conflict"; input: "abc"; separator: ""; flags: 0; options: {mode: "graphemes"; maxSplits: 1}; failure: True})
$cases.push({name: "input limit"; input: "abc"; separator: ","; flags: 0; options: {limits: {maxInputUnits: 2}}; failure: True})
$cases.push({name: "item limit"; input: "a,b,c"; separator: ","; flags: 0; options: {limits: {maxItems: 2}}; failure: True})
$cases.push({name: "candidate budget before filtering"; input: "a,,b,,c"; separator: ","; flags: 1; options: {limits: {maxItems: 3}}; failure: True})
$cases.push({name: "output limit"; input: "abcd"; separator: ","; flags: 0; options: {limits: {maxOutputUnits: 2}}; failure: True})
$cases.push({name: "units before trimming"; input: " a "; separator: ","; flags: 3; options: {limits: {maxOutputUnits: 1}}; failure: True})
$cases.push({name: "pattern limit"; input: "abcd"; separator: "abc"; flags: 0; options: {mode: "regex"; limits: {maxPatternUnits: 1}}; failure: True})
$cases.push({name: "invalid limit"; input: "abc"; separator: ","; flags: 0; options: {limits: {maxItems: -1}}; failure: True})
$cases.push({name: "raised ceiling"; input: "abc"; separator: ","; flags: 0; options: {limits: {maxItems: 100001}}; failure: True})
$cases.push({name: "fractional max"; input: "abc"; separator: ","; flags: 0; options: {maxSplits: 1.5}; failure: True})
$evil:=""
For ($index; 1; 2000)
	$evil:=$evil+"a"
End for
$cases.push({name: "regex budget"; input: $evil+"!"; separator: "(a+)+$"; flags: 0; options: {mode: "regex"; limits: {regexSteps: 1}}; failure: True})
$many:=New collection:C1472
For ($index; 1; 257)
	$many.push(",")
End for
$cases.push({name: "separator count"; input: "abc"; separator: ""; flags: 0; options: {separators: $many}; failure: True})
$private:=""
For ($index; 57344; 63743)
	$private:=$private+Char:C90($index)
End for
$cases.push({name: "trim sentinel collision"; input: " "+$private+" | b "; separator: ""; flags: 3; options: {separators: New collection:C1472("|")}; expected: New collection:C1472($private; "b")})
$cases.push({name: "success after failure"; input: ""; separator: ""; flags: 0; options: {mode: "graphemes"}; expected: New collection:C1472})
For each ($case; $cases)
	$actual:=Split_string_Ex($case.input; $case.separator; $case.flags; $case.options)
	If ($case.failure=True)
		$ok:=$actual=Null
	Else
		$ok:=check_collection($actual; $case.expected)
	End if
	If ($ok)
		$passed:=$passed+1
	Else
		$failures.push($case.name)
	End if
End for each
If ((sk mode regex#4) | (sk mode graphemes#8))
	$failures.push("mode constant values")
End if
$actual:=Split_string_Ex("a,b"; "[,]"; sk mode regex)
If (Not(check_collection($actual; New collection:C1472("a"; "b"))))
	$failures.push("regex constant omitted Object")
End if
$actual:=Split_string_Ex($combining+$family; ""; sk mode graphemes)
If (Not(check_collection($actual; New collection:C1472($combining; $family))))
	$failures.push("graphemes constant omitted Object")
End if
$actual:=Split_string_Ex($combining+$family; "."; sk mode regex+sk mode graphemes)
If (Not(check_collection($actual; New collection:C1472(""; ""; ""))))
	$failures.push("combined constants omitted Object")
End if
$unchanged:={mode: "regex"; limits: {regexSteps: 1}}
$before:=JSON Stringify:C1217($unchanged)
$actual:=Split_string_Ex("abc"; "*"; 0; $unchanged)
If ($actual#Null)
	$failures.push("explicit Null failure")
End if
If (Length:C16($before)#Length:C16(JSON Stringify:C1217($unchanged)))
	$failures.push("caller options mutated")
Else
	If (Position:C15($before; JSON Stringify:C1217($unchanged); *)#1)
		$failures.push("caller options mutated")
	End if
End if
For ($index; 1; 1000)
	$actual:=Split_string_Ex("a"+$nul+"😀,b"; ","; 0)
	If (Not(check_collection($actual; New collection:C1472("a"+$nul+"😀"; "b"))))
		$failures.push("repeated owned result")
	End if
End for
If (Position:C15("a"; "A"; *)#0)
	$failures.push("strict comparator case")
End if
If (Position:C15("é"; $combining; *)#0)
	$failures.push("strict comparator normalization")
End if
If (Position:C15(Char:C90(55296); Char:C90(55297); *)#0)
	$failures.push("strict comparator surrogate")
End if
$report:=New object:C1471("compiled"; Is compiled mode:C492; "passed"; $passed; "failures"; $failures; "nativeCases"; 1248; "extendedCases"; $cases.length)
LOG EVENT:C667(Into system standard outputs:K38:9; "SPLITTER_M1="+JSON Stringify:C1217($report); Information message:K38:1)
