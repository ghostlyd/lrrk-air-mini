/*
 * LiteWing brushed-motor backend for the shared PIOS_Servo interface.
 *
 * This is not an ESC/servo-pulse driver. Four low-side MOSFET gates receive
 * LEDC duty at a fixed 20 kHz carrier. PIOS_Servo_Set() stages a frame and
 * PIOS_Servo_Update() is the commit point used by the Actuator module.
 */
#include "pios.h"

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

#define LITEWING_LEDC_RESOLUTION_BITS 12u
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

static uint32_t duty_to_ledc(uint16_t duty)
{
    return ((uint32_t)duty * LITEWING_LEDC_DUTY_MAX +
            (LITEWING_ACTUATOR_MAX / 2u)) /
           LITEWING_ACTUATOR_MAX;
}

static void write_frame_locked(const struct litewing_output_frame *frame)
{
    for (uint8_t index = 0; index < LITEWING_OUTPUT_CHANNELS; ++index) {
        (void)ledc_set_duty(LEDC_LOW_SPEED_MODE, motor_channels[index],
                            duty_to_ledc(frame->duty[index]));
    }
    /* LEDC has no multi-channel commit primitive. Stage every channel first,
     * then update them in one critical section; the resulting skew is bounded
     * to four register writes and never exposes a partially validated frame. */
    for (uint8_t index = 0; index < LITEWING_OUTPUT_CHANNELS; ++index) {
        (void)ledc_update_duty(LEDC_LOW_SPEED_MODE, motor_channels[index]);
    }
}

static void force_zero_locked(void)
{
    struct litewing_output_frame safe;

    litewing_safe_frame(&safe);
    pending_frame = safe;
    write_frame_locked(&safe);
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
        return 0;
    }

    output_lock = xSemaphoreCreateMutex();
    if (output_lock == 0) {
        return -1;
    }

    const ledc_timer_config_t timer_config = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = LEDC_TIMER_12_BIT,
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

    if (xSemaphoreTake(output_lock, portMAX_DELAY) == pdTRUE) {
        force_zero_locked();
        xSemaphoreGive(output_lock);
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
    litewing_sanitize_frame(&pending_frame, &output_state, &sanitized);
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
