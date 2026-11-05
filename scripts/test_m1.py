#!/usr/bin/env python3
"""Exercise the packaged public API in real source and compiled 4D hosts."""

import argparse
import hashlib
import json
import pathlib
import platform
import shutil
import subprocess
import tempfile

from check_host import ROOT, payload, run_host
from binary import architecture


def verify(result, compiled):
    observed = payload(result, "SPLITTER_M1=")
    if observed["compiled"] is not compiled or observed["failures"]:
        raise RuntimeError(f"M1 host assertions failed: {observed}\n{result}")
    if observed["nativeCases"] != 1248 or observed["extendedCases"] != 46:
        raise RuntimeError(f"Incomplete host corpus: {observed}")
    if observed["passed"] != 1248 + observed["extendedCases"]:
        raise RuntimeError(f"Missing successful host assertions: {observed}")
    return observed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool4d", type=pathlib.Path, required=True)
    parser.add_argument("--plugin", type=pathlib.Path, required=True)
    parser.add_argument("--report", type=pathlib.Path, default=ROOT / "build/m1-host-report.json")
    parser.add_argument("--preemptive", action="store_true",
                        help="Also require eight verified preemptive processes (Process info, 4D 21+)")
    args = parser.parse_args()
    host = args.tool4d.resolve(strict=True)
    plugin = args.plugin.resolve(strict=True)
    manifest = json.loads((plugin / "Contents/Resources/manifest.json").read_text(encoding="utf-8"))
    thread_safe = manifest["commands"][0]["threadSafe"]
    version = subprocess.run([str(host), "--version"], check=True, capture_output=True, text=True).stdout.strip()
    host_architecture = architecture(host)
    target = "arm64_macOS_lib" if platform.system() == "Darwin" and host_architecture == "arm64" else "x86_64_generic"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="m1-", dir=args.report.parent) as temp:
        fixture = pathlib.Path(temp).resolve() / "host"
        shutil.copytree(
            ROOT / "tests/m1/Project", fixture / "Project",
            ignore=None if args.preemptive else shutil.ignore_patterns(
                "test_preemptive.4dm", "split_worker.4dm"),
        )
        installed = fixture / "Plugins" / plugin.name
        shutil.copytree(plugin, installed)
        compile_template = (ROOT / "tests/m1/probe_compile.4dm.in").read_text(encoding="utf-8")
        (fixture / "Project/Sources/Methods/probe_compile.4dm").write_text(
            compile_template.replace("@TARGET@", target), encoding="utf-8"
        )
        project = fixture / "Project/SplitterTests.4DProject"
        compilation = payload(run_host(host, project, "probe_compile"), "SPLITTER_COMPILE=")
        if compilation["success"] is not True:
            raise RuntimeError(f"M1 host compilation failed: {compilation}")
        source_result = run_host(host, project, "test_all")
        source = verify(source_result, False)
        compiled_result = run_host(host, project, "test_all", compiled=True)
        compiled = verify(compiled_result, True)
        preemptive_result = None
        preemptive = {"status": "not-run", "reason": "--preemptive was not requested"}
        if args.preemptive:
            preemptive_result = run_host(host, project, "test_preemptive", compiled=True)
            preemptive = payload(preemptive_result, "SPLITTER_PREEMPTIVE=")
            if preemptive != {
                "compiled": True, "ready": 8, "done": 8,
                "preemptive": 8, "passed": 9600, "failures": 0,
            }:
                raise RuntimeError(f"Compiled preemptive assertions failed: {preemptive_result}")
        # A fresh host process must not borrow data from the host or environment.
        (installed / "Contents/Resources/icudt79l.dat").unlink()
        missing_result = run_host(host, project, "test_missing_data")
        missing = payload(missing_result, "SPLITTER_MISSING=")
        if missing != {"nativeWorks": True, "regexIsNull": True, "graphemesIsNull": True}:
            raise RuntimeError(f"Missing-data isolation failed: {missing_result}")
        (installed / "Contents/Resources/icudt79l.dat").write_bytes(b"x")
        truncated_result = run_host(host, project, "test_missing_data")
        truncated = payload(truncated_result, "SPLITTER_MISSING=")
        if truncated != {"nativeWorks": True, "regexIsNull": True, "graphemesIsNull": True}:
            raise RuntimeError(f"Truncated-data isolation failed: {truncated_result}")
        report = {
            "status": "passed",
            "host": version,
            "hostBinarySha256": hashlib.sha256(host.read_bytes()).hexdigest(),
            "osVersion": platform.mac_ver()[0] if platform.system() == "Darwin" else platform.version(),
            "platform": platform.system() + "-" + platform.machine(),
            "hostArchitecture": host_architecture,
            "execution": "native" if host_architecture == platform.machine().lower().replace("amd64", "x86_64") else "translated",
            "source": source,
            "compiled": compiled,
            "compilation": compilation,
            "source_execution": source_result,
            "compiled_execution": compiled_result,
            "preemptive": preemptive,
            "preemptive_execution": preemptive_result,
            "missing_data": missing_result,
            "truncated_data": truncated_result,
            "package_sha256": {
                str(path.relative_to(plugin)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(plugin.rglob("*")) if path.is_file()
            },
            "source_sha256": {
                str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                for pattern in ("src/**/*.cpp", "src/**/*.hpp", "tests/m1/**/*", "resources/*")
                for path in sorted(ROOT.glob(pattern)) if path.is_file()
            },
            "threadSafe": thread_safe,
        }
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"M1 source and compiled host assertions passed: {source['passed']} per mode")
        print(f"Evidence: {args.report}")


if __name__ == "__main__":
    main()
