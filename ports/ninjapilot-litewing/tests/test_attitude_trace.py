import subprocess
import tempfile
import unittest
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

class AttitudeTraceTests(unittest.TestCase):
    def test_adapted_estimator_captures_input_and_corrected_rates(self):
        upstream=os.environ.get('LRRK_TEST_FLIGHT_ROOT')
        if not upstream:self.skipTest('set LRRK_TEST_FLIGHT_ROOT')
        import prepare_control
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            prepare_control.prepare(Path(upstream)/'flight/modules',out/'control')
            code=(out/'control/attitude.c').read_text()
            start=code.index('__attribute__((optimize("O3"))) static void updateAttitude')
            end=code.index('static void settingsUpdatedCb',start)
            (out/'attitude_step.inc').write_text(code[start:end])
            for enabled in (0,1):
                binary=str(out/f'hook-{enabled}')
                subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',
                    '-Wno-unknown-attributes',f'-DCONFIG_LRRK_ATTITUDE_TRACE={enabled}',
                    '-I',str(out),str(ROOT/'tests/attitude_trace_hook_test.c'),
                    '-o',binary],check=True)
                result=subprocess.run([binary],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)

    def test_generated_wire_and_production_capture(self):
        upstream = os.environ.get('LRRK_TEST_FLIGHT_ROOT')
        if not upstream:
            self.skipTest('set LRRK_TEST_FLIGHT_ROOT for pinned generator')
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            subprocess.run([str(Path(upstream)/'ground/uavobjgenerator/uavobjgenerator'),
                '-flight',str(ROOT/'uavobjects'),upstream,'LiteWingAttitudeTrace'],
                cwd=out,check=True)
            header=(out/'flight/litewingattitudetrace.h').read_text()
            import prepare_attitude_trace
            prepare_attitude_trace.validate(out/'flight',[])
            collision=out/'collision';collision.mkdir()
            for value in (0x5E93B7FE,0x5E93B7FD,0x5E93B7FF):
                (collision/'fake.h').write_text(f'#define FAKE_OBJID {value}\n')
                with self.assertRaises(ValueError):
                    prepare_attitude_trace.validate(out/'flight',[collision])
            declaration=re.search(r'typedef struct \{.*?LiteWingAttitudeTraceData;',header,re.S).group()
            (out/'litewingattitudetrace.h').write_text('#include "pwm_sdk.h"\n'+declaration+
                '\n#define LITEWINGATTITUDETRACE_OBJID 0x5E93B7FEu\n'
                'int32_t LiteWingAttitudeTraceInitialize(void);\n'
                'UAVObjHandle LiteWingAttitudeTraceHandle(void);\n'
                'int LiteWingAttitudeTraceGetMetadata(UAVObjMetadata *);\n')
            for name in ('openpilot.h','uavobjectmanager.h','esp_timer.h'):
                (out/name).write_text('#include "pwm_sdk.h"\n')
            (out/'freertos').mkdir()
            (out/'freertos/FreeRTOS.h').write_text('#include "pwm_sdk.h"\n')
            binary=str(out/'module')
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',
                '-DCONFIG_LRRK_ATTITUDE_TRACE=1','-fsanitize=address,undefined',
                '-I',str(out),'-I',str(ROOT/'tests'),'-I',str(ROOT/'target/include'),
                str(ROOT/'target/litewing_attitude_trace.c'),
                str(ROOT/'target/litewing_attitude_trace_module.c'),
                str(ROOT/'tests/attitude_trace_module_test.c'),'-o',binary],check=True)
            result=subprocess.run([binary],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_ring_order_freeze_and_incomplete_reads(self):
        with tempfile.TemporaryDirectory() as d:
            binary = str(Path(d) / 'trace')
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-I', str(ROOT/'target/include'),
                str(ROOT/'target/litewing_attitude_trace.c'),
                str(ROOT/'tests/attitude_trace_test.c'), '-o', binary], check=True)
            result = subprocess.run([binary], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
