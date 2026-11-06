#!/usr/bin/env python3
"""Reproduce the Gate 0 contract evidence, including expected negative checks."""

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]


def run_host(host, project, method, compiled=False):
    command = [
        str(host),
        "--dataless",
        "--opening-mode=" + ("compiled" if compiled else "interpreted"),
        "--startup-method=" + method,
        "--project=" + str(project),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"{method}: exit {result.returncode}\n{result.stdout}\n{result.stderr}")
    return {"stdout": result.stdout, "stderr": result.stderr}


def payload(result, marker):
    text = result["stdout"]
    if text.count(marker) != 1:
        raise RuntimeError(f"Expected one {marker!r}, received {result}")
    return json.loads(text.split(marker, 1)[1])


def check_contract(result, compiled):
    report = payload(result, "SPLITTER_CONTRACT=")
    if report["compiled"] is not compiled or report["failed"] != 0 or report["passed"] != 1248:
        raise RuntimeError(f"Contract failed: {report}")
    if report["astralLength"] != 2 or report["combiningLength"] != 2:
        raise RuntimeError(f"Unexpected offset convention: {report}")
    # The SDK promotes its signed fType byte: Null (0xff) is observed as -1.
    if report["kindsStructured"] != [42, 38] or report["kindsNull"] != [-1, -1]:
        raise RuntimeError(f"Unexpected Variant kinds: {report}")
    if report["kindsLiteral"][0] != 33 or report["kindsLiteral"][1] not in (1, 9):
        raise RuntimeError(f"Unexpected literal kinds: {report}")
    if report["kindsInteger"] != [33, 9] or report["kindsReal"] != [33, 1]:
        raise RuntimeError(f"Unexpected numeric variable kinds: {report}")
    if report["empty"] != [] or report["whitespace"] != []:
        raise RuntimeError(f"Unexpected native empty/trim behavior: {report}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool4d", type=pathlib.Path, required=True)
    parser.add_argument("--plugin", type=pathlib.Path, required=True)
    parser.add_argument("--report", type=pathlib.Path, default=ROOT / "build/gate0-report.json")
    args = parser.parse_args()
    host = args.tool4d.resolve(strict=True)
    plugin = args.plugin.resolve(strict=True)
    version = subprocess.run([str(host), "--version"], check=True, capture_output=True, text=True).stdout.strip()
    if not version.startswith("20.7 "):
        raise RuntimeError(f"This contract check specifically requires 20.7, got {version!r}")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gate0-", dir=args.report.parent) as temp:
        fixture = pathlib.Path(temp) / "host"
        shutil.copytree(
            ROOT / "tests/host",
            fixture,
            ignore=shutil.ignore_patterns("Plugins", "Data", "Logs", "DerivedData", "userPreferences.*"),
        )
        shutil.copytree(plugin, fixture / "Plugins" / plugin.name)
        project = fixture / "Project/SplitterTests.4DProject"
        source_result = run_host(host, project, "probe_contract")
        source = check_contract(source_result, False)
        compile_result = run_host(host, project, "probe_compile")
        if payload(compile_result, "SPLITTER_COMPILE=")["success"] is not True:
            raise RuntimeError(f"Explicit-argument fixture did not compile: {compile_result}")
        compiled_result = run_host(host, project, "probe_contract", compiled=True)
        compiled = check_contract(compiled_result, True)
        error_result = run_host(host, project, "probe_error")
        if "SPLITTER_THROW status=33" not in error_result["stderr"]:
            raise RuntimeError(f"Unexpected throw availability; revisit error bridge: {error_result}")
        if "SPLITTER_ERROR=" in error_result["stdout"]:
            raise RuntimeError(f"Unexpected host error interception: {error_result}")
        shutil.copyfile(
            ROOT / "tests/negative/probe_omitted.4dm",
            fixture / "Project/Sources/Methods/probe_omitted.4dm",
        )
        omitted_result = run_host(host, project, "probe_omitted")
        if "SPLITTER_OMITTED_INTERPRETED_OK" not in omitted_result["stdout"]:
            raise RuntimeError(f"Interpreted omission failed: {omitted_result}")
        negative_result = run_host(host, project, "probe_compile")
        negative = payload(negative_result, "SPLITTER_COMPILE=")
        if negative["success"] is not False:
            raise RuntimeError(f"Omitted argument unexpectedly compiled: {negative}")
        errors = [item for item in negative["errors"] if item.get("isError")]
        if not any("Not enough parameters" in item["message"] for item in errors):
            raise RuntimeError(f"Compilation failed for an unrelated reason: {negative}")
        source_paths = [
            ROOT / "CMakeLists.txt",
            ROOT / "dependencies.lock.json",
            ROOT / "src/plugin/probe.cpp",
            ROOT / "tests/probes/manifest.json",
            ROOT / "scripts/check_host.py",
            ROOT / "cmake/Info.plist",
            *sorted((ROOT / "tests/host/Project").rglob("*.4dm")),
            ROOT / "tests/host/Project/SplitterTests.4DProject",
            ROOT / "tests/negative/probe_omitted.4dm",
        ]
        report = {
            "status": "historical-observations",
            "host": version,
            "host_binary_sha256": hashlib.sha256(host.read_bytes()).hexdigest(),
            "platform": "macos-arm64",
            "plugin_sha256": hashlib.sha256((plugin / "Contents/MacOS/Splitter").read_bytes()).hexdigest(),
            "source_sha256": {
                str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in source_paths
            },
            "source": source,
            "compiled": compiled,
            "source_execution": source_result,
            "compiled_execution": compiled_result,
            "compilation": compile_result,
            "omitted_interpreted": omitted_result,
            "omitted_compilation": negative,
            "throw_probe": error_result,
            "historical_findings": [
                "The historical Variant-third manifest rejects omission; the selected Longint/Object signature resolves this.",
                "Command 1805 (throw) is unavailable in 20.7; the user selected Null alone for production failures.",
            ],
        }
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Historical Gate 0 observations reproduced. Report: {args.report}")


if __name__ == "__main__":
    main()
