import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


class EspIdfWrapperTests(unittest.TestCase):
    def setUp(self):
        self.project = ROOT / "esp-idf"
        self.top_level = (self.project / "CMakeLists.txt").read_text(encoding="utf-8")
        self.component = (self.project / "main" / "CMakeLists.txt").read_text(encoding="utf-8")
        self.sdkconfig = (self.project / "sdkconfig.defaults").read_text(encoding="utf-8")

    def test_project_is_explicitly_esp32s3_and_external_source_pinned(self):
        self.assertIn('project(lrrk_litewing_ninjapilot)', self.top_level)
        for marker in (
            "NINJAPILOT_ROOT",
            "OPENPILOT_ESP32_ROOT",
            "verify_external_sources.py",
            "IDF_TARGET=esp32s3",
            "idf_component_register",
            "target_linker_script",
        ):
            self.assertIn(marker, self.component)

    def test_litewing_adapter_replaces_reference_servo_and_imu(self):
        self.assertIn("LITEWING_TARGET_SRCS", self.component)
        self.assertIn("pios_i2c.c", self.component)
        self.assertNotIn("/pios_servo.c", self.component)
        self.assertNotIn("/pios_icm20602.c", self.component)
        self.assertIn("pios_litewing_brushed_pwm.c", (ROOT / "target" / "sources.cmake").read_text(encoding="utf-8"))
        self.assertIn("pios_litewing_mpu6050.c", (ROOT / "target" / "sources.cmake").read_text(encoding="utf-8"))

    def test_defaults_keep_console_clean_and_watchdogs_enabled(self):
        self.assertIn('CONFIG_IDF_TARGET="esp32s3"', self.sdkconfig)
        self.assertIn("CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ_240=y", self.sdkconfig)
        self.assertIn("CONFIG_ESP_CONSOLE_UART_NONE=y", self.sdkconfig)
        self.assertIn("CONFIG_ESP_TASK_WDT_INIT=y", self.sdkconfig)
        self.assertIn('CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions.csv"', self.sdkconfig)

    def test_wrapper_has_no_flash_or_esptool_action(self):
        combined = "\n".join((self.top_level, self.component, (ROOT / "build.sh").read_text(encoding="utf-8")))
        self.assertNotIn("idf.py flash", combined)
        self.assertNotIn("esptool", combined)

    def test_manifest_required_files_are_present(self):
        manifest = json.loads((ROOT / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
        for path in manifest["target_adapter"]["required_files"]:
            self.assertTrue((REPO / path).is_file(), path)


if __name__ == "__main__":
    unittest.main()
