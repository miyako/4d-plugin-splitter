#!/usr/bin/env python3
"""Probe optional fourth Variant, Object and Collection parameters on 20.7."""

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
    parser.add_argument("--report", type=pathlib.Path, default=ROOT / "build/fourth-report.json")
    args = parser.parse_args()
    host = args.tool4d.resolve(strict=True)
    plugin = args.plugin.resolve(strict=True)
    version = subprocess.run([str(host), "--version"], check=True, capture_output=True, text=True).stdout.strip()
    if not version.startswith("20.7 "):
        raise RuntimeError(f"This probe requires 20.7, got {version!r}")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    template = (ROOT / "tests/fourth/probe_matrix.4dm.in").read_text(encoding="utf-8")
    arguments = {
        "two": '" a ,b,"; ","',
        "three": '" a ,b,"; ","; 0',
        "object": '" a ,b,"; ","; 0; New object:C1471("mode"; "literal")',
        "collection": '" a ,b,"; ","; 0; New collection:C1472(","; ";")',
        "null": '" a ,b,"; ","; 0; Null',
    }
    report = {"host": version, "platform": "macos-arm64", "cases": {}}
    for kind in ("v", "j", "c"):
        command = f"Splitter_fourth_{kind}"
        syntax = f"{command}(&T;&T;&L;&{kind.upper()}):C"
        for form, call_arguments in arguments.items():
            case = f"{kind}_{form}"
            with tempfile.TemporaryDirectory(prefix=f"fourth-{case}-", dir=args.report.parent) as temp:
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
                call = f"{command}({call_arguments})"
                (methods / "probe_fourth.4dm").write_text(
                    template.replace("@CALL@", call), encoding="utf-8"
                )
                shutil.copytree(plugin, fixture / "Plugins" / plugin.name)
                project = fixture / "Project/SplitterTests.4DProject"
                source_result = run_host(host, project, "probe_fourth")
                if kind == "v":
                    expected_value = {"two": 5, "three": 5, "object": 38, "collection": 42, "null": -1}[form]
                    expected_marker = f"SPLITTER_FOURTH_KIND={expected_value}\n"
                elif kind == "j":
                    expected_marker = f"SPLITTER_FOURTH_OBJECT_NULL={int(form != 'object')}\n"
                else:
                    expected_marker = f"SPLITTER_FOURTH_COLLECTION_NULL={int(form != 'collection')}\n"
                if source_result["stderr"].count(expected_marker) != 1:
                    raise RuntimeError(f"Unexpected fourth-argument default/type for {case}: {source_result}")
                source = None
                if "SPLITTER_FOURTH=" in source_result["stdout"]:
                    source = payload(source_result, "SPLITTER_FOURTH=")
                    if source != {"compiled": False, "equal": 1}:
                        raise RuntimeError(f"Unexpected source output for {case}: {source}")
                compile_result = run_host(host, project, "probe_compile")
                compilation = payload(compile_result, "SPLITTER_COMPILE=")
                expected_success = (
                    (kind == "v" and form in ("object", "collection", "null"))
                    or (kind == "j" and form != "collection")
                    or (kind == "c" and form != "object")
                )
                if compilation["success"] is not expected_success:
                    raise RuntimeError(f"Fourth-argument compilation behavior changed for {case}: {compilation}")
                compiled = None
                compiled_result = None
                if compilation["success"]:
                    compiled_result = run_host(host, project, "probe_fourth", compiled=True)
                    compiled = payload(compiled_result, "SPLITTER_FOURTH=")
                    if compiled != {"compiled": True, "equal": 1}:
                        raise RuntimeError(f"Unexpected compiled output for {case}: {compiled}")
                    if compiled_result["stderr"].count(expected_marker) != 1:
                        raise RuntimeError(f"Unexpected compiled fourth argument for {case}: {compiled_result}")
                else:
                    errors = [item for item in compilation["errors"] if item.get("isError")]
                    if not errors or any(
                        item["code"]["methodName"] != "probe_fourth" for item in errors
                    ):
                        raise RuntimeError(f"Unrelated compilation failure: {compilation}")
                report["cases"][case] = {
                    "syntax": syntax,
                    "call": call,
                    "source": source,
                    "source_execution": source_result,
                    "source_execution_status": "executed" if source is not None else "rejected",
                    "source_argument_preserved": not (
                        (kind == "j" and form == "collection")
                        or (kind == "c" and form == "object")
                    ),
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
                print(case, "source", report["cases"][case]["source_execution_status"],
                      "compile", compilation["success"], flush=True)
    inputs = [
        ROOT / "src/plugin/probe.cpp",
        ROOT / "tests/probes/manifest.json",
        ROOT / "scripts/check_fourth.py",
        ROOT / "scripts/check_host.py",
        ROOT / "tests/fourth/probe_matrix.4dm.in",
    ]
    report["source_sha256"] = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in inputs
    }
    report["plugin_sha256"] = hashlib.sha256(
        (plugin / "Contents/MacOS/Splitter").read_bytes()
    ).hexdigest()
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Evidence: {args.report}")


if __name__ == "__main__":
    main()
