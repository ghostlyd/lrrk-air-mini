"""Exercise the artifact gate with controlled nm process output."""
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOOD = """3c010010 R uavobject_persistence_linked
42001210 T UAVObjSave
42001290 T UAVObjLoad
42001310 T UAVObjDelete
42002000 T UAVObjPers_stub
"""


class PersistenceLinkTests(unittest.TestCase):
    def invoke(self, symbols=GOOD, nm_rc=0, elf=True):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "candidate.elf"
            if elf:
                artifact.write_bytes(b"\x7fELF" + bytes(60))
            nm = root / "nm"
            nm.write_text("#!/bin/sh\nprintf '%s' " + shlex.quote(symbols) +
                          "\nexit %d\n" % nm_rc)
            nm.chmod(0o700)
            return subprocess.run([sys.executable, str(ROOT / "verify_persistence_link.py"),
                "--elf", str(artifact), "--nm", str(nm)], capture_output=True,
                text=True, timeout=5)

    def test_accepts_distinct_strong_persistence_functions(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PERSISTENCE_LINK=PASS", result.stdout)

    def test_rejects_weak_stub_resolution_for_each_operation(self):
        for name in ("UAVObjSave", "UAVObjLoad", "UAVObjDelete"):
            with self.subTest(name=name):
                result = self.invoke(GOOD.replace("T " + name, "W " + name))
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertNotIn("PERSISTENCE_LINK=PASS", result.stdout)

    def test_rejects_missing_symbols_and_anchor(self):
        for name in ("UAVObjSave", "UAVObjLoad", "UAVObjDelete", "uavobject_persistence_linked"):
            with self.subTest(name=name):
                result = self.invoke("\n".join(line for line in GOOD.splitlines() if not line.endswith(name)))
                self.assertEqual(result.returncode, 1, result.stderr)

    def test_rejects_aliases_even_with_strong_symbol_type(self):
        for address in ("42002000", "42001290", "00000000"):
            with self.subTest(address=address):
                self.assertEqual(self.invoke(GOOD.replace("42001210", address)).returncode, 1)

    def test_rejects_ambiguous_duplicate_symbol(self):
        self.assertEqual(self.invoke(GOOD + "42003000 T UAVObjSave\n").returncode, 1)

    def test_rejects_tool_failure_and_missing_artifact(self):
        self.assertEqual(self.invoke(nm_rc=1).returncode, 1)
        self.assertEqual(self.invoke(elf=False).returncode, 1)

    def test_actual_artifact_when_explicitly_supplied(self):
        elf = os.environ.get("LRRK_PERSISTENCE_ELF")
        nm = os.environ.get("LRRK_PERSISTENCE_NM")
        if not elf or not nm:
            self.skipTest("real ESP-IDF artifact/tool not supplied; host fixtures are not firmware proof")
        result = subprocess.run([sys.executable, str(ROOT / "verify_persistence_link.py"),
            "--elf", elf, "--nm", nm], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_direct_app_and_flash_graphs_include_gate_when_build_supplied(self):
        directory, ninja = os.environ.get("LRRK_IDF_BUILD_DIR"), os.environ.get("LRRK_NINJA")
        if not directory or not ninja:
            self.skipTest("generated IDF graph not supplied; host fixtures do not prove target dependencies")
        for target in ("app", "flash"):
            with self.subTest(target=target):
                # -n prints commands without running them, especially flash.
                result = subprocess.run([ninja, "-C", directory, "-n", target],
                    capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("verify_persistence_link.py", result.stdout)
