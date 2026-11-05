#!/usr/bin/env python3
"""Extract and verify a Splitter package in a new isolated directory."""

import argparse
import hashlib
import json
import pathlib
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=pathlib.Path)
    parser.add_argument("destination", type=pathlib.Path)
    args = parser.parse_args()
    destination = args.destination.resolve()
    if destination.exists():
        raise RuntimeError("Extraction destination must not exist")
    with zipfile.ZipFile(args.archive) as archive:
        names = set()
        total_size = 0
        for entry in archive.infolist():
            if entry.orig_filename != entry.filename:
                raise RuntimeError(f"Normalized archive member: {entry.orig_filename!r}")
            path = pathlib.PurePosixPath(entry.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in entry.filename:
                raise RuntimeError(f"Unsafe archive member: {entry.filename}")
            if not path.parts or path.parts[0] != "Splitter.bundle":
                raise RuntimeError(f"Unexpected archive root: {entry.filename}")
            if entry.filename.casefold() in names or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise RuntimeError(f"Duplicate or symlink archive member: {entry.filename}")
            names.add(entry.filename.casefold())
            total_size += entry.file_size
            if total_size > 256 * 1024 * 1024 or len(names) > 1024:
                raise RuntimeError("Package extraction limit exceeded")
        archive.extractall(destination)
        for entry in archive.infolist():
            if not entry.is_dir():
                path = destination / entry.filename
                mode = (entry.external_attr >> 16) & 0o777
                if mode:
                    path.chmod(mode)
    bundle = destination / "Splitter.bundle"
    manifest = json.loads(
        (bundle / "Contents/Resources/build-manifest.json").read_text(encoding="utf-8")
    )
    expected = manifest["filesSha256"]
    actual = {
        path.relative_to(bundle).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in bundle.rglob("*")
        if path.is_file() and path.name != "build-manifest.json"
    }
    if expected != actual:
        raise RuntimeError("Extracted package hashes do not match its provenance manifest")
    print(f"Verified package: {bundle}")


if __name__ == "__main__":
    main()
