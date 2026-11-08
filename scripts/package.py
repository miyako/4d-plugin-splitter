#!/usr/bin/env python3
"""Rebuild, validate and zip a local host-installed Splitter bundle; never publish."""

import argparse
import hashlib
import json
import pathlib
import platform
import re
import shutil
import subprocess
import zipfile

from binary import architecture
from check_host import ROOT


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def output(*command):
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--configuration", default="Release", choices=("Release", "Debug", "RelWithDebInfo"))
    parser.add_argument("--macos-architectures", default="universal", choices=("universal", "arm64", "x86_64"))
    args = parser.parse_args()
    build = args.build_dir.resolve(strict=True)
    subprocess.run(["cmake", "--build", str(build), "--config", args.configuration,
                    "--target", "Splitter", "--parallel", "2"], check=True)
    bundle = build / "plugins/Splitter.bundle"
    resources = bundle / "Contents/Resources"
    lock = json.loads((ROOT / "dependencies.lock.json").read_text(encoding="utf-8"))
    # Resource-only edits also need to be reflected when no relink was necessary.
    for source, target in (
        (ROOT / "resources/manifest.json", resources / "manifest.json"),
        (ROOT / "resources/constants.xlf", resources / "constants.xlf"),
        (ROOT / "dependencies.lock.json", resources / "dependencies.lock.json"),
        (ROOT / "cmake/Info.plist", bundle / "Contents/Info.plist"),
        (ROOT / "licenses/4D-Plugin-SDK.txt", resources / "licenses/4D-Plugin-SDK.txt"),
        (ROOT / "LICENSE", resources / "licenses/Splitter-MIT.txt"),
    ):
        shutil.copyfile(source, target)
    manifest = json.loads((resources / "manifest.json").read_text(encoding="utf-8"))
    if manifest["commands"] != [{
        "theme": "Splitter",
        "syntax": "Split_string_Ex(&T;&T;&L;&J):C",
        "threadSafe": True,
    }]:
        raise RuntimeError("Package command registration does not match the M1 contract")
    if sha(resources / "icudt79l.dat") != lock["icu"]["data_sha256"]:
        raise RuntimeError("Bundled ICU data does not match the pinned source")
    if not (resources / "licenses/ICU-LICENSE.txt").is_file():
        raise RuntimeError("Complete ICU/data redistribution notices are missing")
    dependency_inspection = ""
    if platform.system() == "Darwin":
        binary = bundle / "Contents/MacOS/Splitter"
        arches = set(output("lipo", "-archs", str(binary)).split())
        required = {"arm64", "x86_64"} if args.macos_architectures == "universal" else {args.macos_architectures}
        if arches != required:
            raise RuntimeError(f"Wrong macOS slices: {arches}, expected {required}")
        subprocess.run(["lipo", str(binary), "-verify_arch", *sorted(required)], check=True)
        dependency_inspection = output("otool", "-L", str(binary))
        if re.search(r"libicu|icu(?:uc|in|dt)\d", dependency_inspection, re.IGNORECASE):
            raise RuntimeError("The plug-in unexpectedly depends on an external ICU")
        symbols = output("nm", "-gU", str(binary))
        exports = set(re.findall(r"^\s*[0-9a-fA-F]+\s+[A-Z]\s+(\S+)", symbols, re.MULTILINE))
        if exports != {"_FourDPackex"}:
            raise RuntimeError(f"Private ICU/SDK symbols are exported: {exports}")
    elif platform.system() == "Windows":
        binary = bundle / "Contents/Windows64/Splitter.4DX"
        if architecture(binary) != "x86_64":
            raise RuntimeError("Windows plug-in is not x64")
        arches = {"x86_64"}
        dependency_inspection = output("dumpbin", "/nologo", "/dependents", str(binary))
        if re.search(r"icu\w*\.dll", dependency_inspection, re.IGNORECASE):
            raise RuntimeError("The plug-in unexpectedly depends on an external ICU DLL")
        symbols = output("dumpbin", "/nologo", "/exports", str(binary))
        exports = set(re.findall(
            r"^\s*\d+\s+[0-9A-Fa-f]+\s+[0-9A-Fa-f]+\s+(\w+)", symbols, re.MULTILINE
        ))
        if exports != {"FourDPackex"}:
            raise RuntimeError(f"Unexpected Windows exports: {exports}")
    else:
        raise RuntimeError("Packaging requires a native macOS or Windows builder")
    inputs = {
        ROOT / "CMakeLists.txt",
        ROOT / "LICENSE",
        ROOT / "dependencies.lock.json",
        ROOT / "src/plugin/splitter.cpp",
        *ROOT.glob("src/core/*.cpp"),
        *ROOT.glob("src/core/*.hpp"),
        *ROOT.glob("cmake/*"),
        *ROOT.glob("resources/*"),
        *ROOT.glob("licenses/*"),
    }
    provenance = {
        "repository": "miyako/4d-plugin-splitter",
        "version": "0.1.3",
        "configuration": args.configuration,
        "architectures": sorted(arches),
        "gitRevision": output("git", "-C", str(ROOT), "rev-parse", "HEAD").strip(),
        "dirty": bool(output("git", "-C", str(ROOT), "status", "--porcelain").strip()),
        "toolchain": json.loads((build / "build-toolchain.json").read_text(encoding="utf-8")),
        "sourceSha256": {
            path.relative_to(ROOT).as_posix(): sha(path) for path in sorted(inputs) if path.is_file()
        },
        "filesSha256": {
            path.relative_to(bundle).as_posix(): sha(path)
            for path in sorted(bundle.rglob("*"))
            if path.is_file() and path.name != "build-manifest.json"
        },
        "nativeDependencies": dependency_inspection,
        "signed": False,
        "published": False,
        "threadSafe": manifest["commands"][0]["threadSafe"],
    }
    (resources / "build-manifest.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(bundle.rglob("*")):
            if path.is_symlink():
                raise RuntimeError(f"Unexpected package symlink: {path}")
            if path.is_file():
                archive.write(path, pathlib.PurePosixPath(bundle.name) / path.relative_to(bundle).as_posix())
    print(f"Created unsigned local package: {args.output} (sha256 {sha(args.output)})")


if __name__ == "__main__":
    main()
