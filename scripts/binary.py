"""Minimal CPU identification for the native hosts and produced plug-ins."""

import pathlib
import struct


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
