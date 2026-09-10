"""Build-time USB IDs must not shadow generated data or metadata objects."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class USBIDReservationTests(unittest.TestCase):
    def check(self, definition, success):
        script = ROOT / "verify_usb_ids.py"
        self.assertTrue(script.exists(), "build-time reservation check missing")
        with tempfile.TemporaryDirectory() as directory:
            objects = Path(directory)
            (objects / "example.h").write_text(definition)
            result = subprocess.run([sys.executable,str(script),"--objects",str(objects)],
                                    capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode==0,success,result.stdout+result.stderr)
            if success:
                self.assertIn("USB_ID_RESERVATIONS=PASS",result.stdout)
            else:
                self.assertNotIn("USB_ID_RESERVATIONS=PASS",result.stdout)

    def test_normal_generated_ids(self):
        self.check("#define EXAMPLE_OBJID 0xEF69B6BC\n",True)

    def test_data_and_metadata_collisions(self):
        for value in (0x4C575046,0x4C575048,0x4C575045,0x4C575047):
            for representation in (hex(value),str(value)):
                with self.subTest(value=representation):
                    self.check("#define EXAMPLE_OBJID "+representation+"\n",False)

    def test_unrecognized_or_missing_id_is_not_success(self):
        for value in ("ALIAS", "(0x4C575000 + 0x46)", "0x100000000", "-1", ""):
            with self.subTest(value=value):
                self.check("#define EXAMPLE_OBJID "+value+"\n",False)
        self.check("#define EXAMPLE_NUMBYTES 8\n",False)

    def test_all_headers_are_checked(self):
        script = ROOT / "verify_usb_ids.py"
        self.assertTrue(script.exists(), "build-time reservation check missing")
        with tempfile.TemporaryDirectory() as directory:
            objects=Path(directory)
            (objects/"first.h").write_text("#define FIRST_OBJID 0xEF69B6BC\n")
            (objects/"last.h").write_text("#define LAST_OBJID 0x4C575048\n")
            result=subprocess.run([sys.executable,str(script),"--objects",str(objects)],
                                  capture_output=True,text=True,timeout=5)
            self.assertNotEqual(result.returncode,0)
