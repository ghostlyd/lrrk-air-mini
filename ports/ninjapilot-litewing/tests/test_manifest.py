import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import manifest  # noqa: E402


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / "SOURCE_MANIFEST.json"
        self.value = json.loads(self.path.read_text(encoding="utf-8"))

    def test_checked_in_manifest_is_valid(self):
        manifest.validate_manifest(self.value)

    def test_hardware_validation_cannot_be_enabled_by_accident(self):
        value = copy.deepcopy(self.value)
        value["target"]["hardware_validated"] = True
        with self.assertRaises(ValueError):
            manifest.validate_manifest(value)

    def test_patch_hashes_are_strict(self):
        value = copy.deepcopy(self.value)
        value["patches"][0]["sha256"] = "not-a-hash"
        with self.assertRaises(ValueError):
            manifest.validate_manifest(value)

    def test_mixed_case_commit_is_rejected(self):
        value = copy.deepcopy(self.value)
        value["sources"]["flight_tree"]["commit"] = value["sources"]["flight_tree"]["commit"].upper()
        with self.assertRaises(ValueError):
            manifest.validate_manifest(value)

    def test_repository_patch_checksum_matches_manifest(self):
        for patch in self.value["patches"]:
            if patch["source"] == "repository":
                path = ROOT.parent.parent / patch["path"]
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertEqual(actual, patch["sha256"])

    def test_reference_patches_are_not_applied_without_a_refresh(self):
        reference = [item for item in self.value["patches"] if item["source"] == "reference"]
        self.assertTrue(reference)
        self.assertTrue(all(item["apply"] is False for item in reference))
        self.assertTrue(all(item["source"] == "repository" for item in self.value["patches"] if item["apply"]))


if __name__ == "__main__":
    unittest.main()
