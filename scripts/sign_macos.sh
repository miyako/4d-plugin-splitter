#!/bin/bash
# Manual CI-only signing of a previously verified native build, never a rebuild.
set +x
set -euo pipefail
umask 077

cd "$(dirname "$0")/.."
ROOT="$PWD"
WORK="$ROOT/build/macos-signing"
EVIDENCE="$WORK/evidence"
OUTPUT="$WORK/output"
PRIVATE="$WORK/private"
KEYCHAIN="$PRIVATE/signing.keychain-db"
CERTIFICATE="$PRIVATE/developer-id.p12"
BUNDLE="$WORK/unpacked/Splitter.bundle"
export ROOT WORK EVIDENCE OUTPUT BUNDLE

cleanup() {
    # Never touch the login keychain or remove unrelated runner files.
    if [[ -f "$PRIVATE/original-keychains.txt" ]]; then
        python3 - "$PRIVATE/original-keychains.txt" <<'PY'
import pathlib, shlex, subprocess, sys
keychains = shlex.split(pathlib.Path(sys.argv[1]).read_text())
subprocess.run(["security", "list-keychains", "-d", "user", "-s", *keychains], check=True)
PY
        rm -f -- "$PRIVATE/original-keychains.txt"
    fi
    if [[ -f "$KEYCHAIN" ]]; then
        security delete-keychain "$KEYCHAIN" || return 1
    fi
    rm -f -- "$CERTIFICATE" "$KEYCHAIN" "$KEYCHAIN-shm" "$KEYCHAIN-wal"
    if [[ -d "$PRIVATE" ]]; then
        rmdir "$PRIVATE"
    fi
}

validate_run() {
    python3 - <<'PY'
import json
import os
import pathlib
import re

evidence = pathlib.Path(os.environ["EVIDENCE"])
run = json.loads((evidence / "native-run.json").read_text())
workflow = json.loads((evidence / "native-workflow.json").read_text())
run_id = os.environ["SOURCE_RUN_ID"]
repo = "miyako/4d-plugin-splitter"
assert re.fullmatch(r"[1-9][0-9]*", run_id), "Invalid run ID"
assert os.environ["GITHUB_REPOSITORY"] == repo, "Not the canonical repository"
assert os.environ["GITHUB_REF"] == "refs/heads/main", "Not main"
assert os.environ["GITHUB_EVENT_NAME"] == "workflow_dispatch", "Not a manual signing run"
assert run["id"] == int(run_id), "Wrong run ID"
assert run["repository"]["full_name"] == repo, "Wrong repository"
assert run["head_repository"]["full_name"] == repo, "Fork build"
assert workflow["path"] == ".github/workflows/native.yml", "Wrong workflow path"
assert run["workflow_id"] == workflow["id"], "Wrong workflow ID"
assert run["path"] == workflow["path"], "Wrong run workflow path"
assert run["event"] in ("push", "workflow_dispatch"), "Untrusted build event"
assert run["head_branch"] == "main", "Build is not from main"
assert run["status"] == "completed" and run["conclusion"] == "success", "Build not successful"
assert run["head_sha"] == os.environ["GITHUB_SHA"], "Build must match trusted workflow SHA"
print("Trusted successful native.yml run validated at the signing workflow commit.")
PY
}

