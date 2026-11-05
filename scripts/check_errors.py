#!/usr/bin/env python3
"""Compare supported 20.7 assertions via SDK/direct calls and null results."""

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import tempfile

from check_host import ROOT, payload, run_host


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool4d", type=pathlib.Path, required=True)
    parser.add_argument("--plugin", type=pathlib.Path, required=True)
    parser.add_argument("--report", type=pathlib.Path, default=ROOT / "build/errors-report.json")
    args = parser.parse_args()
    host = args.tool4d.resolve(strict=True)
    plugin = args.plugin.resolve(strict=True)
    version = subprocess.run([str(host), "--version"], check=True, capture_output=True, text=True).stdout.strip()
    if not version.startswith("20.7 "):
        raise RuntimeError(f"This probe requires 20.7, got {version!r}")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    report = {"host": version, "platform": "macos-arm64"}
    with tempfile.TemporaryDirectory(prefix="errors-", dir=args.report.parent) as temp:
        fixture = pathlib.Path(temp).resolve() / "host"
        methods = fixture / "Project/Sources/Methods"
        methods.mkdir(parents=True)
        shutil.copyfile(
            ROOT / "tests/host/Project/SplitterTests.4DProject",
            fixture / "Project/SplitterTests.4DProject",
        )
        for method in ("probe_compile", "probe_error_handler"):
            shutil.copyfile(
                ROOT / f"tests/host/Project/Sources/Methods/{method}.4dm",
                methods / f"{method}.4dm",
            )
        shutil.copyfile(ROOT / "tests/errors/probe_errors.4dm", methods / "probe_errors.4dm")
        shutil.copytree(plugin, fixture / "Plugins" / plugin.name)
        project = fixture / "Project/SplitterTests.4DProject"
        report["source"] = run_host(host, project, "probe_errors")
        report["compilation"] = payload(run_host(host, project, "probe_compile"), "SPLITTER_COMPILE=")
        if report["compilation"]["success"] is not True:
            raise RuntimeError(f"Error-probe fixture did not compile: {report['compilation']}")
        report["compiled"] = run_host(host, project, "probe_errors", compiled=True)
        for mode, compiled in (("source", False), ("compiled", True)):
            observation = payload(report[mode], "SPLITTER_NULL=")
            if observation != {"compiled": compiled, "resultIsNull": True}:
                raise RuntimeError(f"Unexpected null-result semantics: {observation}")
            output = report[mode]["stdout"]
            if output.count("SPLITTER_ERROR=") != 1:
                raise RuntimeError(f"Unexpected error-handler invocation count: {report[mode]}")
            if not (
                output.index("SPLITTER_ASSERT_NATIVE_DONE")
                < output.index("SPLITTER_ERROR=")
                < output.index("SPLITTER_ASSERT_DIRECT_DONE")
            ):
                raise RuntimeError(f"Unexpected error-handler order: {report[mode]}")
            errors_text = output.split("SPLITTER_ERROR=", 1)[1].split(
                "SPLITTER_ASSERT_DIRECT_DONE", 1
            )[0]
            errors = json.loads(errors_text)
            if len(errors) != 1 or errors[0]["errCode"] != -10518:
                raise RuntimeError(f"Unexpected direct assertion error: {errors}")
            if errors[0]["message"] != "Assert failed: Splitter direct assertion":
                raise RuntimeError(f"Handler caught the wrong assertion: {errors}")
            if "SPLITTER_ASSERT status=-10518\n" not in report[mode]["stderr"]:
                raise RuntimeError(f"Native assertion did not report its SDK error: {report[mode]}")
        report["observations"] = {
            "sdk_assert_invokes_host_handler": False,
            "direct_assert_invokes_host_handler": True,
            "null_collection_result_is_actual_null": True,
        }
    inputs = [
        ROOT / "src/plugin/probe.cpp",
        ROOT / "tests/probes/manifest.json",
        ROOT / "scripts/check_errors.py",
        ROOT / "scripts/check_host.py",
        ROOT / "tests/errors/probe_errors.4dm",
    ]
    report["source_sha256"] = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in inputs
    }
    report["plugin_sha256"] = hashlib.sha256(
        (plugin / "Contents/MacOS/Splitter").read_bytes()
    ).hexdigest()
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({mode: report[mode] for mode in ("source", "compiled")}, indent=2))
    print(f"Evidence: {args.report}")


if __name__ == "__main__":
    main()
