#include "battery_sdk.h"
#include "pios_litewing_battery.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>

static const char *scenario;
static int core, task=1, creates, deletions, cal_deletions, starts, stops, reads;
static int64_t now=1000;
static bool running;
static event_cb overflow_cb;
static int fail(const char *name) { return strcmp(scenario,name)==0; }
int xPortGetCoreID(void) { return core; }
TaskHandle_t xTaskGetCurrentTaskHandle(void) { return (void *)(uintptr_t)task; }
int64_t esp_timer_get_time(void) { return now; }
int adc_continuous_io_to_channel(int gpio, adc_unit_t *unit, adc_channel_t *channel) {
    assert(gpio==2); *unit=0; *channel=fail("mapping")?2:1; return 0;
}
int adc_continuous_new_handle(const adc_continuous_handle_cfg_t *c, adc_continuous_handle_t *h) {
    assert(c->max_store_buf_size==256 && c->conv_frame_size==64 && !c->flags.flush_pool);
    creates++; if(fail("allocate")) return -1; *h=(void *)1; return 0;
}
int adc_continuous_config(adc_continuous_handle_t h, const adc_continuous_config_t *c) {
    assert(h && c->pattern_num==1 && c->sample_freq_hz==1000);
    assert(c->adc_pattern->unit==0 && c->adc_pattern->channel==1);
    assert(c->adc_pattern->atten==3 && c->adc_pattern->bit_width==12);
    assert(c->conv_mode==ADC_CONV_SINGLE_UNIT_1 && c->format==ADC_DIGI_OUTPUT_FORMAT_TYPE2);
    return fail("configure")?-1:0;
}
int adc_cali_create_scheme_curve_fitting(const adc_cali_curve_fitting_config_t *c, adc_cali_handle_t *h) {
    assert(c->unit_id==0 && c->chan==1 && c->atten==3 && c->bitwidth==12);
    if(fail("calibration-init")) {
        return -1;
    }
    *h=(void *)2;
    return 0;
}
int adc_continuous_register_event_callbacks(adc_continuous_handle_t h, const adc_continuous_evt_cbs_t *c, void *v) {
    assert(h && !v && !c->on_conv_done && c->on_pool_ovf);
    overflow_cb=c->on_pool_ovf;
    return fail("callbacks") || fail("cleanup") ? -1 : 0;
}
int adc_cali_delete_scheme_curve_fitting(adc_cali_handle_t h) {
    assert(h && !running); cal_deletions++; return fail("cleanup")?-1:0;
}
int adc_continuous_deinit(adc_continuous_handle_t h) {
    assert(h && !running); deletions++; return fail("cleanup")?-1:0;
}
int adc_continuous_flush_pool(adc_continuous_handle_t h) { assert(h && !running); return 0; }
int adc_continuous_start(adc_continuous_handle_t h) { assert(h && !running); starts++; running=true; return 0; }
int adc_continuous_stop(adc_continuous_handle_t h) {
    assert(h && running); stops++; if(fail("stop")) return -1; running=false; return 0;
}
int adc_continuous_read(adc_continuous_handle_t h,uint8_t *out,uint32_t max,uint32_t *bytes,uint32_t timeout) {
    assert(h && running && max==64 && timeout==20); reads++; now+=16000;
    for(unsigned i=0;i<16;i++) { uint32_t value=0x2028; memcpy(out+4*i,&value,4); }
    *bytes=fail("partial")?60:64;
    if(fail("overflow")) overflow_cb(h,NULL,NULL);
    return fail("timeout")?-1:0;
}
int adc_cali_raw_to_voltage(adc_cali_handle_t h,int raw,int *mv) {
    assert(h && !running && raw==40); *mv=1950; return fail("conversion")?-1:0;
}

int main(int argc,char **argv) {
    assert(argc==2); scenario=argv[1];
    struct litewing_battery_sample sample={.valid=true,.millivolts=3900};
    assert(!PIOS_LiteWing_BatteryADC_Read(&sample) && !sample.valid);
    int result=PIOS_LiteWing_BatteryADC_Init();
    bool init_failure=fail("mapping")||fail("allocate")||fail("configure")||
        fail("calibration-init")||fail("callbacks")||fail("cleanup");
    assert((result!=0)==init_failure);
    int old_creates=creates;
    assert(PIOS_LiteWing_BatteryADC_Init()!=0 && creates==old_creates);
    if(init_failure) {
        assert(!PIOS_LiteWing_BatteryADC_Read(&sample) && !sample.valid && starts==0);
        assert(deletions==(!fail("mapping") && !fail("allocate")));
        assert(cal_deletions==(fail("callbacks")||fail("cleanup")));
    } else {
        if(fail("core")) core=1;
        if(fail("task")) task=2;
        bool success=PIOS_LiteWing_BatteryADC_Read(&sample);
        assert(success==fail("success"));
        if(success) assert(sample.valid && sample.millivolts==3900 && sample.captured_us==1000);
        else assert(!sample.valid);
        if(fail("core")||fail("task")) assert(starts==0 && reads==0);
        else assert(starts==1 && stops==1 && reads==1);
        if(fail("stop")) {
            assert(!PIOS_LiteWing_BatteryADC_Read(&sample));
            assert(starts==1 && stops==1 && !sample.valid);
        }
        if(fail("partial")||fail("timeout")||fail("overflow")||fail("conversion")) {
            scenario="success";
            assert(PIOS_LiteWing_BatteryADC_Read(&sample));
            assert(sample.valid && sample.millivolts==3900 && sample.captured_us==17000);
            assert(starts==2 && stops==2 && reads==2);
        }
    }
    puts("PASS"); return 0;
}