prepare() {
    [[ ! -e "$WORK/unpacked" && ! -e "$WORK/prepared.json" ]]
    python3 scripts/unpack.py "$WORK/incoming/Splitter-macos-universal.zip" "$WORK/unpacked"
    python3 - <<'PY'
import hashlib
import json
import os
import pathlib
import shutil

root = pathlib.Path(os.environ["ROOT"])
work = pathlib.Path(os.environ["WORK"])
bundle = pathlib.Path(os.environ["BUNDLE"])
evidence = pathlib.Path(os.environ["EVIDENCE"])
run = json.loads((evidence / "native-run.json").read_text())
manifest_path = bundle / "Contents/Resources/build-manifest.json"
manifest = json.loads(manifest_path.read_text())
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

assert manifest["repository"] == "miyako/4d-plugin-splitter"
assert manifest["gitRevision"] == os.environ["GITHUB_SHA"] == run["head_sha"]
assert manifest["dirty"] is False, "Build source was dirty"
assert manifest["signed"] is False and manifest["published"] is False
assert manifest["configuration"] == "Release"
assert manifest["architectures"] == ["arm64", "x86_64"]
inputs = {
    root / "CMakeLists.txt", root / "LICENSE", root / "dependencies.lock.json", root / "src/plugin/splitter.cpp",
    *root.glob("src/core/*.cpp"), *root.glob("src/core/*.hpp"),
    *root.glob("cmake/*"), *root.glob("resources/*"), *root.glob("licenses/*"),
}
assert manifest["sourceSha256"] == {
    p.relative_to(root).as_posix(): sha(p) for p in inputs if p.is_file()
}, "Build inputs do not match the trusted checkout"
resources = bundle / "Contents/Resources"
lock = json.loads((root / "dependencies.lock.json").read_text())
assert sha(resources / "icudt79l.dat") == lock["icu"]["data_sha256"]
for source, target in (
    (root / "resources/manifest.json", resources / "manifest.json"),
    (root / "dependencies.lock.json", resources / "dependencies.lock.json"),
    (root / "cmake/Info.plist", bundle / "Contents/Info.plist"),
    (root / "licenses/4D-Plugin-SDK.txt", resources / "licenses/4D-Plugin-SDK.txt"),
    (root / "LICENSE", resources / "licenses/Splitter-MIT.txt"),
):
    assert sha(source) == sha(target), f"Unexpected resource: {target.name}"
assert (resources / "licenses/ICU-LICENSE.txt").is_file()
assert {p.name for p in (bundle / "Contents/MacOS").iterdir()} == {"Splitter"}, \
    "Unexpected nested code; signing policy must be updated explicitly"
assert not (bundle / "Contents/Windows64").exists(), "Not a macOS-only package"
shutil.copyfile(manifest_path, evidence / "unsigned-build-manifest.json")
provenance = {
    "repository": manifest["repository"],
    "sourceRunId": run["id"],
    "sourceRunAttempt": run["run_attempt"],
    "sourceWorkflow": run["path"],
    "sourceEvent": run["event"],
    "gitRevision": manifest["gitRevision"],
    "unsignedInput": {
        "name": "Splitter-macos-universal.zip",
        "sha256": sha(work / "incoming/Splitter-macos-universal.zip"),
    },
    "unsignedBuildManifestSha256": sha(manifest_path),
}
(work / "prepared.json").write_text(json.dumps(provenance, indent=2) + "\n")
shutil.copyfile(work / "prepared.json", evidence / "unsigned-input.json")
PY
    [[ "$(lipo -archs "$BUNDLE/Contents/MacOS/Splitter")" == "x86_64 arm64" \
        || "$(lipo -archs "$BUNDLE/Contents/MacOS/Splitter")" == "arm64 x86_64" ]]
    lipo "$BUNDLE/Contents/MacOS/Splitter" -verify_arch arm64 x86_64
    echo "Unsigned package and provenance verified; no downloaded code was executed."
}

notarize() {
    local file="$1" label="$2" rc status submission
    if xcrun notarytool submit "$file" --keychain "$KEYCHAIN" \
        --keychain-profile splitter-notary --wait --output-format json \
        > "$EVIDENCE/$label-submit.json" 2> "$EVIDENCE/$label-submit.stderr"; then
        rc=0
    else
        rc=$?
    fi
    cat "$EVIDENCE/$label-submit.stderr" "$EVIDENCE/$label-submit.json"
    status="$(python3 - "$EVIDENCE/$label-submit.json" <<'PY'
import json, sys
try:
    print(json.load(open(sys.argv[1])).get("status", "Unknown"))
except (ValueError, OSError):
    print("Unknown")
PY
)"
    if [[ "$rc" -ne 0 || "$status" != Accepted ]]; then
        submission="$(python3 - "$EVIDENCE/$label-submit.json" <<'PY'
import json, re, sys
try:
    value = json.load(open(sys.argv[1])).get("id", "")
    print(value if re.fullmatch(r"[0-9a-fA-F-]{36}", value) else "")
except (ValueError, OSError):
    print("")
