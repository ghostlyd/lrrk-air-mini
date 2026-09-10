"""Exercise generated write functions and their shared maintenance exclusion."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def function(code, name):
    start = code.index("int32_t " + name + "(")
    opening = code.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (code[end] == "{") - (code[end] == "}")
        end += 1
    return code[start:end]


class ArmingMaintenanceTests(unittest.TestCase):
    def test_paused_writes_cannot_cross_reservation(self):
        generator = ROOT / "prepare_arming_maintenance.py"
        self.assertTrue(generator.exists(), "object-manager arming exclusion missing")
        upstream = os.environ.get("LRRK_TEST_FLIGHT_ROOT")
        if not upstream:
            self.skipTest("pinned flight checkout not supplied")
        spec = importlib.util.spec_from_file_location("arming_prepare", generator)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            module.prepare(Path(upstream) / "flight/uavobjects", output / "generated")
            code = (output / "generated/uavobjectmanager.c").read_text()
            # Compile the actual adapted three write functions, not reimplemented
            # setter mocks. Object lookup/events are minimal storage fixtures;
            # the mutex uses real pthread recursive/try-lock semantics.
            selected = "\n".join(function(code, name) for name in (
                "UAVObjUnpack", "UAVObjSetInstanceData", "UAVObjSetInstanceDataField"))
            (output / "writes.inc").write_text(selected)
            binary = output / "arming"
            result = subprocess.run([
                "cc", "-std=c11", "-D_XOPEN_SOURCE=700", "-pthread", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                "-I", str(output), "-I", str(ROOT / "target/include"),
                str(ROOT / "tests/arming_maintenance_test.c"), "-o", str(binary),
            ], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            # Reproduce the original bug: identical real functions without the
            # generated write checks must allow the paused arm and fail the test.
            original = (Path(upstream) / "flight/uavobjects/uavobjectmanager.c").read_text()
            selected = "\n".join(function(original, name) for name in (
                "UAVObjUnpack", "UAVObjSetInstanceData", "UAVObjSetInstanceDataField"))
            (output / "writes.inc").write_text(selected)
            command = ["cc", "-std=c11", "-D_XOPEN_SOURCE=700", "-pthread",
                       "-I", str(output), "-I", str(ROOT / "target/include"),
                       str(ROOT / "tests/arming_maintenance_test.c"), "-o", str(binary)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0, "unmodified setter unexpectedly excluded arming")
            self.assertIn("UAVObjSetInstanceData(&flight,0,&cached)==-1", result.stderr)
