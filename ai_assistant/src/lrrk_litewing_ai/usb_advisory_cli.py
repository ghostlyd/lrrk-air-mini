"""Bounded USB telemetry advisory launcher; no flight control interface."""
import argparse
import asyncio
import hashlib
import json
import math
import sys
import uuid
from pathlib import Path
from threading import Event

from .audit import AuditLog
from .cli import _live_prompt
from .live_uavtalk import LiveUAVTalkCollector, SerialTelemetryTransport
from .tools import run_preflight_tool
from .usb_advisory import BoundedAnalysis, run_usb_advisory


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', required=True)
    parser.add_argument('--usb-location', required=True)
    parser.add_argument('--private-capture', type=Path, required=True)
    parser.add_argument('--audit-log', type=Path, required=True)
    parser.add_argument('--duration', type=float, default=15)
    parser.add_argument('--interval', type=float, default=5)
    parser.add_argument('--max-calls', type=int, default=3)
    parser.add_argument('--live-agent', action='store_true')
    parser.add_argument('--prompt', default='Summarize the observed telemetry and deterministic preflight findings. Do not execute actions.')
    args = parser.parse_args(argv)
    cancellation = Event()
    audit = None
    try:
        if not math.isfinite(args.duration) or not .1 <= args.duration <= 60:
            raise ValueError('invalid session duration')
        BoundedAnalysis(lambda *unused: None, interval_s=args.interval, max_calls=args.max_calls)
        if args.private_capture.resolve() == args.audit_log.resolve():
            raise ValueError('capture and audit must be separate')
        if args.private_capture.exists() or args.audit_log.exists():
            raise ValueError('new capture and audit paths required')
        session = uuid.uuid4().hex
        audit = AuditLog(args.audit_log, session)
        audit.append('usb_session_started', {'mode': 'openai' if args.live_agent else 'offline'})

        def analyze(runtime, item):
            report = run_preflight_tool(runtime)
            record = {'historical': True, 'session_id': session,
                      'captured_at': item.snapshot.captured_at.isoformat(),
                      'snapshot_hash': item.snapshot.snapshot_hash(),
                      'preflight': report}
            if args.live_agent:
                audit.append('provider_request', {'snapshot_hash': record['snapshot_hash'],
                    'prompt_sha256': hashlib.sha256(args.prompt.encode()).hexdigest()})
                try:
                    answer = _live_prompt(runtime, args.prompt, timeout_s=30,
                                          stop=cancellation.is_set)
                except asyncio.CancelledError:
                    audit.append('provider_result', {'outcome': 'cancelled'})
                    return
                except Exception:
                    audit.append('provider_result', {'outcome': 'failed'})
                    raise
                audit.append('provider_result', {'outcome': 'completed',
                    'snapshot_hash': record['snapshot_hash'],
                    'response_sha256': hashlib.sha256(answer.encode()).hexdigest()})
                record['assistant'] = answer
            audit.append('usb_advisory_result', {key: value for key, value in record.items()
                                                if key != 'assistant'})
            if not cancellation.is_set():
                print(json.dumps(record, sort_keys=True), flush=True)

        transport = SerialTelemetryTransport(args.device, args.usb_location)
        collector = LiveUAVTalkCollector(transport, args.private_capture)
        count = run_usb_advisory(collector, analyze, cancellation.is_set,
            duration_s=args.duration, interval_s=args.interval,
            max_calls=args.max_calls, cancellation=cancellation)
        audit.append('usb_session_ended', {'snapshots_offered': count})
        return 0
    except KeyboardInterrupt:
        cancellation.set()
        return 130
    except Exception as exc:
        cancellation.set()
        if audit is not None:
            try:
                audit.append('usb_session_failed', {'error_class': type(exc).__name__})
            except Exception:
                print('USB advisory failure audit could not be written', file=sys.stderr)
        print('USB advisory session failed; no flight command was issued by this launcher',
              file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
