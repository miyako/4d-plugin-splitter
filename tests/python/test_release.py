import copy
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import release


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = pathlib.Path(self.temp.name)
        self.repo = self.base / "checkout"
        self.repo.mkdir()
        previous = pathlib.Path.cwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, previous)
        inputs = {
            ROOT / "CMakeLists.txt", ROOT / "LICENSE", ROOT / "dependencies.lock.json",
            ROOT / "src/plugin/splitter.cpp",
            *ROOT.glob("src/core/*.cpp"), *ROOT.glob("src/core/*.hpp"),
            *ROOT.glob("cmake/*"), *ROOT.glob("resources/*"), *ROOT.glob("licenses/*"),
        }
        for path in inputs | {
            ROOT / f"scripts/{name}" for name in
            ("release.py", "bump_version.py", "package.py", "unpack.py", "sign_macos.sh")
        }:
            target = self.repo / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        (self.repo / ".gitignore").write_text("build/\n")
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("add", ".")
        self.git("commit", "-m", "Trusted fixture")
        self.git("init", "--bare", str(self.base / "remote.git"))
        self.git("remote", "add", "origin", str(self.base / "remote.git"))
        self.git("push", "origin", "HEAD:refs/heads/main")
        self.env = {
            **os.environ,
            "GITHUB_REPOSITORY": release.REPOSITORY,
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_SHA": self.git("rev-parse", "HEAD"),
            "GITHUB_RUN_ID": "42",
            "SOURCE_RUN_ID": "42",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_OUTPUT": str(self.base / "output"),
            "GITHUB_STEP_SUMMARY": str(self.base / "summary"),
        }
        self.version = release.read_version_sources()[0]
        self.env["VERSION"] = self.version
        self.run = {
            "id": 42, "run_attempt": 1,
            "repository": {"full_name": release.REPOSITORY},
            "head_repository": {"full_name": release.REPOSITORY},
            "path": release.WORKFLOW, "workflow_id": 7,
            "event": "workflow_dispatch", "head_branch": "main",
            "status": "in_progress", "conclusion": None,
            "head_sha": self.env["GITHUB_SHA"],
        }
        self.workflow = {"path": release.WORKFLOW, "id": 7}
        self.directory = self.repo / "build/release"
        self.directory.mkdir(parents=True)
        for name in release.SIGNED_FILES:
            (self.directory / name).write_bytes(name.encode())
        self.provenance = {
            "repository": release.REPOSITORY, "gitRevision": self.env["GITHUB_SHA"],
            "sourceRunId": 42, "sourceRunAttempt": 1,
            "sourceWorkflow": release.WORKFLOW, "sourceEvent": "workflow_dispatch",
            "signingRunId": "42", "signingRunAttempt": "1",
            "signed": True, "published": False, "dmgStapled": True, "zipStapled": False,
            "notarization": {"zip": {"status": "Accepted"}, "dmg": {"status": "Accepted"}},
            "finalArtifactsSha256": {
                name: release.sha(self.directory / name) for name in release.SIGNED_FILES
            },
        }
        self.write_provenance(self.provenance)
        self.manifest = {
            "repository": release.REPOSITORY, "gitRevision": self.env["GITHUB_SHA"],
            "version": self.version, "architectures": ["x86_64"], "configuration": "Release",
            "dirty": False, "signed": False, "published": False,
            "sourceSha256": {
                path.relative_to(ROOT).as_posix(): release.sha(self.repo / path.relative_to(ROOT))
                for path in inputs
            },
        }
        self.write_windows(self.manifest)

    def git(self, *args):
        return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()

    def write_provenance(self, value):
        (self.directory / "signing-provenance.json").write_text(json.dumps(value))

    def write_windows(self, manifest, corrupt=False):
        manifest = copy.deepcopy(manifest)
        binary = b"Unsigned Windows test fixture"
        filename = "Contents/Windows64/Splitter.4DX"
        manifest["filesSha256"] = {
            filename: hashlib.sha256(b"different" if corrupt else binary).hexdigest(),
        }
        archive = self.directory / "Splitter-windows-x64.zip"
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr(f"Splitter.bundle/{filename}", binary)
            package.writestr("Splitter.bundle/Contents/Resources/build-manifest.json",
                             json.dumps(manifest))
        incoming = self.repo / "build/release-windows"
        incoming.mkdir(exist_ok=True)
        shutil.copyfile(archive, incoming / archive.name)

    def test_only_canonical_main_manual_context_is_trusted(self):
        release.trusted_context(self.env)
        for key, value in (
            ("GITHUB_REPOSITORY", "fork/repo"), ("GITHUB_REF", "refs/heads/feature"),
            ("GITHUB_REF", "refs/tags/main"), ("GITHUB_EVENT_NAME", "pull_request"),
            ("GITHUB_EVENT_NAME", "push"), ("GITHUB_RUN_ID", "0"),
            ("GITHUB_RUN_ATTEMPT", "-1"), ("GITHUB_SHA", "not-a-sha"),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                release.trusted_context({**self.env, key: value})

    def test_signing_requires_current_active_build_identity(self):
        release.validate_run(self.run, self.workflow, self.env)
        for key, value in (
            ("id", 43), ("run_attempt", 2), ("repository", {"full_name": "fork/repo"}),
            ("head_repository", {"full_name": "fork/repo"}), ("workflow_id", 8),
            ("path", ".github/workflows/native.yml"), ("head_branch", "feature"),
            ("event", "push"), ("status", "completed"), ("conclusion", "failure"),
            ("head_sha", "0" * 40),
        ):
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                release.validate_run({**self.run, key: value}, self.workflow, self.env)
        with self.assertRaisesRegex(RuntimeError, "current Build"):
            release.validate_run(self.run, self.workflow, {**self.env, "SOURCE_RUN_ID": "43"})
        with self.assertRaisesRegex(RuntimeError, "workflow path"):
            release.validate_run(self.run, {**self.workflow, "path": "wrong"}, self.env)

    def test_signed_provenance_failures_block_publication(self):
        release.validate_signed(self.directory, self.env)
        for key, value in (
            ("repository", "fork/repo"), ("gitRevision", "0" * 40),
            ("sourceRunId", 43), ("sourceRunAttempt", 2),
            ("sourceWorkflow", ".github/workflows/native.yml"), ("sourceEvent", "push"),
            ("signingRunId", "43"), ("signingRunAttempt", "2"),
            ("signed", False), ("published", True), ("dmgStapled", False), ("zipStapled", True),
            ("notarization", {"zip": {"status": "Accepted"}}),
            ("notarization", {"zip": {"status": "Accepted"}, "dmg": {"status": "Invalid"}}),
            ("finalArtifactsSha256", {}),
        ):
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                self.write_provenance({**self.provenance, key: value})
                release.validate_signed(self.directory, self.env)

    def test_tampered_signed_artifact_is_rejected(self):
        (self.directory / "Splitter-macos-signed.zip").write_bytes(b"tampered")
        with self.assertRaisesRegex(RuntimeError, "hashes"):
            release.validate_signed(self.directory, self.env)

    def test_windows_provenance_failures_block_publication(self):
        release.validate_windows(self.manifest, self.version, self.env)
        for key, value in (
            ("repository", "fork/repo"), ("gitRevision", "0" * 40), ("version", "99.0.0"),
            ("architectures", ["arm64"]), ("configuration", "Debug"),
            ("dirty", True), ("signed", True), ("published", True), ("sourceSha256", {}),
        ):
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                release.validate_windows({**self.manifest, key: value}, self.version, self.env)

    def test_verifies_actual_windows_zip_and_generates_exact_release_assets(self):
        release.prepare_release(self.directory, self.version, self.env)
        expected = "".join(
            f"{release.sha(self.directory / name)}  {name}\n" for name in sorted(release.RELEASE_FILES)
        )
        self.assertEqual((self.directory / "SHA256SUMS").read_text(), expected)
        notes = (self.repo / "build/release-notes.md").read_text()
        self.assertIn(self.env["GITHUB_SHA"], notes)
        self.assertIn("The DMG is stapled; the ZIP is not.", notes)
        self.assertIn("Windows: native x64 package, unsigned.", notes)
        self.assertEqual({path.name for path in self.directory.iterdir()},
                         release.RELEASE_FILES | {"SHA256SUMS"})

    def test_corrupt_windows_zip_blocks_checksums_and_release_notes(self):
        self.write_windows(self.manifest, corrupt=True)
        with self.assertRaises(subprocess.CalledProcessError):
            release.prepare_release(self.directory, self.version, self.env)
        self.assertFalse((self.directory / "SHA256SUMS").exists())
        self.assertFalse((self.repo / "build/release-notes.md").exists())

    def test_extra_or_missing_release_files_are_rejected(self):
        (self.directory / "unexpected.txt").write_text("unexpected")
        with self.assertRaisesRegex(RuntimeError, "release files"):
            release.prepare_release(self.directory, self.version, self.env)
        (self.directory / "unexpected.txt").unlink()
        (self.directory / "Splitter-macos-signed.dmg").unlink()
        with self.assertRaisesRegex(RuntimeError, "release files"):
            release.prepare_release(self.directory, self.version, self.env)

    @unittest.skipIf(os.name == "nt", "Signing runs on macOS, with POSIX runner paths")
    def test_missing_signing_secrets_fail_instead_of_skipping_successfully(self):
        evidence = self.repo / "build/macos-signing/evidence"
        evidence.mkdir(parents=True)
        env = {**self.env, "GITHUB_ACTIONS": "true", "RUNNER_OS": "macOS"}
        names = ("APPLE_DEVELOPER_ID_CERTIFICATE", "APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD",
                 "KEYCHAIN_PASSWORD", "NOTARYTOOL_APPLE_ID", "NOTARYTOOL_PASSWORD",
                 "NOTARYTOOL_TEAM_ID")
        for name in names:
            env.pop(name, None)
        result = subprocess.run(["bash", "scripts/sign_macos.sh", "sign"],
                                env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Build cannot publish", (self.base / "summary").read_text())
        self.assertEqual((self.base / "output").read_text(), "signed=false\n")
        for name in names:
            self.assertIn(f"::error::Signing cannot proceed: missing {name}.", result.stdout)
        self.assertFalse((self.repo / "build/macos-signing/private").exists())

    @unittest.skipIf(os.name == "nt", "Release runs on Ubuntu; the gh shim uses a POSIX shebang")
    def test_actual_release_shell_creates_immutable_tag_at_dispatch_commit(self):
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(
            f"#!{sys.executable}\n"
            "import json, os, pathlib, sys\n"
            "pathlib.Path(os.environ['GH_LOG']).write_text(json.dumps(sys.argv[1:]))\n"
        )
        gh.chmod(0o755)
        env = {**self.env, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
               "GH_LOG": str(self.base / "gh-log")}
        workflow = (ROOT / ".github/workflows/build.yml").read_text()
        shell = textwrap.dedent(workflow.rsplit("        run: |\n", 1)[1])
        result = subprocess.run(["bash", "-eu", "-c", shell], env=env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("ls-remote", "origin", f"refs/tags/v{self.version}").split()[0],
                         self.env["GITHUB_SHA"])
        args = json.loads((self.base / "gh-log").read_text())
        self.assertEqual(args[:3], ["release", "create", f"v{self.version}"])
        self.assertIn("--verify-tag", args)
        self.assertEqual(args[args.index("--target") + 1], self.env["GITHUB_SHA"])
        self.assertEqual(set(args[-5:]),
                         {f"build/release/{name}" for name in release.RELEASE_FILES | {"SHA256SUMS"}})
        (self.base / "gh-log").unlink()
        result = subprocess.run(["bash", "-eu", "-c", shell], env=env,
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already tagged", result.stderr)
        self.assertFalse((self.base / "gh-log").exists())


if __name__ == "__main__":
    unittest.main()