PY
)"
        if [[ -n "$submission" ]]; then
            if ! xcrun notarytool log "$submission" --keychain "$KEYCHAIN" \
                --keychain-profile splitter-notary "$EVIDENCE/$label-notary-log.json" \
                2> "$EVIDENCE/$label-notary-log.stderr"; then
                echo "::warning::Could not retrieve $label notarization log."
            fi
            cat "$EVIDENCE/$label-notary-log.stderr"
            if [[ -f "$EVIDENCE/$label-notary-log.json" ]]; then
                cat "$EVIDENCE/$label-notary-log.json"
            fi
        fi
        echo "::error::$label notarization did not succeed (exit $rc, status $status)."
        [[ "$rc" -ne 0 ]] || rc=1
        return "$rc"
    fi
}

sign() {
    local missing name identity details
    echo "signed=false" >> "$GITHUB_OUTPUT"
    missing="$(python3 - <<'PY'
import os
names = (
    "APPLE_DEVELOPER_ID_CERTIFICATE", "APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD",
    "KEYCHAIN_PASSWORD", "NOTARYTOOL_APPLE_ID", "NOTARYTOOL_PASSWORD", "NOTARYTOOL_TEAM_ID",
)
print("\n".join(name for name in names if not os.environ.get(name)))
PY
)"
    if [[ -n "$missing" ]]; then
        while IFS= read -r name; do
            echo "::warning::Signing skipped: missing $name."
        done <<< "$missing"
        echo "Signing/notarization SKIPPED: one or more required secrets are missing." \
            | tee "$EVIDENCE/signing-skipped.txt" >> "$GITHUB_STEP_SUMMARY"
        return 0
    fi
    [[ -f "$WORK/prepared.json" && -d "$BUNDLE" && ! -e "$PRIVATE" && ! -e "$OUTPUT" ]]
    mkdir -p "$PRIVATE" "$OUTPUT"
    trap cleanup EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    printf '%s' "$APPLE_DEVELOPER_ID_CERTIFICATE" | /usr/bin/base64 --decode > "$CERTIFICATE"
    echo "Preparing isolated signing keychain."
    security list-keychains -d user > "$PRIVATE/original-keychains.txt"
    security create-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN"
    security set-keychain-settings -lut 3600 "$KEYCHAIN"
    security unlock-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN"
    python3 - "$PRIVATE/original-keychains.txt" "$KEYCHAIN" <<'PY'
import pathlib, shlex, subprocess, sys
keychains = shlex.split(pathlib.Path(sys.argv[1]).read_text())
subprocess.run(["security", "list-keychains", "-d", "user", "-s", sys.argv[2], *keychains],
               check=True)
