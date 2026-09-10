"""Real acquisition-store serializer with a changed sample at the clock boundary."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BatterySnapshotTests(unittest.TestCase):
    def test_coherent_bytes_age_and_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "snapshot"
            (Path(directory) / "openpilot.h").write_text(
                '#include "uavobjectmanager.h"\n'
                'uint32_t UAVObjGetID(UAVObjHandle);\n'
                'uint16_t UAVObjGetNumBytes(UAVObjHandle);\n'
                'int32_t UAVObjPack(UAVObjHandle,uint16_t,uint8_t *);\n')
            result = subprocess.run([
                "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pthread",
                "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                "-I", directory, "-I", str(ROOT / "tests/gcs_stubs"), "-I", str(ROOT / "target/include"),
                str(ROOT / "target/litewing_battery_pack.c"),
                str(ROOT / "target/litewing_battery_voltage.c"),
                str(ROOT / "tests/battery_snapshot_test.c"), "-o", str(binary)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
