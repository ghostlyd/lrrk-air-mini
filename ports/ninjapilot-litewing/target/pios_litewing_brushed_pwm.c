/*
 * LiteWing brushed-motor backend for the shared PIOS_Servo interface.
 *
 * This is not an ESC/servo-pulse driver. Four low-side MOSFET gates receive
 * LEDC duty at a fixed 20 kHz carrier. PIOS_Servo_Set() stages a frame and
 * PIOS_Servo_Update() is the commit point used by the Actuator module.
 */
#include "pios.h"
#ifdef ESP_PLATFORM
#include "sdkconfig.h"
#endif

#ifdef PIOS_INCLUDE_SERVO

#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/task.h>
#include <driver/ledc.h>

#include <uavobjectmanager.h>
#include <flightstatus.h>

#include "litewing_contract.h"
#include "pios_litewing_brushed_pwm.h"

/* 20 kHz * 2^12 exceeds the ESP32-S3's fastest LEDC source (80 MHz).
 * Eleven bits retains more hardware steps than the 0..1000 actuator range. */
#define LITEWING_LEDC_RESOLUTION_BITS 11u
#define LITEWING_LEDC_DUTY_MAX ((1u << LITEWING_LEDC_RESOLUTION_BITS) - 1u)
#define LITEWING_OUTPUT_WATCHDOG_MS 100u
#define LITEWING_OUTPUT_WATCHDOG_PERIOD_MS 20u
#define LITEWING_OUTPUT_WATCHDOG_STACK_WORDS 768u
#define LITEWING_OUTPUT_WATCHDOG_PRIORITY (tskIDLE_PRIORITY + 2u)

static const uint8_t motor_pins[LITEWING_OUTPUT_CHANNELS] = {
    LITEWING_MOTOR_GPIO_1,
    LITEWING_MOTOR_GPIO_2,
    LITEWING_MOTOR_GPIO_3,
    LITEWING_MOTOR_GPIO_4,
};

static const ledc_channel_t motor_channels[LITEWING_OUTPUT_CHANNELS] = {
    LEDC_CHANNEL_0,
    LEDC_CHANNEL_1,
    LEDC_CHANNEL_2,
    LEDC_CHANNEL_3,
};

static SemaphoreHandle_t output_lock;
static struct litewing_output_frame pending_frame;
static struct litewing_output_state output_state;
static volatile bool output_ready;
static int64_t last_update_us;
static struct litewing_pwm_observation observation;
#if CONFIG_LRRK_BENCH_FIXED_ALL && (!CONFIG_LRRK_BENCH_OUTPUT_LIMIT || CONFIG_LRRK_BENCH_SINGLE_MOTOR)
#error "Fixed-all diagnostic requires bench limit and excludes single-motor mode"
#endif
#if CONFIG_LRRK_BENCH_SINGLE_MOTOR && !CONFIG_LRRK_BENCH_OUTPUT_LIMIT
#error "Single-motor diagnostic requires the bench output limit"
#endif
#if CONFIG_LRRK_BENCH_SINGLE_MOTOR
#ifndef CONFIG_LRRK_BENCH_MOTOR_CHANNEL
#define CONFIG_LRRK_BENCH_MOTOR_CHANNEL 1
#endif
#if CONFIG_LRRK_BENCH_MOTOR_CHANNEL < 1 || CONFIG_LRRK_BENCH_MOTOR_CHANNEL > 4
#error "Bench motor channel must be 1 through 4"
#endif
#endif
#if CONFIG_LRRK_BENCH_OUTPUT_LIMIT
#ifndef CONFIG_LRRK_BENCH_OUTPUT_DURATION_MS
#define CONFIG_LRRK_BENCH_OUTPUT_DURATION_MS 1000
#endif
#if CONFIG_LRRK_BENCH_OUTPUT_DURATION_MS < 1000 || CONFIG_LRRK_BENCH_OUTPUT_DURATION_MS > 10000
#error "Bench output duration must be between 1000 and 10000 ms"
#endif
/* One interval per boot, starting only at the first eligible nonzero frame.
 * Zero commands, rearming and fresh packets never renew this interval. */
