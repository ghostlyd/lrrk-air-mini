#!/usr/bin/env python3
"""Verify the immutable external source inputs used by the ESP-IDF wrapper."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def git_head(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise ValueError(f"not a usable Git checkout: {path}")
    return result.stdout.strip()


def require_paths(root: Path, paths: list[str], label: str) -> None:
    missing = [path for path in paths if not (root / path).is_file()]
    if missing:
        raise ValueError(f"{label} missing required paths: {', '.join(missing)}")


def verify(manifest_path: Path, flight_root: Path, reference_root: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    flight = manifest["sources"]["flight_tree"]
    reference = manifest["sources"]["esp32_reference"]
    adapter = manifest["target_adapter"]

    actual_flight = git_head(flight_root)
    if actual_flight != flight["commit"]:
        raise ValueError(
            f"NinjaPilot source commit mismatch: expected {flight['commit']}, got {actual_flight}"
        )

    actual_reference = git_head(reference_root)
    if actual_reference != reference["commit"]:
        raise ValueError(
            "OpenPilotESP32 reference commit mismatch: "
            f"expected {reference['commit']}, got {actual_reference}"
        )

    require_paths(flight_root, flight["required_paths"], "NinjaPilot")
    require_paths(reference_root, adapter["reference_backend_files"], "ESP32 reference")

    for path in adapter["excluded_reference_files"]:
        if path not in adapter["reference_backend_files"] and not (reference_root / path).is_file():
            raise ValueError(f"reference exclusion path is missing from pinned source: {path}")

    print("external source inputs valid")
    print(f"ninjapilot: {actual_flight}")
    print(f"esp32-reference: {actual_reference}")
    print("no firmware was flashed")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--flight", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        verify(args.manifest.resolve(), args.flight.resolve(), args.reference.resolve())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"external source verification failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
