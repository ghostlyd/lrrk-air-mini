"""Native IMU snapshot wire contract, with address and undefined-behavior checks."""
from pathlib import Path
import importlib.util
import os
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ImuHealthTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("LW_IMU_GENERATOR"), "set LW_IMU_GENERATOR for pinned schema verification")
    def test_generated_schema(self):
        generator = Path(os.environ["LW_IMU_GENERATOR"])
        existing = Path(os.environ["LW_IMU_EXISTING_HEADERS"])
        spec = importlib.util.spec_from_file_location("verify_usb_ids", ROOT / "verify_usb_ids.py")
        reservations = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reservations)
        with tempfile.TemporaryDirectory(prefix="lw-imu-schema-") as directory:
            command = [str(generator), "-flight", str(ROOT / "uavobjects"),
                       str(generator.parents[2]), "LiteWingIMUHealth"]
            print("GENERATE (fresh cwd):", directory, " ".join(command), flush=True)
            result = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stdout + result.stderr, end="", flush=True)
            generated = Path(directory) / "flight"
            header = (generated / "litewingimuhealth.h").read_text()
            source = (generated / "litewingimuhealth.c").read_text()
            self.assertEqual(reservations.verify(generated), 1)
            count = reservations.verify(existing)
            new_id = int(reservations.DEFINITION.findall(header)[0][1], 0)
            self.assertEqual(new_id & 1, 0)
            occupied = set(reservations.RESERVED)
            for path in existing.glob("*.h"):
                for _, raw in reservations.DEFINITION.findall(path.read_text()):
                    value = int(raw.strip(), 0)
                    occupied.update((value, (value + 1) & 0xffffffff))
            self.assertTrue({new_id, new_id + 1}.isdisjoint(occupied))
            print(f"IDS=PASS object=0x{new_id:08X} metadata=0x{new_id+1:08X} existing_objects={count} maintenance={sorted(reservations.RESERVED)}", flush=True)
            self.assertIn("ACCESS_READONLY << UAVOBJ_GCS_ACCESS_SHIFT", source)
            self.assertIn("ACCESS_READWRITE << UAVOBJ_ACCESS_SHIFT", source)
            self.assertIn("LITEWINGIMUHEALTH_ISSINGLEINST 1", header)
            self.assertIn("LITEWINGIMUHEALTH_ISSETTINGS 0", header)
            declarations = re.search(r"typedef struct \{.*?LiteWingIMUHealthData;", header, re.S).group()
            defaults = "\n".join(re.findall(r"    data\.\w+ = .*?;", source))
            offsets = {"SampleAgeMs": 0, "Version": 4, "IdentityVerified": 5,
                       "WhoAmI": 6, "SampleSeen": 7, "Health": 8}
            assertions = "\n".join(
                f'_Static_assert(offsetof(LiteWingIMUHealthDataPacked, {field}) == {offset}, "{field}");'
                for field, offset in offsets.items())
            probe = Path(directory) / "layout.c"
            probe.write_text('''#include <stdint.h>
#include <stddef.h>
#include <assert.h>
#include <string.h>
#include <stdio.h>
#include "litewing_imu_health.h"
''' + declarations + "\n" + assertions + '''
_Static_assert(sizeof(LiteWingIMUHealthDataPacked) == 9, "packed size");
_Static_assert(sizeof(LiteWingIMUHealthData) == 9, "registered size");
int main(void) {
    LiteWingIMUHealthDataPacked data = {0};
''' + defaults + '''
    uint8_t bytes[9];
    struct lw_imu_observation unseen = {0};
    lw_imu_health_export(&unseen, 99, 100, bytes);
    assert(memcmp(&data, bytes, 9) == 0);
    data = (LiteWingIMUHealthDataPacked){0x12345678,1,1,0x68,1,1};
    struct lw_imu_observation fresh = {1,0x68,1,1,0};
    lw_imu_health_export(&fresh, 0x12345678, UINT32_MAX, bytes);
    assert(memcmp(&data, bytes, 9) == 0);
    puts("GENERATED_LAYOUT_DEFAULTS_WIRE=PASS size=9 offsets=0,4,5,6,7,8 access=gcs-readonly");
}
''')
            binary = Path(directory) / "layout"
            command = ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                       "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                       "-I", str(ROOT / "target/include"), str(probe),
                       str(ROOT / "target/litewing_imu_health.c"), "-o", str(binary)]
            print("COMPILE:", " ".join(command), flush=True)
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print("RUN:", binary, flush=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stdout, end="", flush=True)

    def test_observation_wire_contract(self):
        with tempfile.TemporaryDirectory(prefix="lw-imu-native-") as directory:
            binary = Path(directory) / "imu_health"
            command = [
                "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                "-I", str(ROOT / "target/include"),
                str(ROOT / "tests/imu_health_test.c"),
                str(ROOT / "target/litewing_imu_health.c"), "-o", str(binary),
            ]
            print("COMPILE:", " ".join(command), flush=True)
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print("RUN:", binary, flush=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stdout, end="", flush=True)


if __name__ == "__main__":
    unittest.main()
