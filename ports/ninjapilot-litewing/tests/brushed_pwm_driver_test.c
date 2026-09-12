/* Execute the production driver with only ESP-IDF/RTOS/UAVObject seams faked.
 * Each process runs one scenario so production static state is never reset
 * through a test-only API. This is not an electrical or scheduling simulator. */
#include <setjmp.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pios.h"
#include "driver/ledc.h"
#include "esp_timer.h"
#include "flightstatus.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "pios_litewing_brushed_pwm.h"

#define CHECK(test) do { if (!(test)) { \
    fprintf(stderr, "line %d: %s\n", __LINE__, #test); exit(1); \
} } while (0)

static uint32_t staged[4], active[4], max_duty, staged_mask;
static unsigned stop_mask, updates;
static int fail_set = -1, fail_update = -1, fail_stop = -1;
static bool fail_task, locked;
static uint8_t armed;
static int mutex_token;
static int64_t now_us = 1000;
static TaskFunction_t watchdog;
static jmp_buf watchdog_return;
static int delays;

SemaphoreHandle_t xSemaphoreCreateMutex(void) { return &mutex_token; }
BaseType_t xSemaphoreTake(SemaphoreHandle_t lock, TickType_t ticks)
{
    if (lock == &mutex_token && locked && ticks == 0) return 0;
    CHECK(lock == &mutex_token && !locked);
    locked = true;
    return pdTRUE;
}
BaseType_t xSemaphoreGive(SemaphoreHandle_t lock)
{
    CHECK(lock == &mutex_token && locked);
    locked = false;
    return pdTRUE;
}
void vSemaphoreDelete(SemaphoreHandle_t lock) { CHECK(lock == &mutex_token && !locked); }
BaseType_t xTaskCreate(TaskFunction_t task, const char *name, uint32_t stack,
                      void *arg, UBaseType_t priority, TaskHandle_t *handle)
{
    (void)name; (void)stack; (void)arg; (void)priority; (void)handle;
    if (fail_task) { return 0; }
    watchdog = task;
    return pdPASS;
}
void vTaskDelay(TickType_t ticks)
{
    CHECK(ticks > 0);
    if (delays++ > 0) { longjmp(watchdog_return, 1); }
}
int64_t esp_timer_get_time(void) { return now_us; }
void FlightStatusArmedGet(uint8_t *value) { *value = armed; }

esp_err_t ledc_timer_config(const ledc_timer_config_t *config)
{
    CHECK(config->speed_mode == LEDC_LOW_SPEED_MODE && config->freq_hz == 20000);
    /* ESP32-S3 LEDC sources top out at 80 MHz; divider must be >= 1.
     * See the pinned ESP-IDF 5.3.2 LEDC clock table/divisor calculation. */
    uint64_t required_clock = (uint64_t)config->freq_hz << config->duty_resolution;
    if (required_clock > 80000000) { return ESP_FAIL; }
    max_duty = (1u << config->duty_resolution) - 1;
    return ESP_OK;
}
esp_err_t ledc_channel_config(const ledc_channel_config_t *config)
{
    const int pins[4] = {5, 6, 3, 4};
    CHECK(config->channel < 4 && max_duty > 0);
    CHECK(config->gpio_num == pins[config->channel]);
    CHECK(config->duty == 0 && !config->flags.output_invert);
    staged[config->channel] = active[config->channel] = config->duty;
    return ESP_OK;
}
esp_err_t ledc_set_duty(ledc_mode_t mode, ledc_channel_t channel, uint32_t duty)
{
    CHECK(locked && mode == LEDC_LOW_SPEED_MODE && channel < 4 && duty <= max_duty);
    if ((int)channel == fail_set) { return ESP_FAIL; }
    staged[channel] = duty;
    staged_mask |= 1u << channel;
    return ESP_OK;
}
esp_err_t ledc_update_duty(ledc_mode_t mode, ledc_channel_t channel)
{
    CHECK(locked && mode == LEDC_LOW_SPEED_MODE && channel < 4);
    CHECK(staged_mask == 15); /* No commit before all channels stage successfully. */
    if ((int)channel == fail_update) { return ESP_FAIL; }
    active[channel] = staged[channel];
    updates++;
    if (channel == 3) { staged_mask = 0; }
    return ESP_OK;
}
esp_err_t ledc_stop(ledc_mode_t mode, ledc_channel_t channel, uint32_t idle_level)
{
    CHECK(locked && mode == LEDC_LOW_SPEED_MODE && channel < 4 && idle_level == 0);
    stop_mask |= 1u << channel;
    staged_mask = 0;
    if ((int)channel == fail_stop) { return ESP_FAIL; }
    active[channel] = 0;
    return ESP_OK;
}

