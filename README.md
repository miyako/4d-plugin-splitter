# Splitter

English | [日本語](README.ja.md)

Native 4D text toolkit in [`miyako/4d-plugin-splitter`](https://github.com/miyako/4d-plugin-splitter).
M1 (the first implementation milestone, not Apple M1) implements
native-compatible literal splitting, literal separator lists,
bounded ICU regular-expression splitting, and opt-in extended grapheme clusters.
CSV/TSV and the remaining toolkit are follow-on milestones, **not implemented APIs**.

Splitter is [MIT licensed](LICENSE). Distributed bundles include the project
license together with the complete ICU/data and 4D Plug-in SDK notices under
`Contents/Resources/licenses/`.

## Installation

Download from [Releases](https://github.com/miyako/4d-plugin-splitter/releases/latest).
Each release ships `Splitter-X.Y.Z.dmg` and `Splitter-X.Y.Z.zip` with **the same
cross-platform `Splitter.bundle`**: a universal arm64/x86_64 macOS binary
(Developer ID signed and notarized) and a Windows x64 binary (not Authenticode
signed). Either archive works on either platform; you can download on a Mac and
copy the bundle to Windows. The DMG is stapled, the ZIP is not.
Releases up to v0.1.3 shipped separate macOS-only and Windows-only packages; the
macOS packages from those releases do not load on Windows.
Ordinary push/PR builds remain unsigned per-platform Actions artifacts; the manual
**Build** workflow merges, signs and publishes new releases after verification.
Verify signed downloads using
the release's external `signing-provenance.json`, `SHA256SUMS` and macOS
signature. The internal `build-manifest.json` intentionally describes unsigned
macOS input provenance; unsigned-only `scripts/unpack.py` rejects the signed ZIP.
Quit the host, extract the ZIP or open the DMG, copy **the entire
`Splitter.bundle`** into the host project's `Plugins/` folder, and restart:

```text
Host/
  Project/
  Plugins/
    Splitter.bundle/
      Contents/
        MacOS/Splitter              # macOS: arm64 + x86_64
        Windows64/Splitter.4DX      # Windows: x64
        Resources/
          manifest.json
          constants.xlf
          icudt79l.dat
          licenses/
          dependencies.lock.json
          build-manifest.json
```

Platform packages contain their respective executable directory. The private
ICU 79.1 code is statically linked; matching full segmentation data and complete
upstream notices are bundled. Nothing downloads at runtime or uses OS/host ICU.
Missing data makes regex/grapheme calls fail with Null; native literal calls
remain independent of that data.

No component, namespace facade, CLI subprocess or component-private plug-in
loader is used. Commands occupy the host's global plug-in command space.
Check for an existing `Split_string_Ex` command or plug-in ID 20371 in your host;
the clean test fixture does not establish uniqueness in arbitrary installations.

## API

Manifest: **`Split_string_Ex(&T;&T;&L;&J):C`**.

```4d
$parts:=Split_string_Ex($text; $separator)
$parts:=Split_string_Ex($text; $separator; $nativeOptions)
$parts:=Split_string_Ex($text; $separator; $nativeOptions; $extensions)
$parts:=Split_string_Ex($text; $pattern; sk mode regex)
$parts:=Split_string_Ex($text; ""; sk mode graphemes)
```

Without mode bits, the first three arguments preserve native `Split string` semantics **within the
documented resource limits**. Text separators are whole literal strings, not
patterns or character lists. An empty separator retains native UTF-16 code-unit
behavior, not grapheme splitting. Native flags remain unchanged:
`sk ignore empty strings` = 1, `sk trim spaces` = 2, both = 3.

Custom constants `sk mode regex` = 4 and `sk mode graphemes` = 8 select
extended modes in the third argument. Add them to native flags, for example
`sk mode regex+sk trim spaces+sk ignore empty strings`.
Both mode bits together select regex splitting with grapheme-aware wildcard dots
and Unicode trimming when `sk trim spaces` is set.
The Object remains optional for separator lists, `maxSplits`, regex flags and
lower resource limits; mode selection alone no longer needs it.

| Mode | Selection | `sk trim spaces` behavior |
| --- | --- | --- |
| Literal / literal list | No mode bits; optional Object | Native 4D trimming |
| Regex | `sk mode regex` or `mode:"regex"` | Native 4D trimming |
| Graphemes | `sk mode graphemes` or `mode:"graphemes"` | Unicode `White_Space` per cluster |
| Regex + graphemes | Both mode bits | Unicode `White_Space` per result field |

Options 3 and 4 may be omitted. On the observed 20.7 compiler, missing plug-in
parameters emit advisory warning 533.4 but compilation succeeds; actual compiled
omission is exercised. A trailing Variant does **not** behave the same way, so
the fourth parameter is deliberately Object, not Variant. Pass a separators
Collection **inside** that Object, never directly as parameter 4.

The host rejects a direct Collection fourth in compiled code. In interpreted
code, it can coerce that wrong structured type to a null Object reference before
the plug-in sees it, making it indistinguishable from omission. Only Object or
Null is supported; the plug-in cannot recover a type already coerced by 4D.

**Success returns an actual Collection, including a valid empty Collection.
Failure returns Null alone.** Always check before using `.length` or iterating:

```4d
$parts:=Split_string_Ex($text; ","; sk mode regex)
If ($parts=Null)
    // Handle failure in the caller.
Else
    // Use the Collection, which may legitimately be empty.
End if
```

There is no last-error command/state, diagnostic Object, mutation of options,
or promise to invoke `ON ERR CALL`. This intentionally simple contract does not
distinguish invalid options/patterns, resource exhaustion, missing ICU data or
native failures. C++ exceptions are contained at the plug-in boundary.

### Extension Object

| Property | Meaning |
| --- | --- |
| `mode` | `"literal"` (default), `"literals"`, `"regex"` or `"graphemes"` |
| `separators` | Collection of nonempty Text delimiters; selects list mode if `mode` is absent |
| `maxSplits` | Nonnegative integer; consume at most N delimiters and preserve the entire remainder |
| `regexFlags` | Object of explicit Boolean matching flags, only in regex mode |
| `limits` | Object lowering finite resource ceilings below |

Unknown keys, invalid member types, conflicting settings and raised ceilings return Null.
An empty Object or Null fourth parameter retains native behavior.
Extended modes accept only native flag combinations 0/1/2/3.
Mode bits are removed before passing native flags to the host.
The Object's `mode` remains supported for existing callers. If mode bits and
an explicit `mode` are both provided, they must agree; combined bits agree
with `"regex"`. Separator lists cannot be combined with either mode bit.

### Literal lists and split limits

List mode requires an empty second Text parameter; the Object's Collection
supplies the delimiters. Choose the **earliest occurrence**, then **longest
matching separator**, then Collection order for any remaining tie.
Empty members are invalid; an empty Collection produces the unsplit source.

```4d
$parts:=Split_string_Ex("a---b::c"; ""; 0; {separators: New collection("-"; "---"; "::")})
// ["a","b","c"]

$parts:=Split_string_Ex("a,b,c"; ","; 0; {maxSplits: 1})
// ["a","b,c"], never ["a","b"] with the remainder discarded
```

`maxSplits:0` returns the unsplit source before explicit trimming/filtering,
including one empty field for empty input. Without this explicit extension,
native empty-input/empty-separator behavior remains unchanged.

### Regular expressions

The second parameter becomes a pattern **only** with `sk mode regex`
or the legacy Object setting `mode:"regex"`.
Delimiters and captured groups are not returned in M1.

```4d
$names:=Split_string_Ex("Bois-Joli / Morne-à-l’eau"; "\\s*/\\s*"; sk mode regex)
// ["Bois-Joli","Morne-à-l’eau"]

$tokens:=Split_string_Ex("Bois-Joli Morne-à-l’eau"; "[-’\\s]+"; sk mode regex)
// ["Bois","Joli","Morne","à","l","eau"]
```

Boolean `regexFlags` keys: `caseInsensitive`, `multiline`, `dotAll`, `comments`,
`unicodeWords`, `unixLines`. Other keys and non-Boolean values fail.
No unsupported canonical-equivalence flag is exposed.

An empty pattern and other zero-width matches progress safely by Unicode code
point while a separate output cursor preserves source data. Leading/trailing
empty fields are retained unless native options request otherwise.
`maxSplits` counts matched delimiters, including zero-width matches; its
remainder is retained unchanged before requested trim/filter.

### Regex + graphemes

```4d
$parts:=Split_string_Ex("e"+Char(769)+"👩‍💻x"; ".{2}"; sk mode regex+sk mode graphemes)
// ["","x"]: the delimiter consumes two entire grapheme clusters
```

An unescaped `.` outside character classes consumes an extended grapheme
cluster, like `\X`, but keeps dot's active newline exclusions. CRLF is never
partially consumed by a wildcard dot, including with `unixLines`.
`regexFlags.dotAll` or scoped/inline `(?s)` allows newline clusters too.
Escaped `\.`, dots in character classes, `\Q...\E` quoted text and regex
comments stay unchanged. Noncapturing expansion preserves capture numbering
and quantifier binding. Other regex atoms and zero-width advancement keep ICU's
normal semantics; this is not a change to every atom's matching unit.
Explicit `\X` still matches newline clusters independently of dot flags.
ICU restrictions still apply, including no variable-length `\X` in lookbehind.
Pattern limits count the caller's original pattern, not the internal expansion.
As in ordinary regex mode, the result contains fields **between** matched
delimiters, not the matched clusters.

With `sk trim spaces`, combined mode trims leading/trailing Unicode `White_Space`
(the same set as ICU regex `\s`) from each result field, even when the pattern
has no wildcard dots. This includes U+3000 ideographic space, NBSP, tabs and
line breaks; internal whitespace is preserved. Matching always sees the original,
untrimmed source, so anchors, lookarounds, delimiter matching and `maxSplits`
counts do not change. The remainder is trimmed only after matching, and candidate
item/output limits still apply before trimming/filtering.
Whitespace-only fields become empty strings; `sk ignore empty strings` removes
them **after** trimming. Without trim, fields are unchanged; ignore alone removes
only already-empty fields.

```4d
$parts:=Split_string_Ex("　やや　。、 ご機嫌　、斜め。"; "[、。]"; sk mode regex+sk mode graphemes+sk trim spaces+sk ignore empty strings)
// ["やや","ご機嫌","斜め"]
```

**Compatibility change:** combined mode previously delegated trimming to 4D.
It now removes more kinds of whitespace and can return fewer fields when ignore
is also set. Ordinary regex, literal and list modes retain native 4D semantics;
standalone grapheme Unicode trimming is unchanged.

### Graphemes

Use an empty second parameter and explicitly opt in:

```4d
$clusters:=Split_string_Ex($text; ""; sk mode graphemes)
```

Pinned ICU character boundaries implement extended grapheme clusters: surrogate
pairs, decomposed accents, ZWJ emoji, skin tones, regional-indicator flags and
CRLF sequences remain together. Empty input yields an empty Collection.
No normalization is performed; results are original substrings.
In this mode, `sk trim spaces` trims Unicode `White_Space` characters (the same
set as ICU regex `\s`) per field, including tabs, line breaks, non-breaking spaces
and ideographic spaces. Trimmed whitespace-only fields become empty strings;
add `sk ignore empty strings` to remove them. Neither flag changes the input.
`maxSplits`, separators lists and regex flags are invalid in grapheme mode.

Native literal calls, literal lists and ordinary regex mode use the real host's trimming/filtering rules;
they are not approximated with an ASCII or Unicode whitespace guess.
Internal spans are zero-based UTF-16 ranges, translated to the observed host's
one-based `Substring` positions. M1 does not expose token offsets. Code units,
code points and grapheme clusters are not interchangeable.

## Resource controls

Limits can only be lowered; all are positive integers.

| `limits` key | Hard ceiling |
| --- | ---: |
| `maxInputUnits` | 16,777,216 UTF-16 units (also bounds the second Text argument) |
| `maxPatternUnits` | 65,536 UTF-16 units |
| `maxItems` | 100,000 candidate fields |
| `maxOutputUnits` | 33,554,432 UTF-16 units across candidate fields |
| `regexSteps` | 1,000 ICU processing-limit units |
| `regexStackBytes` | 8,388,608 bytes of ICU backtracking heap storage |
| `operationBudgetMs` | 5,000 ms of cooperatively checked aggregate budget |

Lists additionally allow at most 256 separators and 65,536 combined separator
units. `maxSplits` must fit a nonnegative 32-bit integer.
Candidate limits apply **before** trimming and empty filtering; a call can fail
even if filtering would have produced a smaller final Collection.

ICU processing-limit units are engine work, **not guaranteed wall-clock
milliseconds**. Aggregate checks run between steps; they do not interrupt a
single host command, pattern compilation or blocked native call. This is not
process isolation or a hard wall-clock timeout.

## Build and verification

Requires CMake 3.24+, a C++17 compiler and Python 3.12+ for scripts.
Dependencies are immutable/checksum-pinned in
[`dependencies.lock.json`](dependencies.lock.json). No package manager, external
runtime process or host ICU is required.

```sh
cmake -S . -B build/universal -DCMAKE_BUILD_TYPE=Release \
  '-DCMAKE_OSX_ARCHITECTURES=arm64;x86_64' -DCMAKE_OSX_DEPLOYMENT_TARGET=12.0
cmake --build build/universal --parallel 2
ctest --test-dir build/universal --output-on-failure
python3 -m unittest discover -s tests/python -v
python3 scripts/package.py --build-dir build/universal --output dist/Splitter-macos-universal.zip
python3 scripts/unpack.py dist/Splitter-macos-universal.zip build/unpacked
python3 scripts/test_m1.py --tool4d /path/to/tool4d.app/Contents/MacOS/tool4d \
  --plugin build/unpacked/Splitter.bundle --report build/host-report.json
```

On a 4D 21+ host, add `--preemptive` to require the compiled eight-process
stress check and actual runtime-mode verification using `Process info`.
Without that flag, the report explicitly records the preemptive check as not
run. The baseline 20.7 fixture excludes these newer-command test methods.

Windows x64 uses `cmake -S . -B build -A x64`, then
`cmake --build build --config Release` and `ctest --test-dir build -C Release`.
Run packaging in an MSVC developer environment so `dumpbin` is available.
Static CRT and ICU code stay private; only the SDK entry point is exported.

The packager rebuilds, checks architecture, external dependencies, exports,
matching data and notices, and records source/binary hashes plus toolchain
provenance. ZIP extraction verifies paths, permissions and file hashes.
Normal build packages are unsigned. They are local files or Actions artifacts,
not automatically published releases; the manually published v0.1.0 downloads
are described under [Installation](#installation).

`scripts/fetch_host.py` restores a public host into a **new isolated directory**,
verifying both archive SHA-256 and host version against
[`tests/tool4d.lock.json`](tests/tool4d.lock.json). Download URLs are mutable;
a checksum change fails rather than silently accepting a new host. Optional
`--cache-dir` caches archives only and verifies their checksums on every restore.
The host itself is not shipped with Splitter.
On macOS, version identification uses the pinned bundle's plist: the 21.1
`--version` command crashed on hosted runners even after printing its version.
Metadata verification does **not** establish runtime compatibility; actual
source/compiled host runs must still exit successfully and pass every assertion.

[`native.yml`](.github/workflows/native.yml) builds a universal macOS package,
checks it on native arm64 and native Intel hosts, and builds/tests Windows x64.
The Intel job checks the **same universal package** produced by the arm64 job.
It also builds/tests independently with the native Intel toolchain. A separate
macOS 26 arm64 job checks the same package in eight actual compiled preemptive
processes on pinned 21.1; all three build platforms check interpreted and
compiled behavior on pinned 20.7. Dependency caches contain checksum-verified source/host archives, not
compiled libraries or credentials. Build/signing Actions use immutable revisions
and read-only permissions; normal builds never receive signing secrets.
Builds run on pull requests and main pushes without duplicate feature-push jobs.
Only the separate, manually dispatched **Build** pipeline can sign and publish
releases; push/PR checks cannot. Generated packages, host installations
and ongoing CI evidence stay in ignored `build/`/`dist/` or Actions artifacts.
The small checked-in JSON reports retain their original historical provenance.

### Preparing a version

Manually run **Bump version** ([`bump-version.yml`](.github/workflows/bump-version.yml))
from **main**, choosing `patch` (default), `minor` or `major`. It validates the
strict `X.Y.Z` version in `CMakeLists.txt` and requires both bundle version fields
in `cmake/Info.plist` and the package provenance version in `scripts/package.py`
to match. All four fields are updated together; published download links and
historical evidence are not changed. The workflow rejects an already-tagged
target `vX.Y.Z`, serializes bump runs, and commits/pushes to main without force.
It uses only `GITHUB_TOKEN` with `contents: write`; repository/branch rules must
allow that bot push. No PAT or additional secret is required.

The bump creates **no tag, build or release**. A `GITHUB_TOKEN` push does not
trigger the main-push build: separately dispatch **Build**
([`build.yml`](.github/workflows/build.yml)) from main at the new commit.
That single run handles all builds, tests, signing/notarization and release
publication. No run ID needs to be copied and no second signing dispatch is
required. A stale bump dispatch whose push is rejected must be rerun from
current main.

### Build, sign and release

After bumping, open Actions → **Build** → **Run workflow**, select **main**, and
run it once. It rejects versions whose tag already exists, builds/tests both
platforms using reusable [`native.yml`](.github/workflows/native.yml), then calls
[`sign-macos.yml`](.github/workflows/sign-macos.yml) only after **all native and
real-host checks succeed**. That job verifies both unsigned packages, requires
their shared resources to be byte-identical, merges `Contents/Windows64/Splitter.4DX`
into the universal bundle, then signs and notarizes the single cross-platform bundle. Both use the same dispatch commit and run. Native
jobs have read-only permissions and no signing secrets. Signing receives only
the six existing signing secrets; missing credentials or failed signing or
notarization fail the run and prevent publication.

The final isolated job verifies package hashes, source/run provenance and
accepted notarizations, then creates `vX.Y.Z` at the dispatch commit and publishes
a GitHub release containing `Splitter-X.Y.Z.dmg` and `Splitter-X.Y.Z.zip` (the same
cross-platform bundle), external `signing-provenance.json` and `SHA256SUMS`. Only that job receives
`contents: write`. It uses `GITHUB_TOKEN` directly, not a PAT or a tag-triggered
workflow; repository tag rules must allow creation of the version tag.
Tags and releases are never replaced. If tag creation succeeds but publication
fails, finish that release manually after inspecting the failed run; rerunning
Build deliberately rejects the existing tag.

Signing outputs and diagnostic logs remain available as Actions artifacts.
The DMG is stapled; the ZIP is not. The unchanged internal build manifest describes the
unsigned macOS input (the merged Windows binary is recorded in `windowsInput` of
`signing-provenance.json`); signed ZIPs intentionally fail unsigned-only `unpack.py`
verification and must instead be checked against their external signing
provenance and macOS signature.

Required repository secret names: `APPLE_DEVELOPER_ID_CERTIFICATE`,
`APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD`, `KEYCHAIN_PASSWORD`,
`NOTARYTOOL_APPLE_ID`, `NOTARYTOOL_PASSWORD`, `NOTARYTOOL_TEAM_ID`.
Only the user runs their local secret-setup helper. Ordinary push/PR build/test
CI does not depend on these secrets. Signing/notarization requires an actual credentialed
run to succeed; the [v0.1.0 signing run](https://github.com/miyako/4d-plugin-splitter/actions/runs/42151065472)
succeeded with both notarizations Accepted before manual publication.

### Evidence and support boundaries

Compatibility targets: **4D 20.7 LTS onward**, macOS universal arm64/x86_64 and
Windows x64. macOS binaries target 12.0 or later. These are not blanket claims
for every later 4D or OS release. The macOS 12.0 minimum runtime and GUI
workflows were not tested. The table below preserves historical local runs,
not the later release validation summarized in [v0.1.0](https://github.com/miyako/4d-plugin-splitter/releases/tag/v0.1.0).

| Observed host on macOS 26.7 | Execution | Source / compiled |
| --- | --- | --- |
| [20.7 build 20.101905, arm64](tests/evidence/m1-macos-arm64-20.7.json) | Native | 1,294 assertions passed per mode |
| [21.1 build 21.100468, arm64](tests/evidence/m1-macos-arm64-21.1.json) | Native | 1,294 assertions passed per mode |
| [20.7 build 20.101905, x86_64](tests/evidence/m1-macos-x86_64-translated-20.7.json) | Rosetta translation | 1,294 assertions passed per mode |
| Physical Intel / Windows x64 | CI configured, not run here | Not claimed |

The native core passed 31,185 checks on arm64 and on the translated x86_64
slice, including eight-thread stress. Translated execution is not native Intel
validation. Remote platform results and downloadable evidence are available in
the [native workflow runs](https://github.com/miyako/4d-plugin-splitter/actions/workflows/native.yml);
only completed successful jobs establish those additional observations.

The host runner asserts actual interpreted and compiled execution, native
parity across 1,248 cases per mode, extended Unicode/regex/list/error/limit
cases, repeated ownership, and explicit missing/truncated-data failure without host ICU
fallback. Source/compiled mode is never inferred merely from a launch flag.
The production manifest enables **`threadSafe:true`** at the user's explicit
request. This declaration permits preemptive use; it is not itself proof of
bridge safety. The reports above preserve the earlier `threadSafe:false`
package provenance. With `--preemptive`, the host runner additionally checks
eight compiled preemptive processes, verifies their actual runtime mode, and
exercises all four split modes, failure isolation and concurrent first-use ICU
initialization.
New enabled-package reports record 1,294 source and compiled assertions per
mode on [native arm64 20.7](tests/evidence/m1-threadsafe-macos-arm64-20.7.json)
and [native arm64 21.1](tests/evidence/m1-threadsafe-macos-arm64-21.1.json).
The 21.1 run additionally passed 9,600 assertions across eight processes
confirmed preemptive at runtime. The 20.7 run did **not** validate preemptive
execution: its compiler does not support the newer `Process info` observer.
This limited macOS evidence is not a general bridge-safety certification;
these local reports do not establish Windows, native Intel or 20.7 preemptive
support. Consult the corresponding CI evidence for remote platform observations.

Earlier SDK investigations remain under `tests/evidence/` as historical
observations, not current blockers: Variant omission fails, typed Longint and
Object omission succeeds with warning-only compilation, and SDK assertions do
not invoke the host handler. Historical probes are opt-in with
`-DSPLITTER_BUILD_PROBES=ON` and build separately under `build/probes/`; they are
never registered in the production bundle.

## Follow-on toolkit

Next milestones preserve the agreed scope: structured positions and retained
delimiters/captures; lines with CRLF/LF/CR and final-empty policy;
partition/rpartition and scan/extract; strict incremental CSV/TSV **read and
write**, text-preserving fields, explicit dialect/header settings and opt-in
formula protection; locale-aware words/sentences and documented identifier
rules; reusable compiled patterns and batch APIs with bounded, lifetime-safe
handles. CSV library licensing and detailed CSV diagnostics remain decisions
for that milestone. No stemming, implicit type coercion, performance,
release-readiness or unexecuted-platform claim is made.
