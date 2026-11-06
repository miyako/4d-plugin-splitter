import importlib.util
import os
import pathlib
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bump_version", ROOT / "scripts/bump_version.py")
BUMP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUMP)


class BumpVersionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = pathlib.Path(self.temp.name)
        self.remote = self.base / "remote.git"
        self.repo = self.base / "checkout"
        self.repo.mkdir()
        self.git("init", "--bare", str(self.remote))
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        for filename in {field[0] for field in BUMP.FIELDS} | {"scripts/bump_version.py"}:
            target = self.repo / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / filename, target)
        self.replace_versions("1.2.3")
        self.commit("Initial fixture")
        self.git("remote", "add", "origin", str(self.remote))
        self.git("push", "origin", "HEAD:refs/heads/main")
        self.initial = self.git("rev-parse", "HEAD")
        self.output = self.base / "output"
        self.env = {
            **os.environ,
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_OUTPUT": str(self.output),
        }

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, message):
        self.git("add", ".")
        self.git("commit", "-m", message)

    def replace_versions(self, version):
        for filename, pattern in BUMP.FIELDS:
            path = self.repo / filename
            content = path.read_text(encoding="utf-8")
            match = re.search(pattern, content)
            path.write_text(content[:match.start(1)] + version + content[match.end(1):],
                            encoding="utf-8")

    def run_bump(self, mode="patch"):
        return subprocess.run(
            [sys.executable, "scripts/bump_version.py", mode], cwd=self.repo,
            env=self.env, capture_output=True, text=True,
        )

    def assert_rejected(self, result, message):
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(message, result.stderr)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(self.git("ls-remote", "origin", "refs/heads/main").split()[0],
                         self.git("rev-parse", "HEAD"))

    def test_increments_commit_push_all_fields_without_tags(self):
        for mode, expected in (("patch", "1.2.4"), ("minor", "1.3.0"), ("major", "2.0.0")):
            with self.subTest(mode=mode):
                result = self.run_bump(mode)
                self.assertEqual(result.returncode, 0, result.stderr)
                for filename, pattern in BUMP.FIELDS:
                    content = (self.repo / filename).read_text(encoding="utf-8")
                    self.assertEqual(re.search(pattern, content)[1], expected)
                with (self.repo / "cmake/Info.plist").open("rb") as source:
                    self.assertEqual(plistlib.load(source)["CFBundleVersion"], expected)
                self.assertEqual(self.output.read_text(), f"version={expected}\n")
                self.assertEqual(self.git("status", "--porcelain"), "")
                self.assertEqual(self.git("ls-remote", "origin", "refs/heads/main").split()[0],
                                 self.git("rev-parse", "HEAD"))
                self.assertEqual(self.git("ls-remote", "--tags", "origin"), "")
                self.assertEqual(self.git("tag"), "")
                self.assertIn("Co-authored-by: Copilot App", self.git("log", "-1", "--format=%B"))
                self.assertEqual(set(self.git("diff-tree", "--no-commit-id", "--name-only",
                                              "-r", "HEAD").splitlines()),
                                 {field[0] for field in BUMP.FIELDS})
                self.replace_versions("1.2.3")
                self.commit("Restore fixture version")
                self.git("push", "origin", "HEAD:refs/heads/main")
                self.output.unlink()

    def test_invalid_versions_are_rejected_without_edits(self):
        for version in ("01.2.3", "1.02.3", "1.2.03", "1.2", "v1.2.3",
                        "1.2.3-rc.1", "1.2.3+build", "-1.2.3", "1.2.3\n"):
            with self.subTest(version=version):
                self.replace_versions(version)
                self.commit("Invalid version")
                self.git("push", "origin", "HEAD:refs/heads/main")
                self.assert_rejected(self.run_bump(), "strict X.Y.Z")

    def test_invalid_mode_is_rejected(self):
        self.assert_rejected(self.run_bump("bogus"), "invalid choice")

    def test_existing_remote_tag_is_rejected_even_without_local_tag(self):
        self.git("tag", "-a", "v1.2.4", "-m", "Published version")
        self.git("push", "origin", "refs/tags/v1.2.4")
        self.git("tag", "-d", "v1.2.4")
        self.assert_rejected(self.run_bump(), "already tagged")

    def test_drift_missing_and_duplicate_fields_are_rejected(self):
        path = self.repo / "cmake/Info.plist"
        original = path.read_text()
        for content, message in (
            (original.replace("<string>1.2.3</string>", "<string>9.0.0</string>", 1), "differs"),
            (original.replace("CFBundleVersion", "RemovedVersion"), "exactly one"),
            (original + "\n<key>CFBundleVersion</key><string>1.2.3</string>", "exactly one"),
        ):
            with self.subTest(message=message):
                path.write_text(content)
                self.commit("Change version field")
                self.git("push", "origin", "HEAD:refs/heads/main")
                self.assert_rejected(self.run_bump(), message)

    def test_remote_inspection_failure_is_not_treated_as_missing_tag(self):
        self.git("remote", "set-url", "origin", str(self.base / "missing.git"))
        result = self.run_bump()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Could not inspect remote version tags", result.stderr)
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertFalse(self.output.exists())

    def test_stale_dispatch_cannot_overwrite_main(self):
        (self.repo / "concurrent.txt").write_text("Concurrent main change\n")
        self.commit("Concurrent change")
        latest = self.git("rev-parse", "HEAD")
        self.git("push", "origin", "HEAD:refs/heads/main")
        self.git("checkout", "--detach", self.initial)
        result = self.run_bump()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("rejected", result.stderr)
        self.assertEqual(self.git("ls-remote", "origin", "refs/heads/main").split()[0], latest)
        self.assertFalse(self.output.exists())

    def test_main_only_dispatch_guards(self):
        workflow = (ROOT / ".github/workflows/bump-version.yml").read_text()
        guard = textwrap.dedent(workflow.split("        run: |\n", 1)[1]
                                .split("      - uses:", 1)[0])
        for event, ref, allowed in (
            ("workflow_dispatch", "refs/heads/main", True),
            ("workflow_dispatch", "refs/heads/feature", False),
            ("workflow_dispatch", "refs/tags/main", False),
            ("push", "refs/heads/main", False),
        ):
            with self.subTest(event=event, ref=ref):
                self.env.update(GITHUB_EVENT_NAME=event, GITHUB_REF=ref)
                result = subprocess.run(["bash", "-eu", "-c", guard], env=self.env,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, allowed, result.stderr)
                if not allowed:
                    self.assert_rejected(self.run_bump(), "dispatched from main")

    def test_dirty_checkout_is_rejected(self):
        (self.repo / "unrelated.txt").write_text("Do not commit this\n")
        result = self.run_bump()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("clean checkout", result.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.initial)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