static bool bench_started;
static int64_t bench_start_us;

static bool bench_expired_locked(int64_t now_us)
{
    if (bench_started && now_us - bench_start_us >=
        (int64_t)CONFIG_LRRK_BENCH_OUTPUT_DURATION_MS * 1000) {
        output_state.shutdown = true;
        return true;
    }
    return false;
}
#endif

static void increment_counter(uint32_t *value)
{
    if (*value != UINT32_MAX) ++*value;
}

bool PIOS_LiteWing_BrushedPWM_GetObservation(struct litewing_pwm_observation *out)
{
    if (!out || !output_ready || !output_lock ||
        xSemaphoreTake(output_lock, 0) != pdTRUE) return false;
    *out = observation;
    out->suppression =
        (!output_state.hardware_ready ? LITEWING_PWM_SUPPRESS_HARDWARE : 0) |
        (!output_state.imu_healthy ? LITEWING_PWM_SUPPRESS_IMU : 0) |
        (!output_state.link_fresh ? LITEWING_PWM_SUPPRESS_LINK : 0) |
        (!output_state.armed ? LITEWING_PWM_SUPPRESS_DISARMED : 0) |
        (output_state.failsafe ? LITEWING_PWM_SUPPRESS_FAILSAFE : 0) |
        (output_state.shutdown ? LITEWING_PWM_SUPPRESS_SHUTDOWN : 0);
    out->observed_us = esp_timer_get_time();
    xSemaphoreGive(output_lock);
    return true;
}

static uint32_t duty_to_ledc(uint16_t duty)
{
    return ((uint32_t)duty * LITEWING_LEDC_DUTY_MAX +
            (LITEWING_ACTUATOR_MAX / 2u)) /
           LITEWING_ACTUATOR_MAX;
}

static void stop_outputs_locked(void)
{
    /* Latch until reboot. A later update_duty would re-enable a stopped
     * channel, so recovery must never be inferred from fresh control data. */
    output_state.hardware_ready = false;
    output_state.link_fresh = false;
    litewing_safe_frame(&pending_frame);
    for (uint8_t index = 0; index < LITEWING_OUTPUT_CHANNELS; ++index) {
        /* Best effort on every channel even when an earlier stop fails.
         * Software cannot guarantee electrical low if the peripheral fails. */
        if (ledc_stop(LEDC_LOW_SPEED_MODE, motor_channels[index], 0) == ESP_OK) {
            observation.submitted[index] = 0;
            observation.known_mask |= (1u << index);
        } else {
            observation.known_mask &= ~(1u << index);
            increment_counter(&observation.stop_errors);
        }
    }
}

static bool write_frame_locked(const struct litewing_output_frame *frame)
{
    if (!output_state.hardware_ready) {
        stop_outputs_locked();
        return false;
    }
    for (uint8_t index = 0; index < LITEWING_OUTPUT_CHANNELS; ++index) {
        if (ledc_set_duty(LEDC_LOW_SPEED_MODE, motor_channels[index],
                          duty_to_ledc(frame->duty[index])) != ESP_OK) {
            observation.known_mask &= ~(1u << index);
            increment_counter(&observation.write_errors);
            stop_outputs_locked();
            return false;
        }
    }
    /* LEDC has no multi-channel commit primitive. Stage every channel first,
     * then update under the mutex. This is not an atomic cross-channel commit
     * or a measured timing guarantee; each change takes effect on a PWM cycle. */
    for (uint8_t index = 0; index < LITEWING_OUTPUT_CHANNELS; ++index) {
        if (ledc_update_duty(LEDC_LOW_SPEED_MODE, motor_channels[index]) != ESP_OK) {
            observation.known_mask &= ~(1u << index);
            increment_counter(&observation.write_errors);
            stop_outputs_locked();
            return false;
        }
        observation.submitted[index] = duty_to_ledc(frame->duty[index]);
        observation.known_mask |= (1u << index);
    }
    increment_counter(&observation.commits);
    return true;
}

