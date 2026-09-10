"""Exercise the actual generated UART task body with bounded host I/O fixtures."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class USBTelemetryCleanupTests(unittest.TestCase):
    def test_uart_data_idle_and_missing_port_cleanup(self):
        script=ROOT/"prepare_usb_telemetry.py"
        self.assertTrue(script.exists(),"UART idle cleanup integration missing")
        upstream=os.environ.get("LRRK_TEST_FLIGHT_ROOT")
        if not upstream:
            self.skipTest("pinned flight checkout not supplied")
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            subprocess.run([sys.executable,str(script),"--source",str(Path(upstream)/"flight/modules/Telemetry"),
                            "--output",str(path)],check=True,capture_output=True)
            code=(path/"telemetry.c").read_text()
            start=code.index("static void telemetryRxTask(__attribute__((unused)) void *parameters)\n{")
            end=code.index("\n#ifdef PIOS_INCLUDE_RFM22B",start)
            (path/"task.inc").write_text(code[start:end])
            result=subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Werror",
                "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                "-I",str(path),"-I",str(ROOT/"target/include"),
                str(ROOT/"tests/usb_telemetry_cleanup_test.c"),"-o",str(path/"test")],
                capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(path/"test")],capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
