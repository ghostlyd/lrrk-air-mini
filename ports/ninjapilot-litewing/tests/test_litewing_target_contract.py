import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LiteWingContractTests(unittest.TestCase):
    def test_pure_contract_compiles_with_warnings_as_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "contract-test"
            result = subprocess.run(
                [
                    "cc",
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    str(ROOT / "contract"),
                    str(ROOT / "contract" / "litewing_contract.c"),
                    str(ROOT / "tests" / "contract_test.c"),
                    "-o",
                    str(binary),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run([str(binary)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == "__main__":
    unittest.main()
