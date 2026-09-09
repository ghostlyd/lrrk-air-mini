"""Read-only telemetry adapter boundaries."""

from __future__ import annotations

from pathlib import Path
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
