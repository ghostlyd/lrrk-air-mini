import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lrrk_litewing_ai.agent import OfflineAssistant  # noqa: E402
from lrrk_litewing_ai.models import BatteryState, SensorHealth, SourceIdentity, TelemetrySnapshot  # noqa: E402
from lrrk_litewing_ai.tools import AssistantRuntime  # noqa: E402


class OfflineAgentTests(unittest.TestCase):
    def test_offline_response_has_no_credential_or_network_dependency(self):
        original = os.environ.pop("OPENAI_API_KEY", None)
        try:
            snapshot = TelemetrySnapshot(
                snapshot_id="offline-1",
                captured_at=datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc),
                source=SourceIdentity("test"),
                link_age_ms=10,
                armed=False,
                flight_mode="attitude",
                battery=BatteryState(voltage_v=3.9, percent=80),
                sensors=SensorHealth(imu_present=True, imu_identity="MPU6050", imu_healthy=True),
                actuators=(0, 0, 0, 0),
            )
            runtime = AssistantRuntime()
            runtime.ingest(snapshot)
            answer = OfflineAssistant(runtime).respond("show telemetry")
            self.assertTrue(answer["available"])
        finally:
            if original is not None:
                os.environ["OPENAI_API_KEY"] = original


if __name__ == "__main__":
    unittest.main()
