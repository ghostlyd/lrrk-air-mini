"""Read-only telemetry adapter boundaries."""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
import math
from typing import Iterable, Iterator, Protocol, Union

from .jsonl import iter_records
from .models import TelemetrySnapshot


class AdapterError(ValueError):
    pass


class TelemetryAdapter(Protocol):
    def snapshots(self) -> Iterable[TelemetrySnapshot]:
        ...


class JsonlTelemetryAdapter:
    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)

    def snapshots(self) -> Iterator[TelemetrySnapshot]:
        if not self.path.exists():
            raise AdapterError("telemetry input does not exist")
        try:
            records = iter_records(self.path)
            for index, record in enumerate(records, start=1):
                try:
                    yield TelemetrySnapshot.from_dict(record)
                except (TypeError, ValueError, KeyError) as exc:
                    raise AdapterError("invalid telemetry snapshot at line %d" % index) from exc
        except ValueError as exc:
            raise AdapterError(str(exc)) from exc


class UAVTalkAdapter:
    """Collect one bounded, read-side aggregate from the pinned LiteWing target."""

    def __init__(
        self,
        device: str,
        location: str,
        capture_path: Union[str, Path],
        duration_s: float = 2.0,
    ):
        if (isinstance(duration_s, bool)
                or not isinstance(duration_s, (int, float))
                or not math.isfinite(duration_s)
                or not 0.1 <= duration_s <= 5.0):
            raise AdapterError("live collection duration must be 0.1..5.0 seconds")
        self.device = device
        self.location = location
        self.capture_path = Path(capture_path)
        self.duration_s = duration_s

    def snapshots(self) -> Iterator[TelemetrySnapshot]:
        from .live_uavtalk import (
            LiveUAVTalkCollector,
            SerialTelemetryTransport,
            UAVTalkLiveError,
        )

        try:
            transport = SerialTelemetryTransport(self.device, self.location)
        except UAVTalkLiveError as exc:
            raise AdapterError(str(exc)) from exc
        try:
            collector = LiveUAVTalkCollector(
                transport,
                self.capture_path,
                duration_s=self.duration_s,
            )
        except UAVTalkLiveError as exc:
            transport.close()
            raise AdapterError(str(exc)) from exc
        try:
            yield collector.collect()
        except UAVTalkLiveError as exc:
            raise AdapterError(str(exc)) from exc


class UAVTalkCaptureAdapter:
    """Partial snapshots from a saved capture with explicit capture metadata."""

    def __init__(self, path: Union[str, Path], captured_at: datetime):
        if not isinstance(captured_at, datetime) or captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise AdapterError("capture time must be timezone-aware")
        self.path = Path(path)
        self.captured_at = captured_at

    def snapshots(self) -> Iterator[TelemetrySnapshot]:
        from .uavtalk import UAVTalkError, read_frames
        from .uavobjects import snapshot_from_frame

        if not self.path.is_file():
            raise AdapterError("capture must be a regular file")
        try:
            with self.path.open("rb") as stream:
                for frame in read_frames(stream):
                    snapshot = snapshot_from_frame(frame, self.captured_at)
                    if snapshot is not None:
                        yield snapshot
        except UAVTalkError as exc:
            raise AdapterError(str(exc)) from exc
