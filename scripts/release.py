#!/usr/bin/env python3
"""Verify the manual Build pipeline's identity and release inputs before publication."""

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

from bump_version import read_version_sources, require_unused_tag


REPOSITORY = "miyako/4d-plugin-splitter"
WORKFLOW = ".github/workflows/build.yml"
SIGNED_FILES = {"Splitter-macos-signed.zip", "Splitter-macos-signed.dmg"}
RELEASE_FILES = SIGNED_FILES | {"Splitter-windows-x64.zip", "signing-provenance.json"}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def trusted_context(env):
    require(env["GITHUB_REPOSITORY"] == REPOSITORY, "Not the canonical repository")
    require(env["GITHUB_REF"] == "refs/heads/main", "Not main")
    require(env["GITHUB_EVENT_NAME"] == "workflow_dispatch", "Not a manual Build run")
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        require(re.fullmatch(r"[1-9][0-9]*", env[key]), f"Invalid {key}")
    require(re.fullmatch(r"[0-9a-f]{40}", env["GITHUB_SHA"]), "Invalid commit SHA")


def validate_run(run, workflow, env):
    trusted_context(env)
    require(env["SOURCE_RUN_ID"] == env["GITHUB_RUN_ID"], "Not the current Build run")
    require(run["id"] == int(env["GITHUB_RUN_ID"]), "Wrong run ID")
    require(run["run_attempt"] == int(env["GITHUB_RUN_ATTEMPT"]), "Wrong run attempt")
    require(run["repository"]["full_name"] == REPOSITORY, "Wrong repository")
    require(run["head_repository"]["full_name"] == REPOSITORY, "Fork build")
    require(workflow["path"] == WORKFLOW and run["path"] == WORKFLOW, "Wrong workflow path")
    require(run["workflow_id"] == workflow["id"], "Wrong workflow ID")
    require(run["event"] == "workflow_dispatch", "Untrusted build event")
    require(run["head_branch"] == "main", "Build is not from main")
    # The caller's needs:native gate establishes success of every native job.
    # The enclosing run cannot be completed yet: signing is part of that run.
    require(run["status"] == "in_progress" and run["conclusion"] is None, "Build is not active")
    require(run["head_sha"] == env["GITHUB_SHA"], "Build must match trusted workflow SHA")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_signed(directory, env):
    provenance = json.loads((directory / "signing-provenance.json").read_text(encoding="utf-8"))
    require(provenance["repository"] == REPOSITORY, "Wrong signing repository")
    require(provenance["gitRevision"] == env["GITHUB_SHA"], "Wrong signed source commit")
    require(provenance["sourceRunId"] == int(env["GITHUB_RUN_ID"]), "Wrong source run")
    require(provenance["sourceRunAttempt"] == int(env["GITHUB_RUN_ATTEMPT"]), "Wrong source attempt")
    require(provenance["sourceWorkflow"] == WORKFLOW, "Wrong source workflow")
    require(provenance["sourceEvent"] == "workflow_dispatch", "Wrong source event")
    require(provenance["signingRunId"] == env["GITHUB_RUN_ID"], "Wrong signing run")
    require(provenance["signingRunAttempt"] == env["GITHUB_RUN_ATTEMPT"], "Wrong signing attempt")
    require(provenance["signed"] is True and provenance["published"] is False,
            "Expected signed, unpublished artifacts")
    require(provenance["dmgStapled"] is True and provenance["zipStapled"] is False,
            "Unexpected stapling policy")
    require(set(provenance["notarization"]) == {"zip", "dmg"}, "Missing notarization results")
    require(all(result["status"] == "Accepted" for result in provenance["notarization"].values()),
            "Notarization was not accepted")
    require(provenance["finalArtifactsSha256"] == {
        name: sha(directory / name) for name in SIGNED_FILES
    }, "Signed artifact hashes do not match verified signing provenance")


def validate_windows(manifest, version, env):
    require(manifest["repository"] == REPOSITORY, "Wrong Windows repository")
    require(manifest["gitRevision"] == env["GITHUB_SHA"], "Wrong Windows source commit")
    require(manifest["version"] == version, "Wrong Windows version")
    require(manifest["architectures"] == ["x86_64"], "Wrong Windows architecture")
    require(manifest["configuration"] == "Release", "Not a Windows Release build")
    require(manifest["dirty"] is False, "Dirty Windows build")
    require(manifest["signed"] is False and manifest["published"] is False,
            "Unexpected Windows signing/publication policy")
    root = pathlib.Path(".")
    inputs = {
        root / "CMakeLists.txt", root / "LICENSE", root / "dependencies.lock.json",
        root / "src/plugin/splitter.cpp",
        *root.glob("src/core/*.cpp"), *root.glob("src/core/*.hpp"),
        *root.glob("cmake/*"), *root.glob("resources/*"), *root.glob("licenses/*"),
    }
    require(manifest["sourceSha256"] == {
        path.as_posix(): sha(path) for path in inputs if path.is_file()
    }, "Windows build inputs do not match the trusted checkout")


def prepare_release(directory, version, env):
    trusted_context(env)
    require({path.name for path in directory.iterdir()} == RELEASE_FILES,
            "Unexpected or missing release files")
    validate_signed(directory, env)
    destination = directory.parent / "release-windows-verified"
    subprocess.run([sys.executable, "scripts/unpack.py",
                    str(directory / "Splitter-windows-x64.zip"), str(destination)], check=True)
    manifest = json.loads(
        (destination / "Splitter.bundle/Contents/Resources/build-manifest.json").read_text(encoding="utf-8")
    )
    validate_windows(manifest, version, env)
    checksums = "".join(f"{sha(directory / name)}  {name}\n" for name in sorted(RELEASE_FILES))
    (directory / "SHA256SUMS").write_text(checksums, encoding="utf-8")
    (directory.parent / "release-notes.md").write_text(
        f"Splitter v{version}, built and verified from `{env['GITHUB_SHA']}`.\n\n"
        "- macOS: universal arm64/x86_64, Developer ID signed and notarized. "
        "The DMG is stapled; the ZIP is not.\n"
        "- Windows: native x64 package, unsigned.\n"
        "- Copy the entire `Splitter.bundle` into the host project's `Plugins/` folder.\n\n"
        "Verify downloads with `SHA256SUMS`, external `signing-provenance.json`, "
        "and the macOS signature. The sealed internal `build-manifest.json` remains "
        "unsigned-input provenance; `scripts/unpack.py` intentionally rejects signed ZIPs.\n\n"
        f"Build and platform/host verification: https://github.com/{REPOSITORY}/actions/runs/"
        f"{env['GITHUB_RUN_ID']}\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("version", "validate-run", "verify"))
    args = parser.parse_args()
    trusted_context(os.environ)
    if args.command == "validate-run":
        evidence = pathlib.Path(os.environ["EVIDENCE"])
        validate_run(json.loads((evidence / "native-run.json").read_text()),
                     json.loads((evidence / "native-workflow.json").read_text()), os.environ)
        print("Trusted current Build run validated; native checks are gated by job dependencies.")
    else:
        version, _ = read_version_sources()
        require_unused_tag(version)
        if args.command == "version":
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
                output.write(f"version={version}\n")
        else:
            require(version == os.environ["VERSION"], "Version changed after preflight")
            prepare_release(pathlib.Path("build/release"), version, os.environ)
            print(f"Release v{version} inputs verified; safe to create the immutable tag.")


if __name__ == "__main__":
    main()
