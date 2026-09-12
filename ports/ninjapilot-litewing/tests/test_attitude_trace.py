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
    def test_generated_sensor_early_returns_invalidate_capture(self):
        upstream=os.environ.get('LRRK_TEST_FLIGHT_ROOT')
        if not upstream:self.skipTest('set LRRK_TEST_FLIGHT_ROOT')
        import prepare_control
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            prepare_control.prepare(Path(upstream)/'flight/modules',out/'control')
            code=(out/'control/attitude.c').read_text()
            signature='static int32_t updateSensorsCC3D(AccelStateData *accelStateData, GyroStateData *gyrosData)\n{'
            start=code.index(signature)
            end=code.index('    float invcount = 1.0f / count;',start)
            # Execute the actual acquisition/early-return prefix. The remaining
            # arithmetic is covered by the capture/application test below.
            source='''#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
typedef struct {float x,y,z;} AccelStateData;
typedef AccelStateData GyroStateData;
typedef int BaseType_t;
typedef int xQueueHandle;
static bool trace_sample_valid,gyro_ro,accel_ro;
static int pending;
static const int sensor_period_ms=2;
static struct {AccelStateData sample[2]; int temperature;} sample;
static void *get_queue(int unused) {(void)unused;return 0;}
static struct {void *(*get_queue)(int);} ATTITUDE_IMU_DRIVER={get_queue};
#define xQueueHandle void *
#define mpu6000_data (&sample)
#define pdTRUE 1
#define PERF_TRACK_VALUE(a,b) ((void)0)
static int GyroStateReadOnly(void){return gyro_ro;}
static int AccelStateReadOnly(void){return accel_ro;}
static int xQueueReceive(void *q,void *data,int wait) {
    (void)q;(void)data;(void)wait;
    if(pending){pending=0;return 1;}return 0;
}
'''+code[start:end]+'''
#endif
    (void)accels;(void)gyros;(void)temp;(void)accelStateData;(void)gyrosData;
    return 7;
}
int main(void){
    AccelStateData a={0};GyroStateData g={0};
    trace_sample_valid=true;pending=0;
    assert(updateSensorsCC3D(&a,&g)==-1 && !trace_sample_valid);
    trace_sample_valid=true;pending=1;gyro_ro=true;
    assert(updateSensorsCC3D(&a,&g)==0 && !trace_sample_valid);
    trace_sample_valid=true;pending=1;gyro_ro=false;accel_ro=true;
    assert(updateSensorsCC3D(&a,&g)==0 && !trace_sample_valid);
    return 0;
}
'''
            (out/'early.c').write_text(source)
            binary=str(out/'early')
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',
                '-DCONFIG_LRRK_ATTITUDE_TRACE=1','-DPIOS_INCLUDE_ICM20602',
                str(out/'early.c'),'-o',binary],check=True)
            subprocess.run([binary],check=True)

    def test_generated_sensor_bias_capture_executes_actual_application(self):
        upstream=os.environ.get('LRRK_TEST_FLIGHT_ROOT')
        if not upstream:self.skipTest('set LRRK_TEST_FLIGHT_ROOT')
        import prepare_control
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            prepare_control.prepare(Path(upstream)/'flight/modules',out/'control')
            code=(out/'control/attitude.c').read_text()
            marker=code.index('/* Same task and sample, before applying')
            start=code.rfind('#if CONFIG_LRRK_ATTITUDE_TRACE',0,marker)
            end=code.index('    // Force the roll & pitch gyro rates',marker)
            body=code[start:end]
            source='''#include <assert.h>
#include <stdbool.h>
static float trace_pre_bias[3],trace_applied_bias[3];
static bool trace_sample_valid;
typedef struct {float x,y,z;} Gyro;
static void capture(float gyros[3], float gyro_correct_int[3], bool bias_correct_gyro, Gyro *gyrosData) {
'''+body+'''
}
int main(void) {
    float input[3]={10,-20,30},bias[3]={1,2,-3}; Gyro output;
    capture(input,bias,true,&output);
    assert(trace_sample_valid && output.x==11 && output.y==-18 && output.z==27);
    assert(trace_pre_bias[0]==10 && trace_pre_bias[1]==-20 && trace_pre_bias[2]==30);
    assert(trace_applied_bias[0]==1 && trace_applied_bias[1]==2 && trace_applied_bias[2]==-3);
    input[0]=99; bias[0]=500; trace_sample_valid=false;
    capture(input,bias,false,&output);
    assert(trace_sample_valid && output.x==99 && trace_pre_bias[0]==99);
    assert(trace_applied_bias[0]==0 && trace_applied_bias[1]==0 && trace_applied_bias[2]==0);
    return 0;
}
'''
            (out/'capture.c').write_text(source)
            binary=str(out/'capture')
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',
                '-DCONFIG_LRRK_ATTITUDE_TRACE=1',str(out/'capture.c'),'-o',binary],check=True)
            subprocess.run([binary],check=True)

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
            for value in (0xC6CEDB44,0xC6CEDB43,0xC6CEDB45):
                (collision/'fake.h').write_text(f'#define FAKE_OBJID {value}\n')
                with self.assertRaises(ValueError):
                    prepare_attitude_trace.validate(out/'flight',[collision])
            declaration=re.search(r'typedef struct \{.*?LiteWingAttitudeTraceData;',header,re.S).group()
            (out/'litewingattitudetrace.h').write_text('#include "pwm_sdk.h"\n'+declaration+
                '\n#define LITEWINGATTITUDETRACE_OBJID 0xC6CEDB44u\n'
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
