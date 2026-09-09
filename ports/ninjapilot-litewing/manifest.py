#!/usr/bin/env python3
"""Validate and inspect the pinned NinjaPilot LiteWing source manifest."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable


COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def load_manifest(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    validate_manifest(value)
    return value


def validate_manifest(value: Dict[str, Any]) -> None:
    if not isinstance(value, dict):
        raise ValueError("manifest must be an object")
    if value.get("schema_version") != 1:
        raise ValueError("unsupported schema_version")

    target = value.get("target")
    if not isinstance(target, dict):
        raise ValueError("target must be an object")
    required_target = ("name", "status", "board", "board_type", "board_rev")
    for field in required_target:
        if not isinstance(target.get(field), str) or not target[field]:
            raise ValueError("target.%s must be a non-empty string" % field)
    if target.get("hardware_validated") is not False:
        raise ValueError("target.hardware_validated must remain false")
    if target.get("flash_allowed_by_this_manifest") is not False:
        raise ValueError("manifest must not authorize flashing")

    sources = value.get("sources")
    if not isinstance(sources, dict):
        raise ValueError("sources must be an object")
    flight = sources.get("flight_tree")
    reference = sources.get("esp32_reference")
    if not isinstance(flight, dict) or not isinstance(reference, dict):
        raise ValueError("flight_tree and esp32_reference are required")
    for source_name, source in (("flight_tree", flight), ("esp32_reference", reference)):
        if not isinstance(source.get("repository"), str) or not source["repository"].startswith("https://"):
            raise ValueError("%s.repository must be an HTTPS URL" % source_name)
        if not COMMIT_RE.fullmatch(source.get("commit", "")):
            raise ValueError("%s.commit must be a 40-character lowercase SHA" % source_name)
    if not isinstance(flight.get("branch"), str) or not flight["branch"]:
        raise ValueError("flight_tree.branch is required")
    paths = flight.get("required_paths")
    if not isinstance(paths, list) or not paths or not all(isinstance(item, str) and item for item in paths):
        raise ValueError("flight_tree.required_paths must be a non-empty string list")

    toolchain = value.get("toolchain")
    if not isinstance(toolchain, dict):
        raise ValueError("toolchain is required")
    if toolchain.get("target") != "esp32s3":
        raise ValueError("toolchain.target must be esp32s3")
    if toolchain.get("esp_idf") != "5.3.2":
        raise ValueError("toolchain.esp_idf must be 5.3.2")
    if toolchain.get("generated_uavobjects") != "make uavobjects_flight":
        raise ValueError("toolchain.generated_uavobjects must record the generator command")

    patches = value.get("patches")
    if not isinstance(patches, list) or not patches:
        raise ValueError("patches must be a non-empty list")
    seen = set()
    for patch in patches:
        if not isinstance(patch, dict):
            raise ValueError("each patch must be an object")
        name = patch.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", name):
            raise ValueError("patch names must be simple filenames")
        if name in seen:
            raise ValueError("duplicate patch name: %s" % name)
        seen.add(name)
        if patch.get("source") not in ("reference", "repository"):
            raise ValueError("patch source must be reference or repository")
        if not isinstance(patch.get("apply"), bool):
            raise ValueError("patch %s must declare apply true or false" % name)
        if not isinstance(patch.get("role"), str) or not patch["role"]:
            raise ValueError("patch %s must declare a role" % name)
        if not SHA256_RE.fullmatch(patch.get("sha256", "")):
            raise ValueError("patch %s has an invalid sha256" % name)
        if patch["source"] == "reference":
            if not isinstance(patch.get("url"), str) or not patch["url"].startswith("https://"):
                raise ValueError("reference patch %s must have an HTTPS URL" % name)
        elif not isinstance(patch.get("path"), str) or not patch["path"]:
            raise ValueError("repository patch %s must have a path" % name)

    contract = value.get("hardware_contract")
    if not isinstance(contract, dict):
        raise ValueError("hardware_contract is required")
    imu = contract.get("imu")
    motors = contract.get("motors")
    if not isinstance(imu, dict) or not isinstance(motors, dict):
        raise ValueError("hardware_contract.imu and motors are required")
    if imu.get("bus") != "I2C0" or imu.get("sda_gpio") != 11 or imu.get("scl_gpio") != 10:
        raise ValueError("MPU6050 I2C0 pin contract is inconsistent")
    if motors.get("gpio") != [5, 6, 3, 4] or motors.get("pwm_hz") != 20000:
        raise ValueError("brushed motor pin or PWM contract is inconsistent")
    if motors.get("actuator_min") != 0 or motors.get("actuator_max") != 1000:
        raise ValueError("actuator range must be 0..1000")
    if motors.get("corner_order_verified") is not False:
        raise ValueError("motor corner order must remain unverified")


def patch_records(value: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    return value["patches"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--patches", action="store_true")
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    if args.patches:
        for patch in patch_records(manifest):
            print("\t".join(
                (
                    patch["name"],
                    patch["source"],
                    "true" if patch["apply"] else "false",
                    patch.get("url", "-"),
                    patch.get("path", "-"),
                    patch["sha256"],
                )
            ))
    else:
        print("manifest valid: %s" % args.manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