PY
    echo "Importing Developer ID certificate."
    security import "$CERTIFICATE" -P "$APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD" \
        -t cert -f pkcs12 -k "$KEYCHAIN" -T /usr/bin/codesign -T /usr/bin/security
    rm -f -- "$CERTIFICATE"
    echo "Allowing codesign access to the private key."
    security set-key-partition-list -S apple-tool:,apple:,codesign: -s \
        -k "$KEYCHAIN_PASSWORD" "$KEYCHAIN" > /dev/null
    echo "Resolving Developer ID identity."
    identity="$(security find-identity -v -p codesigning "$KEYCHAIN" \
        | sed -nE 's/.* ([0-9A-F]{40}) "Developer ID Application:.*".*/\1/p')"
    [[ "$identity" =~ ^[0-9A-F]{40}$ ]] || {
        echo "::error::Expected exactly one valid Developer ID Application identity."
        return 1
    }
    echo "Storing notarization credentials."
    xcrun notarytool store-credentials splitter-notary --keychain "$KEYCHAIN" \
        --apple-id "$NOTARYTOOL_APPLE_ID" --password "$NOTARYTOOL_PASSWORD" \
        --team-id "$NOTARYTOOL_TEAM_ID" > /dev/null
    # Preserve the original manifest as unsigned-build provenance, then seal it unchanged.
    echo "Signing universal plug-in."
    codesign --force --timestamp --options runtime --keychain "$KEYCHAIN" \
        --sign "$identity" "$BUNDLE"
    codesign --verify --deep --strict --verbose=2 "$BUNDLE" \
        2> "$EVIDENCE/codesign-verify.log"
    details="$(codesign --display --verbose=4 "$BUNDLE" 2>&1)"
    printf '%s\n' "$details" | grep -Fx "TeamIdentifier=$NOTARYTOOL_TEAM_ID" > /dev/null
    printf '%s\n' "$details" | grep -E 'flags=.*runtime' > /dev/null
    echo "Developer ID identity, expected team, and hardened runtime verified." \
        > "$EVIDENCE/signing-policy.log"
    ditto -c -k --sequesterRsrc --keepParent "$BUNDLE" "$OUTPUT/Splitter-macos-signed.zip"
    notarize "$OUTPUT/Splitter-macos-signed.zip" zip
    mkdir "$WORK/dmg-root"
    ditto "$BUNDLE" "$WORK/dmg-root/Splitter.bundle"
    hdiutil create -volname Splitter -srcfolder "$WORK/dmg-root" -format UDZO \
        "$OUTPUT/Splitter-macos-signed.dmg" > "$EVIDENCE/dmg-create.log"
    codesign --timestamp --options runtime --keychain "$KEYCHAIN" --sign "$identity" \
        "$OUTPUT/Splitter-macos-signed.dmg"
    codesign --verify --strict --verbose=2 "$OUTPUT/Splitter-macos-signed.dmg" \
        2> "$EVIDENCE/dmg-codesign-verify.log"
    notarize "$OUTPUT/Splitter-macos-signed.dmg" dmg
    xcrun stapler staple "$OUTPUT/Splitter-macos-signed.dmg" > "$EVIDENCE/staple.log" 2>&1
    xcrun stapler validate "$OUTPUT/Splitter-macos-signed.dmg" > "$EVIDENCE/staple-validate.log" 2>&1
    python3 - <<'PY'
import hashlib
import json
import os
import pathlib

work = pathlib.Path(os.environ["WORK"])
output = pathlib.Path(os.environ["OUTPUT"])
evidence = pathlib.Path(os.environ["EVIDENCE"])
provenance = json.loads((work / "prepared.json").read_text())
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

manifest = pathlib.Path(os.environ["BUNDLE"]) / "Contents/Resources/build-manifest.json"
assert sha(manifest) == provenance["unsignedBuildManifestSha256"], "Unsigned manifest was changed"
provenance.update({
    "signingRunId": os.environ["GITHUB_RUN_ID"],
    "signingRunAttempt": os.environ["GITHUB_RUN_ATTEMPT"],
    "signed": True,
    "published": False,
    "notarization": {
        label: json.loads((evidence / f"{label}-submit.json").read_text())
        for label in ("zip", "dmg")
    },
    "dmgStapled": True,
    "zipStapled": False,
    "finalArtifactsSha256": {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()},
    "manifestSemantics": (
        "The sealed internal build-manifest.json is unchanged unsigned-build provenance. "
        "Its executable hash and signed=false describe the unsigned input, not these signed outputs. "
        "scripts/unpack.py is an unsigned-package verifier and rejects the signed ZIP. "
        "Verify these external final hashes and use codesign to verify the signed bundle instead."
    ),
})
assert all(v["status"] == "Accepted" for v in provenance["notarization"].values())
text = json.dumps(provenance, indent=2) + "\n"
(output / "signing-provenance.json").write_text(text)
(evidence / "signing-provenance.json").write_text(text)
PY
    cleanup
    trap - EXIT INT TERM
    echo "signed=true" >> "$GITHUB_OUTPUT"
    echo "Developer ID signatures verified; ZIP and DMG notarization Accepted; DMG stapled. Artifacts only." \
        >> "$GITHUB_STEP_SUMMARY"
}

[[ "${GITHUB_ACTIONS:-}" == true && "${RUNNER_OS:-}" == macOS ]] || {
    echo "This script is restricted to the manual macOS GitHub Actions workflow." >&2
    exit 1
}
case "${1:-}" in
    validate-run) validate_run ;;
    prepare) prepare ;;
    sign) sign ;;
    cleanup) cleanup ;;
    *) echo "Usage: $0 {validate-run|prepare|sign|cleanup}" >&2; exit 2 ;;
esac
