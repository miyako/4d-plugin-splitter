#!/usr/bin/env python3
"""Restore a checksum-pinned public tool4d host into a new isolated directory."""

import argparse
import hashlib
import json
import pathlib
import shutil
import tarfile
import tempfile
import urllib.request

from check_host import ROOT
from binary import host_version


def fetch_archive(entry, archive):
    digest = hashlib.sha256()
    total = 0
    if not archive.exists():
        with urllib.request.urlopen(entry["url"], timeout=120) as response, archive.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 1024 * 1024 * 1024:
                    raise RuntimeError("Host archive exceeds the download ceiling")
                output.write(chunk)
    total = 0
    with archive.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            total += len(chunk)
            if total > 1024 * 1024 * 1024:
                raise RuntimeError("Host archive exceeds the download ceiling")
            digest.update(chunk)
    if digest.hexdigest() != entry["sha256"]:
        raise RuntimeError("Host archive checksum changed; review and repin explicitly")


def extract_archive(archive, destination):
    with tarfile.open(archive, "r:*") as bundle:
        bundle.extractall(destination, filter="data")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=("macos-arm64", "macos-x86_64",
                                             "windows-x64", "macos-arm64-21.1"), required=True)
    parser.add_argument("--destination", type=pathlib.Path, required=True)
    parser.add_argument("--cache-dir", type=pathlib.Path,
                        help="Cache archives only; checksums are verified on every restore")
    args = parser.parse_args()
    destination = args.destination.resolve()
    if destination.exists():
        raise RuntimeError(f"Destination must not exist: {destination}")
    lock = json.loads((ROOT / "tests/tool4d.lock.json").read_text(encoding="utf-8"))
    entry = lock[args.platform]
    expected_version = entry.get("version", lock["version"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tool4d-", dir=destination.parent) as temp:
        temp = pathlib.Path(temp)
        archive = temp / "host.tar.xz"
        if args.cache_dir:
            cache = args.cache_dir.resolve()
            cache.mkdir(parents=True, exist_ok=True)
            archive = cache / (entry["sha256"] + ".tar.xz")
        fetch_archive(entry, archive)
        extracted = temp / "host"
        extracted.mkdir()
        extract_archive(archive, extracted)
        executable = extracted / entry["executable"]
        version = host_version(executable)
        if version != expected_version:
            raise RuntimeError(f"Unexpected host version: {version!r}")
        shutil.move(str(extracted), str(destination))
    print(f"Verified {expected_version} ({args.platform}): {destination / entry['executable']}")


if __name__ == "__main__":
    main()