static void expect_all(uint32_t expected)
{
    for (int index = 0; index < 4; ++index) { CHECK(active[index] == expected); }
}
static void stage_all(uint16_t value)
{
    for (int index = 0; index < 4; ++index) { PIOS_Servo_Set(index, value); }
}
static void start_running(void)
{
    CHECK(PIOS_LiteWing_BrushedPWM_Init() == 0);
    expect_all(0);
    PIOS_LiteWing_BrushedPWM_SetImuHealthy(true);
    armed = FLIGHTSTATUS_ARMED_ARMED;
    stage_all(500);
    PIOS_Servo_Update();
    expect_all(1024);
}
static void watchdog_once(void)
{
    CHECK(watchdog != NULL);
    delays = 0;
    if (setjmp(watchdog_return) == 0) { watchdog(NULL); }
    CHECK(!locked);
}
static void verify_fault_stays_latched(void)
{
    unsigned prior_updates = updates;
    fail_set = fail_update = fail_stop = -1;
    PIOS_LiteWing_BrushedPWM_SetImuHealthy(true);
    PIOS_LiteWing_BrushedPWM_SetFailsafe(false);
    stage_all(1000);
    PIOS_Servo_Update();
    expect_all(0);
    CHECK(updates == prior_updates); /* Updating LEDC would re-enable stopped outputs. */
    CHECK(PIOS_LiteWing_BrushedPWM_Init() != 0);
}