static bool force_zero_locked(void)
{
    struct litewing_output_frame safe;

    litewing_safe_frame(&safe);
    pending_frame = safe;
    return write_frame_locked(&safe);
}

static void output_watchdog_task(__attribute__((unused)) void *argument)
{
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(LITEWING_OUTPUT_WATCHDOG_PERIOD_MS));

        if (!output_ready || output_lock == 0) {
            continue;
        }

        if (xSemaphoreTake(output_lock, portMAX_DELAY) == pdTRUE) {
            const int64_t now_us = esp_timer_get_time();
#if CONFIG_LRRK_BENCH_OUTPUT_LIMIT
            if (bench_expired_locked(now_us)) force_zero_locked();
#endif
            const bool stale = last_update_us == 0 ||
                               now_us - last_update_us >
                                   ((int64_t)LITEWING_OUTPUT_WATCHDOG_MS * 1000);
            if (stale) {
                output_state.link_fresh = false;
                force_zero_locked();
            }
            xSemaphoreGive(output_lock);
        }
    }
}

int32_t PIOS_LiteWing_BrushedPWM_Init(void)
{
    if (output_ready) {
        return output_state.hardware_ready && !output_state.shutdown ? 0 : -5;
    }

    output_lock = xSemaphoreCreateMutex();
    if (output_lock == 0) {
        return -1;
    }

    const ledc_timer_config_t timer_config = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = LEDC_TIMER_11_BIT,
        .timer_num = LEDC_TIMER_0,
        .freq_hz = LITEWING_PWM_HZ,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    if (ledc_timer_config(&timer_config) != ESP_OK) {
        vSemaphoreDelete(output_lock);
        output_lock = 0;
        return -2;
    }

    for (uint8_t index = 0; index < LITEWING_OUTPUT_CHANNELS; ++index) {
        const ledc_channel_config_t channel_config = {
            .gpio_num = motor_pins[index],
            .speed_mode = LEDC_LOW_SPEED_MODE,
            .channel = motor_channels[index],
            .intr_type = LEDC_INTR_DISABLE,
            .timer_sel = LEDC_TIMER_0,
            .duty = 0,
            .hpoint = 0,
            .flags = { .output_invert = 0 },
        };
        if (ledc_channel_config(&channel_config) != ESP_OK) {
            vSemaphoreDelete(output_lock);
            output_lock = 0;
            return -3;
        }
    }

    litewing_safe_frame(&pending_frame);
    output_state = (struct litewing_output_state){
        .hardware_ready = true,
        .imu_healthy = false,
        .link_fresh = false,
        .armed = false,
        .failsafe = false,
        .shutdown = false,
    };
    output_ready = true;
    last_update_us = 0;

    bool zero_written = false;
    if (xSemaphoreTake(output_lock, portMAX_DELAY) == pdTRUE) {
        zero_written = force_zero_locked();
        xSemaphoreGive(output_lock);
    }
    if (!zero_written) {
        output_state.hardware_ready = false;
        return -5;
    }

    if (xTaskCreate(output_watchdog_task, "LWOutWdog",
                    LITEWING_OUTPUT_WATCHDOG_STACK_WORDS, 0,
                    LITEWING_OUTPUT_WATCHDOG_PRIORITY, 0) != pdPASS) {
        PIOS_LiteWing_BrushedPWM_Shutdown();
        return -4;
    }
    return 0;
}

void PIOS_LiteWing_BrushedPWM_SetImuHealthy(bool healthy)
{
    if (!output_ready || output_lock == 0 ||
        xSemaphoreTake(output_lock, portMAX_DELAY) != pdTRUE) {
        return;
    }

    output_state.imu_healthy = healthy;
    if (!healthy) {
        output_state.link_fresh = false;
        force_zero_locked();
    }
    xSemaphoreGive(output_lock);
}

