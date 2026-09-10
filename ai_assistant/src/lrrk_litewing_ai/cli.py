"""Dry-run CLI for normalized LiteWing telemetry."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Iterable, Optional, Sequence

from .adapters import (
    AdapterError,
    JsonlTelemetryAdapter,
    UAVTalkAdapter,
    UAVTalkCaptureAdapter,
)
from .agent import create_assistant
from .audit import AuditLog
from .tools import AssistantRuntime, run_preflight_tool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline-first LiteWing telemetry assistant")
    parser.add_argument("--input", type=Path, help="JSONL or saved UAVTalk telemetry input")
    parser.add_argument(
        "--input-format",
        choices=("jsonl", "uavtalk", "uavtalk-live"),
        default="jsonl",
    )
    parser.add_argument("--captured-at", help="timezone-aware capture time, required for UAVTalk replay")
    parser.add_argument("--device", help="live /dev/cu.* serial device")
    parser.add_argument("--usb-location", help="exact live USB topology location")
    parser.add_argument("--private-capture", type=Path, help="new mode-0600 live capture path")
    parser.add_argument("--duration", type=float, help="live collection duration in seconds (0.1..5.0)")
    parser.add_argument("--audit-log", type=Path, help="append-only JSONL audit destination")
    parser.add_argument("--session", default="cli-session", help="operator session identifier")
    parser.add_argument("--prompt", help="optional offline prompt or live-agent prompt")
    parser.add_argument("--live-agent", action="store_true", help="explicitly enable the optional OpenAI provider")
    parser.add_argument("--json", action="store_true", dest="json_output", help="emit machine-readable reports")
    return parser


def _print_report(report: dict, json_output: bool) -> None:
    if json_output:
        print(json.dumps(report, sort_keys=True))
        return
    print("preflight: %s" % report.get("overall", "UNKNOWN"))
    for finding in report.get("findings", []):
        print("- %s: %s (%s)" % (finding["finding_id"], finding["status"], finding["evidence"]))


def _live_prompt(agent: object, prompt: str) -> str:
    async def run() -> str:
        from agents import Runner
        result = await Runner.run(agent, prompt)
        return str(getattr(result, "final_output", result))

    return asyncio.run(run())


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = AssistantRuntime(operator_session=args.session)
    audit = AuditLog(args.audit_log, args.session) if args.audit_log else None
    try:
        live_values = (args.device, args.usb_location, args.private_capture, args.duration)
        if args.input_format == "uavtalk-live":
            if args.input is not None or args.captured_at:
                raise AdapterError("--input and --captured-at do not apply to live UAVTalk")
            missing = [
                flag for flag, value in (
                    ("--device", args.device),
                    ("--usb-location", args.usb_location),
                    ("--private-capture", args.private_capture),
                ) if value is None
            ]
            if missing:
                raise AdapterError("live UAVTalk requires %s" % ", ".join(missing))
            adapter = UAVTalkAdapter(
                device=args.device,
                location=args.usb_location,
                capture_path=args.private_capture,
                duration_s=2.0 if args.duration is None else args.duration,
            )
        elif args.input_format == "uavtalk":
            if args.input is None:
                raise AdapterError("--input is required for UAVTalk replay")
            if any(value is not None for value in live_values):
                raise AdapterError("live transport flags apply only to --input-format uavtalk-live")
            if not args.captured_at:
                raise AdapterError("--captured-at is required for UAVTalk replay")
            try:
                captured_at = datetime.fromisoformat(args.captured_at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise AdapterError("invalid --captured-at timestamp") from exc
            adapter = UAVTalkCaptureAdapter(args.input, captured_at)
        else:
            if args.input is None:
                raise AdapterError("--input is required for JSONL replay")
            if any(value is not None for value in live_values):
                raise AdapterError("live transport flags apply only to --input-format uavtalk-live")
            if args.captured_at:
                raise AdapterError("--captured-at applies only to UAVTalk replay")
            adapter = JsonlTelemetryAdapter(args.input)
        snapshots = list(adapter.snapshots())
    except (AdapterError, OSError) as exc:
        print("telemetry input blocked: %s" % exc, file=sys.stderr)
        return 2
    if not snapshots:
        print("telemetry input blocked: no snapshots", file=sys.stderr)
        return 2

    for snapshot in snapshots:
        runtime.ingest(snapshot)
        if audit:
            audit.append("snapshot_received", {"snapshot": snapshot.to_dict(), "snapshot_hash": snapshot.snapshot_hash()}, source=snapshot.source.to_dict())
        report = run_preflight_tool(runtime)
        if audit:
            audit.append("preflight_result", report, source=snapshot.source.to_dict())
        _print_report(report, args.json_output)

    if args.prompt:
        try:
            assistant = create_assistant(runtime, live_agent=args.live_agent)
            if args.live_agent:
                answer = _live_prompt(assistant, args.prompt)
            else:
                answer = assistant.respond(args.prompt)
        except Exception as exc:
            print("assistant request blocked: %s" % exc, file=sys.stderr)
            return 3
        if args.json_output:
            print(json.dumps({"assistant": answer}, sort_keys=True))
        else:
            print("assistant: %s" % answer)
    elif args.live_agent:
        try:
            create_assistant(runtime, live_agent=True)
        except Exception as exc:
            print("live-agent mode blocked: %s" % exc, file=sys.stderr)
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
