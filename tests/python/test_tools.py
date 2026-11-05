import importlib.util
import hashlib
import io
import pathlib
import plistlib
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("binary", ROOT / "scripts/binary.py")
BINARY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BINARY)
sys.path.insert(0, str(ROOT / "scripts"))
import fetch_host


class HostCacheTests(unittest.TestCase):
    def test_cached_archives_are_revalidated_without_network(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "host.tar.xz"
            archive.write_bytes(b"pinned host")
            entry = {"url": "https://invalid.example/host",
                     "sha256": hashlib.sha256(b"pinned host").hexdigest()}
            with mock.patch.object(fetch_host.urllib.request, "urlopen") as download:
                fetch_host.fetch_archive(entry, archive)
                download.assert_not_called()
                archive.write_bytes(b"corrupt")
                with self.assertRaisesRegex(RuntimeError, "checksum changed"):
                    fetch_host.fetch_archive(entry, archive)
                download.assert_not_called()

    def test_downloads_are_verified_before_use(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "host.tar.xz"
            entry = {"url": "https://invalid.example/host",
                     "sha256": hashlib.sha256(b"pinned host").hexdigest()}
            with mock.patch.object(fetch_host.urllib.request, "urlopen",
                                   return_value=io.BytesIO(b"pinned host")):
                fetch_host.fetch_archive(entry, archive)
            self.assertEqual(archive.read_bytes(), b"pinned host")
            bad = pathlib.Path(temp) / "bad.tar.xz"
            with mock.patch.object(fetch_host.urllib.request, "urlopen",
                                   return_value=io.BytesIO(b"wrong host")):
                with self.assertRaisesRegex(RuntimeError, "checksum changed"):
                    fetch_host.fetch_archive(entry, bad)


class BinaryTests(unittest.TestCase):
    def test_bundle_version_does_not_claim_runtime_success(self):
        with tempfile.TemporaryDirectory() as temp:
            contents = pathlib.Path(temp) / "tool4d.app/Contents"
            executable = contents / "MacOS/tool4d"
            executable.parent.mkdir(parents=True)
            with (contents / "Info.plist").open("wb") as target:
                plistlib.dump({"CFBundleShortVersionString": "21.1 build 21.100562"}, target)
            with mock.patch.object(BINARY.subprocess, "run") as run:
                self.assertEqual(BINARY.host_version(executable), "21.1 build 21.100562")
                run.assert_not_called()
            with (contents / "Info.plist").open("wb") as target:
                plistlib.dump({"CFBundleShortVersionString": 123}, target)
            with self.assertRaises(RuntimeError):
                BINARY.host_version(executable)

    def test_exact_native_machine_types(self):
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "binary"
            for cpu, expected in ((0x0100000C, "arm64"), (0x01000007, "x86_64")):
                path.write_bytes(struct.pack("<II", 0xFEEDFACF, cpu) + bytes(56))
                self.assertEqual(BINARY.architecture(path), expected)
            pe = bytearray(134)
            pe[:2] = b"MZ"
            struct.pack_into("<I", pe, 60, 128)
            pe[128:134] = b"PE\0\0\x64\x86"
            path.write_bytes(pe)
            self.assertEqual(BINARY.architecture(path), "x86_64")
            pe[132:134] = b"\x64\xaa"
            path.write_bytes(pe)
            with self.assertRaises(RuntimeError):
                BINARY.architecture(path)


class PackageTests(unittest.TestCase):
    def test_unsafe_members_are_rejected_before_extraction(self):
        for name in ("../escape", "/absolute", "Splitter.bundle/../escape", "Splitter.bundle\\escape"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                archive = pathlib.Path(temp) / "package.zip"
                destination = pathlib.Path(temp) / "output"
                with zipfile.ZipFile(archive, "w") as package:
                    package.writestr(name, "bad")
                result = subprocess.run(
                    [sys.executable, str(ROOT / "scripts/unpack.py"), str(archive), str(destination)],
                    capture_output=True, text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(destination.exists())

    def test_case_collisions_and_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "package.zip"
            destination = pathlib.Path(temp) / "output"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("Splitter.bundle/file", "first")
                package.writestr("Splitter.bundle/FILE", "second")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/unpack.py"), str(archive), str(destination)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(destination.exists())
            entry = zipfile.ZipInfo("Splitter.bundle/link")
            entry.external_attr = 0o120777 << 16
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr(entry, "/outside")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/unpack.py"), str(archive), str(destination)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