void PIOS_LiteWing_BrushedPWM_SetFailsafe(bool failsafe)
{
    if (!output_ready || output_lock == 0 ||
        xSemaphoreTake(output_lock, portMAX_DELAY) != pdTRUE) {
        return;
    }

    output_state.failsafe = failsafe;
    if (failsafe) {
        force_zero_locked();
    }
    xSemaphoreGive(output_lock);
}

void PIOS_LiteWing_BrushedPWM_Shutdown(void)
{
    if (!output_ready || output_lock == 0 ||
        xSemaphoreTake(output_lock, portMAX_DELAY) != pdTRUE) {
        return;
    }

    output_state.shutdown = true;
    output_state.link_fresh = false;
    force_zero_locked();
    xSemaphoreGive(output_lock);
}

void PIOS_Servo_SetHz(const uint16_t *speeds,
                      const uint32_t *clock,
                      uint8_t banks)
{
    (void)speeds;
    (void)clock;
    (void)banks;
    /* The LiteWing carrier is a board contract, not a runtime servo setting. */
}

void PIOS_Servo_Set(uint8_t servo, uint16_t position)
{
    if (!output_ready || servo >= LITEWING_OUTPUT_CHANNELS || output_lock == 0) {
        return;
    }
    if (xSemaphoreTake(output_lock, portMAX_DELAY) == pdTRUE) {
        pending_frame.duty[servo] = litewing_clamp_duty(position);
        xSemaphoreGive(output_lock);
    }
}

void PIOS_Servo_Update(void)
{
    if (!output_ready || output_lock == 0 ||
        xSemaphoreTake(output_lock, portMAX_DELAY) != pdTRUE) {
        return;
    }

    uint8_t armed = FLIGHTSTATUS_ARMED_DISARMED;
    FlightStatusArmedGet(&armed);
    output_state.armed = armed == FLIGHTSTATUS_ARMED_ARMED;
    output_state.link_fresh = true;

    struct litewing_output_frame sanitized;
#if CONFIG_LRRK_BENCH_OUTPUT_LIMIT
    const int64_t now_us = esp_timer_get_time();
    bench_expired_locked(now_us);
#endif
    for (uint8_t index = 0; index < LITEWING_OUTPUT_CHANNELS; ++index)
        observation.requested[index] = pending_frame.duty[index];
    litewing_sanitize_frame(&pending_frame, &output_state, &sanitized);
#if CONFIG_LRRK_BENCH_OUTPUT_LIMIT
#if CONFIG_LRRK_BENCH_SINGLE_MOTOR || CONFIG_LRRK_BENCH_FIXED_ALL
    /* Opt-in props-off diagnostic: remove mixer variation from the applied
     * output, not from sensor data. Sanitized zero/fault demand stays zero. */
    bool demand_present = false;
    for (uint8_t index = 0; index < LITEWING_OUTPUT_CHANNELS; ++index)
        demand_present |= sanitized.duty[index] != 0;
    litewing_safe_frame(&sanitized);
    if (demand_present) {
#if CONFIG_LRRK_BENCH_FIXED_ALL
        for (uint8_t index = 0; index < LITEWING_OUTPUT_CHANNELS; ++index)
            sanitized.duty[index] = 200u;
#else
        sanitized.duty[CONFIG_LRRK_BENCH_MOTOR_CHANNEL - 1] = 200u;
#endif
    }
#endif
    for (uint8_t index = 0; index < LITEWING_OUTPUT_CHANNELS; ++index) {
        if (sanitized.duty[index] > 200u) sanitized.duty[index] = 200u;
        if (sanitized.duty[index] && !bench_started) {
            bench_started = true;
            bench_start_us = now_us;
        }
    }
#endif
    write_frame_locked(&sanitized);
    last_update_us = esp_timer_get_time();
    xSemaphoreGive(output_lock);
}

void PIOS_Servo_SetBankMode(uint8_t bank, uint8_t mode)
{
    (void)bank;
    (void)mode;
    /* Brushed channels share one fixed LEDC carrier. */
}

uint8_t PIOS_Servo_GetPinBank(uint8_t pin)
{
    (void)pin;
    return 0;
}

#endif /* PIOS_INCLUDE_SERVO */
