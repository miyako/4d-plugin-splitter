#!/usr/bin/env python3
"""Compare omitted Longint/Variant options in isolated 4D 20.7 projects."""

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import tempfile

from check_host import ROOT, payload, run_host


def verify_execution(result, compiled):
    observed = payload(result, "SPLITTER_MATRIX=")
    if observed != {"compiled": compiled, "explicitEqual": 1, "omittedEqual": 1}:
        raise RuntimeError(f"Unexpected execution result: {observed}")
    return observed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool4d", type=pathlib.Path, required=True)
    parser.add_argument("--plugin", type=pathlib.Path, required=True)
    parser.add_argument("--report", type=pathlib.Path, default=ROOT / "build/omission-report.json")
    args = parser.parse_args()
    host = args.tool4d.resolve(strict=True)
    plugin = args.plugin.resolve(strict=True)
    version = subprocess.run([str(host), "--version"], check=True, capture_output=True, text=True).stdout.strip()
    if not version.startswith("20.7 "):
        raise RuntimeError(f"This probe requires 20.7, got {version!r}")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    report = {"host": version, "platform": "macos-arm64", "cases": {}}
    syntaxes = {
        "vv": "Splitter_probe(&T;&V;&V):C",
        "vl": "Splitter_probe_vl(&T;&V;&L):C",
        "tl": "Splitter_probe_tl(&T;&T;&L):C",
        "tv": "Splitter_probe_tv(&T;&T;&V):C",
    }
    for case, syntax in syntaxes.items():
        with tempfile.TemporaryDirectory(prefix=f"omission-{case}-", dir=args.report.parent) as temp:
            fixture = pathlib.Path(temp).resolve() / "host"
            methods = fixture / "Project/Sources/Methods"
            methods.mkdir(parents=True)
            shutil.copyfile(
                ROOT / "tests/host/Project/SplitterTests.4DProject",
                fixture / "Project/SplitterTests.4DProject",
            )
            shutil.copyfile(
                ROOT / "tests/host/Project/Sources/Methods/probe_compile.4dm",
                methods / "probe_compile.4dm",
            )
            shutil.copyfile(ROOT / f"tests/matrix/{case}.4dm", methods / "probe_matrix.4dm")
            shutil.copytree(plugin, fixture / "Plugins" / plugin.name)
            project = fixture / "Project/SplitterTests.4DProject"
            source_result = run_host(host, project, "probe_matrix")
            source = verify_execution(source_result, False)
            compile_result = run_host(host, project, "probe_compile")
            compilation = payload(compile_result, "SPLITTER_COMPILE=")
            if compilation["success"] is not (case in ("vl", "tl")):
                raise RuntimeError(f"Omission behavior changed for {syntax}: {compilation}")
            if case in ("vl", "tl"):
                if source_result["stderr"].count("SPLITTER_LONG_OPTIONS=0\n") != 2:
                    raise RuntimeError(f"Unexpected Longint default: {source_result}")
            compiled = None
            compiled_result = None
            if compilation["success"]:
                compiled_result = run_host(host, project, "probe_matrix", compiled=True)
                compiled = verify_execution(compiled_result, True)
                if compiled_result["stderr"].count("SPLITTER_LONG_OPTIONS=0\n") != 2:
                    raise RuntimeError(f"Unexpected compiled Longint default: {compiled_result}")
            else:
                errors = [item for item in compilation["errors"] if item.get("isError")]
                if not errors or any(
                    item["code"]["methodName"] != "probe_matrix" for item in errors
                ):
                    raise RuntimeError(f"Unrelated compilation failure: {compilation}")
            report["cases"][case] = {
                "syntax": syntax,
                "source": source,
                "source_execution": source_result,
                "compilation": compilation,
                "compiled": compiled,
                "compiled_execution": compiled_result,
                "compiled_execution_status": "passed" if compiled is not None else "not_run",
                "compiled_libraries": sorted(
                    str(path.relative_to(fixture))
                    for path in fixture.rglob("*")
                    if path.is_file() and path.suffix.lower() in (".dylib", ".dll", ".4dindy", ".4dc")
                ),
            }
    inputs = [
        ROOT / "src/plugin/probe.cpp",
        ROOT / "tests/probes/manifest.json",
        ROOT / "scripts/check_omission.py",
        ROOT / "scripts/check_host.py",
        *sorted((ROOT / "tests/matrix").glob("*.4dm")),
    ]
    report["source_sha256"] = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in inputs
    }
    report["plugin_sha256"] = hashlib.sha256(
        (plugin / "Contents/MacOS/Splitter").read_bytes()
    ).hexdigest()
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for case, result in report["cases"].items():
        print(case, result["syntax"], "compile", result["compilation"]["success"],
              "compiled_execution", result["compiled_execution_status"])
    print(f"Evidence: {args.report}")


if __name__ == "__main__":
    main()
