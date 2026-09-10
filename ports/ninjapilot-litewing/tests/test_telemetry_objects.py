"""Pinned real object packer behind a zero-wait telemetry read guard."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_arming_maintenance import function

ROOT = Path(__file__).resolve().parents[1]


class TelemetryObjectTests(unittest.TestCase):
    def test_actual_pack_with_contention_and_schema_bounds(self):
        upstream = os.environ.get("LRRK_TEST_FLIGHT_ROOT")
        if not upstream:
            self.skipTest("pinned flight checkout not supplied")
        spec = importlib.util.spec_from_file_location("prepare_objects", ROOT / "prepare_arming_maintenance.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            module.prepare(Path(upstream) / "flight/uavobjects", out / "generated")
            code = (out / "generated/uavobjectmanager.c").read_text()
            # The serializer under the guard is the real pinned function,
            # including its recursive mutex acquisition and instance lookup.
            (out / "pack.inc").write_text(function(code, "UAVObjPack") + "\n" +
                                           function(code, "lw_telemetry_try_pack"))
            binary = out / "objects"
            result = subprocess.run([
                "cc", "-std=c11", "-D_XOPEN_SOURCE=700", "-pthread", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                "-I", str(out), "-I", str(ROOT / "target/include"),
                str(ROOT / "tests/telemetry_objects_test.c"), "-o", str(binary)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            # A blocking guard deadlocks behind the holder until the test
            # timeout: the holder is released only after a skipped read.
            guarded = (out / "pack.inc").read_text()
            (out / "pack.inc").write_text(guarded.replace(
                "xSemaphoreTakeRecursive(mutex, 0)",
                "xSemaphoreTakeRecursive(mutex, portMAX_DELAY)"))
            mutant = out / "blocking-objects"
            result = subprocess.run([
                "cc", "-std=c11", "-D_XOPEN_SOURCE=700", "-pthread",
                "-I", str(out), "-I", str(ROOT / "target/include"),
                str(ROOT / "tests/telemetry_objects_test.c"), "-o", str(mutant)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            with self.assertRaises(subprocess.TimeoutExpired):
                subprocess.run([str(mutant)], capture_output=True, timeout=1)
