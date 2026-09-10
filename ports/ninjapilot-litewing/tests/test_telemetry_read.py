"""Selection and failure behavior; target build checks actual generated headers."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TelemetryReadTests(unittest.TestCase):
    def test_selection_and_failed_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "openpilot.h").write_text('#include "uavobjectmanager.h"\n')
            for name, oid, size in (
                ("AttitudeState", 0xD7E0D964, 28), ("FlightStatus", 0xEF69B6BC, 8),
                ("FlightBatteryState", 0x26962352, 30), ("SystemAlarms", 0x6B7639EC, 25),
                ("ActuatorCommand", 0xB8229FE4, 29),
            ):
                (out / f"{name.lower()}.h").write_text(
                    f'#define {name.upper()}_OBJID {oid}u\n'
                    f'#define {name.upper()}_NUMBYTES {size}\n'
                    f'UAVObjHandle {name}Handle(void);\n')
            binary = out / "read"
            result = subprocess.run([
                "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pthread",
                "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                "-I", directory, "-I", str(ROOT / "tests/gcs_stubs"),
                "-I", str(ROOT / "target/include"),
                str(ROOT / "target/litewing_telemetry_read.c"),
                str(ROOT / "tests/telemetry_read_test.c"), "-o", str(binary)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
