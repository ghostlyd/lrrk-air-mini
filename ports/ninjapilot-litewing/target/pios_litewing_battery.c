/* ESP-IDF 5.3.2 adapter. No UAVObject, arming, settings, or motor writes. */
#include "pios_litewing_battery.h"
#include "esp_adc/adc_continuous.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static adc_continuous_handle_t adc;
static adc_cali_handle_t calibration;
static bool attempted, ready, faulted;
static int owner_core;
static TaskHandle_t owner_task;
/* ISR and worker run on the same core. Worker only clears while ADC stopped. */
static volatile bool overflow;

static bool on_overflow(adc_continuous_handle_t handle,
                         const adc_continuous_evt_data_t *event, void *context)
{
    (void)handle; (void)event; (void)context;
    overflow = true;
    return false;
}

static int flush(void *context)
{
    (void)context;
    int result = adc_continuous_flush_pool(adc);
    if (result == ESP_OK) overflow = false;
    return result;
}
static int start(void *context) { (void)context; return adc_continuous_start(adc); }
static int stop(void *context) { (void)context; return adc_continuous_stop(adc); }
static int overflowed(void *context) { (void)context; return overflow; }
static int64_t clock_us(void *context) { (void)context; return esp_timer_get_time(); }
static int calibrate(void *context, int raw, int *millivolts)
{
    (void)context;
    return adc_cali_raw_to_voltage(calibration, raw, millivolts);
}
static int read_words(void *context, uint32_t *words, size_t capacity,
                       size_t *count, uint32_t timeout_ms)
{
    (void)context;
    *count = 0;
    if (capacity != 16 || timeout_ms != 20) return ESP_ERR_INVALID_ARG;
    uint32_t bytes = 0;
    int result = adc_continuous_read(adc, (uint8_t *)words, 64, &bytes, timeout_ms);
    if (result != ESP_OK) return result;
    if (bytes != 64) return ESP_ERR_INVALID_SIZE;
    *count = 16;
    return ESP_OK;
}
static const struct litewing_battery_acquisition_ops ops = {
    .flush = flush, .start = start, .read = read_words, .stop = stop,
    .overflowed = overflowed, .clock = clock_us, .calibrate = calibrate,
};

int PIOS_LiteWing_BatteryADC_Init(void)
{
    if (attempted) return -1;
    attempted = true;
    owner_core = xPortGetCoreID();
    owner_task = xTaskGetCurrentTaskHandle();
    adc_unit_t unit;
    adc_channel_t channel;
    if (adc_continuous_io_to_channel(2, &unit, &channel) != ESP_OK
        || unit != ADC_UNIT_1 || channel != ADC_CHANNEL_1) return -1;
    adc_continuous_handle_cfg_t handle_config = {
        .max_store_buf_size = 256, .conv_frame_size = 64, .flags.flush_pool = 0,
    };
    if (adc_continuous_new_handle(&handle_config, &adc) != ESP_OK) return -1;
    adc_digi_pattern_config_t pattern = {
        .atten = ADC_ATTEN_DB_12, .channel = ADC_CHANNEL_1,
        .unit = ADC_UNIT_1, .bit_width = ADC_BITWIDTH_12,
    };
    adc_continuous_config_t config = {
        .pattern_num = 1, .adc_pattern = &pattern, .sample_freq_hz = 1000,
        .conv_mode = ADC_CONV_SINGLE_UNIT_1, .format = ADC_DIGI_OUTPUT_FORMAT_TYPE2,
    };
    adc_cali_curve_fitting_config_t cal_config = {
        .unit_id = ADC_UNIT_1, .chan = ADC_CHANNEL_1,
        .atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_12,
    };
    adc_continuous_evt_cbs_t callbacks = { .on_pool_ovf = on_overflow };
    if (adc_continuous_config(adc, &config) != ESP_OK
        || adc_cali_create_scheme_curve_fitting(&cal_config, &calibration) != ESP_OK
        || adc_continuous_register_event_callbacks(adc, &callbacks, NULL) != ESP_OK) {
        /* No start has occurred. Check cleanup; retain ambiguous handles and
         * prohibit another init instead of freeing resources twice. */
        if (calibration && adc_cali_delete_scheme_curve_fitting(calibration) == ESP_OK)
            calibration = NULL;
        if (adc_continuous_deinit(adc) == ESP_OK) adc = NULL;
        faulted = true;
        return -1;
    }
    ready = true;
    return 0;
}

bool PIOS_LiteWing_BatteryADC_Read(struct litewing_battery_sample *sample)
{
    *sample = (struct litewing_battery_sample){0};
    if (!ready || xPortGetCoreID() != owner_core
        || xTaskGetCurrentTaskHandle() != owner_task) return false;
    return litewing_battery_acquire(sample, &faulted, &ops, NULL);
}