int main(int argc, char **argv)
{
    CHECK(argc >= 2);
    const char *scenario = argv[1];
    int channel = argc > 2 ? atoi(argv[2]) : 0;
    CHECK(channel >= 0 && channel < 4);
    if (strncmp(scenario, "bench-", 6) == 0) {
        CHECK(PIOS_LiteWing_BrushedPWM_Init() == 0);
        /* Suppressed demand and long zero-output waits must not consume
         * the one-shot interval. Test the real Update/sanitizer path. */
        stage_all(1000);
        PIOS_Servo_Update();
        now_us = 5000000;
        PIOS_LiteWing_BrushedPWM_SetImuHealthy(true);
        armed = FLIGHTSTATUS_ARMED_ARMED;
        stage_all(0);
        PIOS_Servo_Update();
        now_us = 9000000;
        const uint16_t demand[4] = {0, 1000, 80, 737};
        for (int i = 0; i < 4; ++i) PIOS_Servo_Set(i, demand[i]);
        PIOS_Servo_Update();
        CHECK(active[0] == 0 && active[1] == 409 &&
              active[2] == 164 && active[3] == 409);
        struct litewing_pwm_observation observed;
        CHECK(PIOS_LiteWing_BrushedPWM_GetObservation(&observed));
        CHECK(observed.requested[1] == 1000 && observed.submitted[1] == 409);
        if (strcmp(scenario, "bench-cap") == 0 ||
            strcmp(scenario, "bench-start") == 0) return 0;
        if (strcmp(scenario, "bench-interruption") == 0 ||
            strcmp(scenario, "bench-imu") == 0 ||
            strcmp(scenario, "bench-failsafe") == 0) {
            now_us = 9500000;
            if (strcmp(scenario, "bench-imu") == 0)
                PIOS_LiteWing_BrushedPWM_SetImuHealthy(false);
            else if (strcmp(scenario, "bench-failsafe") == 0)
                PIOS_LiteWing_BrushedPWM_SetFailsafe(true);
            else {
                stage_all(0);
                PIOS_Servo_Update();
                expect_all(0);
                armed = FLIGHTSTATUS_ARMED_DISARMED;
            }
            stage_all(1000);
            PIOS_Servo_Update();
            expect_all(0);
            now_us = 9750000;
            armed = FLIGHTSTATUS_ARMED_ARMED;
            PIOS_LiteWing_BrushedPWM_SetImuHealthy(true);
            PIOS_LiteWing_BrushedPWM_SetFailsafe(false);
            stage_all(1000);
            PIOS_Servo_Update();
            expect_all(409);
        }
        now_us = 9999999;
        stage_all(1000);
        PIOS_Servo_Update();
        expect_all(409);
        now_us = 10000000;
        if (strcmp(scenario, "bench-expiry-set-failure") == 0) fail_set = channel;
        if (strcmp(scenario, "bench-expiry-update-failure") == 0) fail_update = channel;
        if (strcmp(scenario, "bench-expiry-stop-failure") == 0) {
            fail_set = channel;
            fail_stop = channel;
        }
        if (strcmp(scenario, "bench-watchdog") == 0) watchdog_once();
        else PIOS_Servo_Update();
        if (strcmp(scenario, "bench-expiry-stop-failure") == 0) {
            CHECK(stop_mask == 15);
            CHECK(PIOS_LiteWing_BrushedPWM_GetObservation(&observed));
            CHECK(!(observed.known_mask & (1u << channel)));
            CHECK(observed.write_errors == 1 && observed.stop_errors == 1);
            for (int i = 0; i < 4; ++i) if (i != channel) CHECK(active[i] == 0);
            verify_fault_stays_latched();
            return 0;
        }
        expect_all(0);
        if (strncmp(scenario, "bench-expiry-", 13) == 0) {
            CHECK(stop_mask == 15);
            verify_fault_stays_latched();
        }
        CHECK(PIOS_LiteWing_BrushedPWM_GetObservation(&observed));
        CHECK(observed.suppression & LITEWING_PWM_SUPPRESS_SHUTDOWN);
        if (strcmp(scenario, "bench-latch") == 0) {
            armed = FLIGHTSTATUS_ARMED_DISARMED;
            PIOS_Servo_Update();
            armed = FLIGHTSTATUS_ARMED_ARMED;
            PIOS_LiteWing_BrushedPWM_SetFailsafe(false);
            PIOS_LiteWing_BrushedPWM_SetImuHealthy(true);
            CHECK(PIOS_LiteWing_BrushedPWM_Init() != 0);
            stage_all(1000);
            PIOS_Servo_Update();
            expect_all(0);
        }
        return 0;
    }
    if (strcmp(scenario, "init-write-failure") == 0 || strcmp(scenario, "init-update-failure") == 0) {
        if (strcmp(scenario, "init-write-failure") == 0) { fail_set = channel; }
        else { fail_update = channel; }
        CHECK(PIOS_LiteWing_BrushedPWM_Init() != 0);
        CHECK(stop_mask == 15);
        verify_fault_stays_latched();
        return 0;
    }
    if (strcmp(scenario, "watchdog-create-failure") == 0) {
        fail_task = true;
        CHECK(PIOS_LiteWing_BrushedPWM_Init() == -4);
        CHECK(PIOS_LiteWing_BrushedPWM_Init() != 0);
        PIOS_LiteWing_BrushedPWM_SetImuHealthy(true);
        armed = FLIGHTSTATUS_ARMED_ARMED;
        stage_all(1000);
        PIOS_Servo_Update();
        expect_all(0);
        return 0;
    }
    if (strcmp(scenario, "observation") == 0) {
        struct litewing_pwm_observation observation;
        CHECK(!PIOS_LiteWing_BrushedPWM_GetObservation(NULL));
        CHECK(!PIOS_LiteWing_BrushedPWM_GetObservation(&observation));
        start_running();
        unsigned before = updates;
        CHECK(PIOS_LiteWing_BrushedPWM_GetObservation(&observation));
        CHECK(updates == before);
        CHECK(observation.suppression == 0 && observation.known_mask == 15);
        CHECK(observation.commits == 2 && observation.write_errors == 0);
        CHECK(observation.requested[0] == 500 && observation.submitted[0] == 1024);
        locked = true;
        observation.commits = 12345;
        CHECK(!PIOS_LiteWing_BrushedPWM_GetObservation(&observation));
        CHECK(locked && observation.commits == 12345 && updates == before);
        locked = false;
        stage_all(250);
        CHECK(PIOS_LiteWing_BrushedPWM_GetObservation(&observation));
        CHECK(observation.requested[0] == 500 && observation.submitted[0] == 1024);
        PIOS_LiteWing_BrushedPWM_SetImuHealthy(false);
        CHECK(PIOS_LiteWing_BrushedPWM_GetObservation(&observation));
        CHECK(observation.suppression & LITEWING_PWM_SUPPRESS_IMU);
        CHECK(observation.requested[0] == 500 && observation.submitted[0] == 0);
        CHECK(observation.known_mask == 15);
        return 0;
    }
    if (strcmp(scenario, "observation-failure") == 0) {
        struct litewing_pwm_observation observation;
        start_running();
        fail_update = 1; fail_stop = 2;
        stage_all(250); PIOS_Servo_Update();
        CHECK(PIOS_LiteWing_BrushedPWM_GetObservation(&observation));
        CHECK(observation.write_errors == 1 && observation.stop_errors == 1);
        CHECK(observation.known_mask == 11);
        CHECK(observation.suppression & LITEWING_PWM_SUPPRESS_HARDWARE);
        CHECK(observation.requested[0] == 250);
        CHECK(observation.submitted[0] == 0);
        return 0;
    }
    start_running();
    if (strcmp(scenario, "duty") == 0) {
        stage_all(65000);
        expect_all(1024); /* Staging is not a hardware commit. */
        PIOS_Servo_Set(255, 0); /* Invalid channel must not affect any output. */
        PIOS_Servo_Update();
        expect_all(2047);
        stage_all(0);
        PIOS_Servo_Update();
        expect_all(0);
    } else if (strcmp(scenario, "disarm") == 0) {
        armed = FLIGHTSTATUS_ARMED_DISARMED;
        PIOS_Servo_Update();
        expect_all(0);
    } else if (strcmp(scenario, "imu") == 0) {
        PIOS_LiteWing_BrushedPWM_SetImuHealthy(false);
        expect_all(0);
        stage_all(1000);
        PIOS_Servo_Update();
        expect_all(0);
    } else if (strcmp(scenario, "failsafe") == 0) {
        PIOS_LiteWing_BrushedPWM_SetFailsafe(true);
        expect_all(0);
        stage_all(1000);
        PIOS_Servo_Update();
        expect_all(0);
    } else if (strcmp(scenario, "shutdown") == 0) {
        PIOS_LiteWing_BrushedPWM_Shutdown();
        expect_all(0);
        stage_all(1000);
        PIOS_Servo_Update();
        expect_all(0);
    } else if (strcmp(scenario, "watchdog") == 0) {
        now_us = 101000; /* Exactly 100 ms after update: not yet stale. */
        watchdog_once();
        expect_all(1024);
        now_us++;
        watchdog_once();
        expect_all(0);
    } else if (strcmp(scenario, "set-failure") == 0 || strcmp(scenario, "stop-failure") == 0) {
        fail_set = channel;
        if (strcmp(scenario, "stop-failure") == 0) { fail_stop = channel; }
        stage_all(1000);
        PIOS_Servo_Update();
        CHECK(stop_mask == 15); /* Attempt every stop even if one stop fails. */
        for (int index = 0; index < 4; ++index) {
            if (index != fail_stop) { CHECK(active[index] == 0); }
        }
        verify_fault_stays_latched();
    } else if (strcmp(scenario, "update-failure") == 0) {
        fail_update = channel;
        stage_all(1000);
        PIOS_Servo_Update();
        CHECK(stop_mask == 15);
        expect_all(0);
        verify_fault_stays_latched();
    } else {
        CHECK(false);
    }
    return 0;
}
