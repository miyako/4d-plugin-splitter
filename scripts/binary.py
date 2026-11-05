"""Minimal CPU identification for the native hosts and produced plug-ins."""

import pathlib
import plistlib
import struct
import subprocess


def host_version(path):
    executable = pathlib.Path(path)
    if executable.parent.name == "MacOS":
        # 21.1 --version can crash on hosted runners; this identifies the pinned
        # bundle only. Actual interpreted/compiled execution is checked separately.
        with (executable.parent.parent / "Info.plist").open("rb") as source:
            version = plistlib.load(source)["CFBundleShortVersionString"]
        if not isinstance(version, str) or not version:
            raise RuntimeError("Host bundle version must be nonempty text")
        return version
    result = subprocess.run([str(executable), "--version"], check=True,
                            capture_output=True, text=True, timeout=60)
    return result.stdout.strip()


def architecture(path):
    with pathlib.Path(path).open("rb") as binary:
        header = binary.read(64)
        if header[:4] == b"\xcf\xfa\xed\xfe":
            cpu = struct.unpack_from("<I", header, 4)[0]
            if cpu == 0x0100000C:
                return "arm64"
            if cpu == 0x01000007:
                return "x86_64"
        if header[:2] == b"MZ":
            offset = struct.unpack_from("<I", header, 60)[0]
            binary.seek(offset)
            pe = binary.read(6)
            if pe[:4] == b"PE\0\0" and struct.unpack_from("<H", pe, 4)[0] == 0x8664:
                return "x86_64"
    raise RuntimeError(f"Unsupported or non-thin native binary: {path}")
