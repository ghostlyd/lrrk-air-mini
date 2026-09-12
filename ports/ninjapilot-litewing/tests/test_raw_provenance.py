"""Real native collector: catches aliasing, wrap and silent truncation."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RawProvenanceTests(unittest.TestCase):
    def test_retention_wrap_and_overflow(self):
        header = ROOT / 'target/include/litewing_raw_provenance.h'
        self.assertTrue(header.exists(), 'raw provenance collector is not implemented')
        with tempfile.TemporaryDirectory() as directory:
            binary = str(Path(directory) / 'test')
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', '-I', str(header.parent),
                            str(ROOT / 'tests/raw_provenance_test.c'), '-o', binary], check=True)
            subprocess.run([binary], check=True)
