"""Read-only telemetry adapter boundaries."""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
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
    """Reserved protocol boundary; deliberately has no write operation."""

    def __init__(self, endpoint: str):
        self.endpoint = endpoint

    def snapshots(self) -> Iterator[TelemetrySnapshot]:
        raise AdapterError("UAVTalk adapter is not enabled in the offline build")


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
