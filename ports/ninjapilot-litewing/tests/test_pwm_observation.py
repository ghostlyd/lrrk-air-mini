"""Read-only PWM USB integration, using the pinned generated wire schema."""
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class PwmObservationTests(unittest.TestCase):
    def test_generated_wire_and_access(self):
        self.assertTrue((ROOT / 'prepare_pwm_observation.py').exists())
        upstream = os.environ.get('LRRK_TEST_FLIGHT_ROOT')
        if not upstream:
            self.skipTest('set LRRK_TEST_FLIGHT_ROOT for pinned generator')
        import prepare_pwm_observation as schema
        import prepare_arming_maintenance
        from test_arming_maintenance import function
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            generator = Path(os.environ.get('LW_IMU_GENERATOR',
                str(Path(upstream) / 'ground/uavobjgenerator/uavobjgenerator')))
            existing = Path(os.environ.get('LW_IMU_EXISTING_HEADERS',
                str(Path(upstream) / 'build/uavobject-synthetics/flight')))
            (out / 'imu').mkdir()
            subprocess.run([str(generator), '-flight', str(ROOT / 'uavobjects'), upstream,
                'LiteWingIMUHealth'], cwd=out / 'imu', check=True, timeout=30)
            custom = out / 'imu/flight'
            schema.prepare(upstream, out / 'pwm', custom, generator, existing)
            generated = out / 'pwm/object'
            header = (generated / 'litewingpwmobservation.h').read_text()
            source = (generated / 'litewingpwmobservation.c').read_text()
            self.assertIn('ACCESS_READONLY << UAVOBJ_GCS_ACCESS_SHIFT', source)
            self.assertIn('LITEWINGPWMOBSERVATION_ISSINGLEINST 1', header)
            self.assertIn('LITEWINGPWMOBSERVATION_ISSETTINGS 0', header)
            # Verify both custom and upstream object/metadata collisions fail.
            for value in (schema.OBJID, schema.OBJID - 1, schema.OBJID + 1):
                collision = out / 'collision'
                collision.mkdir(exist_ok=True)
                (collision / 'collision.h').write_text(f'#define COLLISION_OBJID {value}\n')
                with self.assertRaises(ValueError):
                    schema.validate(generated, collision, custom)
                with self.assertRaises(ValueError):
                    schema.validate(generated, existing, collision)
            prepare_arming_maintenance.prepare(Path(upstream) / 'flight/uavobjects', out / 'manager')
            unpack = function((out / 'manager/uavobjectmanager.c').read_text(), 'UAVObjUnpack')
            # Execute the actual early read-only guard, before any manager side effect.
            guard = unpack[:unpack.index('return -1;') + len('return -1;')] + '\nreturn 123;\n}\n'
            (out / 'unpack.inc').write_text(guard)
            declarations = re.search(r'typedef struct \{.*?LiteWingPWMObservationData;', header, re.S).group()
            defaults = '\n'.join(re.findall(r'    data\.\w+(?:\[\d+\])? = .*?;', source))
            (out / 'litewingpwmobservation.h').write_text(
                '#include "pwm_sdk.h"\n' + declarations + '\n' +
                f'#define LITEWINGPWMOBSERVATION_OBJID {schema.OBJID}u\n'
                'int32_t LiteWingPWMObservationInitialize(void);\n'
                'UAVObjHandle LiteWingPWMObservationHandle(void);\n'
                'int LiteWingPWMObservationGetMetadata(UAVObjMetadata *);\n'
                'static inline void schema_defaults(LiteWingPWMObservationData *out) {\n'
                'LiteWingPWMObservationData data = {0};\n' + defaults + '\n*out=data;\n}\n')
            for name in ('openpilot.h', 'uavobjectmanager.h', 'esp_timer.h'):
                (out / name).write_text('#include "pwm_sdk.h"\n')
            (out / 'freertos').mkdir()
            (out / 'freertos/FreeRTOS.h').write_text('#include "pwm_sdk.h"\n')
            binary = out / 'pwm-test'
            result = subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-Wno-unused-parameter', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                '-I', str(out), '-I', str(ROOT / 'tests'), '-I', str(ROOT / 'target/include'),
                str(ROOT / 'tests/pwm_observation_test.c'),
                str(ROOT / 'target/litewing_battery_pack.c'),
                str(ROOT / 'target/litewing_battery_voltage.c'),
                str(ROOT / 'target/litewing_pwm_observation.c'), '-o', str(binary)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for case in ('normal', 'register', 'handle', 'metadata', 'access'):
                result = subprocess.run([str(binary), case], capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                if case == 'normal':
                    spec = importlib.util.spec_from_file_location('pwm_decoder',
                        ROOT / 'diagnostics/pwm_observation.py')
                    decoder = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(decoder)
                    packets = [decoder.decode(bytes.fromhex(line[5:]))
                               for line in result.stdout.splitlines() if line.startswith('WIRE=')]
                    self.assertEqual(len(packets), 4)
                    self.assertFalse(packets[0]['available'])
                    self.assertEqual(packets[0]['submitted_ledc'], [None] * 4)
                    self.assertEqual(packets[1]['requested_duty'], [1, 256, 1000, 0])
                    self.assertEqual(packets[1]['submitted_ledc'], [2, 512, 2047, 0])
                    self.assertEqual(packets[2]['submitted_ledc'], [2, None, 2047, None])
                    self.assertFalse(packets[3]['available'])
                    self.assertEqual(packets[3]['snapshot_age_ms'], 100)


if __name__ == '__main__':
    unittest.main()
