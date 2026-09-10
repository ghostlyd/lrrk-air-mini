#ifndef BATTERY_TEST_SDK_H
#define BATTERY_TEST_SDK_H
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
typedef void *adc_continuous_handle_t;
typedef void *adc_cali_handle_t;
typedef void *TaskHandle_t;
typedef int adc_unit_t;
typedef int adc_channel_t;
enum { ESP_OK=0, ESP_ERR_INVALID_ARG=-2, ESP_ERR_INVALID_SIZE=-3,
       ADC_UNIT_1=0, ADC_CHANNEL_1=1, ADC_ATTEN_DB_12=3, ADC_BITWIDTH_12=12,
       ADC_CONV_SINGLE_UNIT_1=1, ADC_DIGI_OUTPUT_FORMAT_TYPE2=2 };
typedef struct { unsigned max_store_buf_size, conv_frame_size;
    struct { unsigned flush_pool; } flags; } adc_continuous_handle_cfg_t;
typedef struct { unsigned atten, channel, unit, bit_width; } adc_digi_pattern_config_t;
typedef struct { unsigned pattern_num; adc_digi_pattern_config_t *adc_pattern;
    unsigned sample_freq_hz, conv_mode, format; } adc_continuous_config_t;
typedef struct { int unit_id, chan, atten, bitwidth; } adc_cali_curve_fitting_config_t;
typedef struct { uint8_t *conv_frame_buffer; uint32_t size; } adc_continuous_evt_data_t;
typedef bool (*event_cb)(adc_continuous_handle_t, const adc_continuous_evt_data_t *, void *);
typedef struct { event_cb on_conv_done, on_pool_ovf; } adc_continuous_evt_cbs_t;
int adc_continuous_flush_pool(adc_continuous_handle_t);
int adc_continuous_start(adc_continuous_handle_t);
int adc_continuous_stop(adc_continuous_handle_t);
int adc_continuous_read(adc_continuous_handle_t, uint8_t *, uint32_t, uint32_t *, uint32_t);
int adc_continuous_io_to_channel(int, adc_unit_t *, adc_channel_t *);
int adc_continuous_new_handle(const adc_continuous_handle_cfg_t *, adc_continuous_handle_t *);
int adc_continuous_config(adc_continuous_handle_t, const adc_continuous_config_t *);
int adc_continuous_register_event_callbacks(adc_continuous_handle_t, const adc_continuous_evt_cbs_t *, void *);
int adc_continuous_deinit(adc_continuous_handle_t);
int adc_cali_raw_to_voltage(adc_cali_handle_t, int, int *);
int adc_cali_create_scheme_curve_fitting(const adc_cali_curve_fitting_config_t *, adc_cali_handle_t *);
int adc_cali_delete_scheme_curve_fitting(adc_cali_handle_t);
int xPortGetCoreID(void);
TaskHandle_t xTaskGetCurrentTaskHandle(void);
int64_t esp_timer_get_time(void);
#endif
