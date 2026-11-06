#!/usr/bin/env python3
"""Validate, bump and push coordinated Splitter version fields; never tag or release."""

import argparse
import os
import pathlib
import re
import subprocess


VERSION = r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
FIELDS = (
    ("CMakeLists.txt", r"project\(Splitter VERSION ([^\s]+) LANGUAGES CXX\)"),
    ("cmake/Info.plist", r"<key>CFBundleVersion</key>\s*<string>([^<]*)</string>"),
    ("cmake/Info.plist", r"<key>CFBundleShortVersionString</key>\s*<string>([^<]*)</string>"),
    ("scripts/package.py", r'"version": "([^"]*)"'),
)


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def read_version_sources():
    sources = {}
    current = None
    for filename, pattern in FIELDS:
        path = pathlib.Path(filename)
        if path not in sources:
            sources[path] = path.read_text(encoding="utf-8")
        matches = list(re.finditer(pattern, sources[path]))
        if len(matches) != 1 or not re.fullmatch(VERSION, matches[0][1]):
            raise RuntimeError(f"{filename}: expected exactly one strict X.Y.Z version for {pattern}")
        value = matches[0][1]
        if current is None:
            current = value
        elif value != current:
            raise RuntimeError(f"{filename}: version {value} differs from CMake version {current}")
    return current, sources


def require_unused_tag(version):
    tag = subprocess.run(["git", "ls-remote", "--exit-code", "origin", f"refs/tags/v{version}"],
                         capture_output=True, text=True)
    if tag.returncode == 0:
        raise RuntimeError(f"Version v{version} is already tagged; refusing to reuse it.")
    if tag.returncode != 2:
        raise RuntimeError(f"Could not inspect remote version tags: {tag.stderr.strip()}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("patch", "minor", "major"))
    args = parser.parse_args()
    if (os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or os.environ.get("GITHUB_REF") != "refs/heads/main"):
        raise RuntimeError("Version bumps must be dispatched from main.")
    if git("status", "--porcelain"):
        raise RuntimeError("Version bumps require a clean checkout.")

    current, sources = read_version_sources()
    major, minor, patch = map(int, current.split("."))
    if args.mode == "major":
        major, minor, patch = major + 1, 0, 0
    elif args.mode == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    new = f"{major}.{minor}.{patch}"
    require_unused_tag(new)

    for filename, pattern in FIELDS:
        path = pathlib.Path(filename)
        sources[path] = re.sub(pattern, lambda match: (
            match[0][:match.start(1) - match.start()] + new
            + match[0][match.end(1) - match.start():]
        ), sources[path])
    for path, content in sources.items():
        path.write_text(content, encoding="utf-8")
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "github-actions[bot]@users.noreply.github.com")
    git("add", "--", *map(str, sources))
    git("commit", "-m", f"chore: bump version to {new}",
        "-m", "Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>")
    # A stale dispatch or a concurrent main update must fail, never overwrite main.
    subprocess.run(["git", "push", "origin", "HEAD:refs/heads/main"], check=True)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"version={new}\n")
    print(f"Bumped {current} -> {new}; no tag or release created.")


if __name__ == "__main__":
    main()
