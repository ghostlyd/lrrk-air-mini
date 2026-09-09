/*
 * LiteWing MPU6050 driver.
 *
 * The driver uses the standard PIOS_SENSORS queue record consumed by
 * NinjaPilot's Sensors and Attitude modules. The transport is the pinned
 * ESP32 I2C backend, and all register reads are bounded transaction calls.
 * The GPIO12 data-ready ISR only wakes the task; I2C and queue operations stay
 * out of interrupt context.
 */
#include "pios.h"

#ifdef PIOS_INCLUDE_I2C

#include <esp_err.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <driver/gpio.h>

#include <pios_constants.h>
#include <pios_sensors.h>

#include "litewing_contract.h"
#include "litewing_mpu6050_protocol.h"
#include "pios_litewing_brushed_pwm.h"
#include "pios_litewing_mpu6050.h"
#include "pios_icm20602.h"

#define LITEWING_MPU6050_REG_SMPLRT_DIV 0x19u
#define LITEWING_MPU6050_REG_CONFIG 0x1Au
#define LITEWING_MPU6050_REG_GYRO_CONFIG 0x1Bu
#define LITEWING_MPU6050_REG_ACCEL_CONFIG 0x1Cu
#define LITEWING_MPU6050_REG_INT_PIN_CFG 0x37u
#define LITEWING_MPU6050_REG_INT_ENABLE 0x38u
#define LITEWING_MPU6050_REG_ACCEL_XOUT_H 0x3Bu
#define LITEWING_MPU6050_REG_PWR_MGMT_1 0x6Bu
#define LITEWING_MPU6050_REG_WHO_AM_I 0x75u
#define LITEWING_MPU6050_RESET 0x80u
#define LITEWING_MPU6050_CLOCK_PLL_X 0x01u
#define LITEWING_MPU6050_INT_DATA_READY 0x01u
#define LITEWING_MPU6050_QUEUE_LENGTH 4u
#define LITEWING_MPU6050_STALE_TIMEOUT_MS 20u
#define LITEWING_MPU6050_SENSOR_COUNT 2u
#define LITEWING_MPU6050_DATA_SIZE \
    (sizeof(PIOS_SENSORS_3Axis_SensorsWithTemp) + \
     sizeof(Vector3i16) * LITEWING_MPU6050_SENSOR_COUNT)
#define LITEWING_MPU6050_ORIENTATION_TOP_0DEG 0u

struct litewing_mpu6050_device {
    uint32_t i2c_id;
    uint8_t address;
    uint8_t orientation;
    QueueHandle_t queue;
    TaskHandle_t task;
    volatile bool healthy;
    bool sample_seen;
    uint32_t last_sample_ms;
};

static struct litewing_mpu6050_device device;
static PIOS_SENSORS_3Axis_SensorsWithTemp *queue_data;

static bool transfer_write(uint8_t reg, uint8_t value)
{
    uint8_t buffer[2] = { reg, value };
    const struct pios_i2c_txn transaction = {
        .info = "litewing-mpu6050-write",
        .addr = device.address,
        .rw = PIOS_I2C_TXN_WRITE,
        .len = sizeof(buffer),
        .buf = buffer,
    };
    return PIOS_I2C_Transfer(device.i2c_id, &transaction, 1u) == 0;
}

static bool transfer_read(uint8_t reg, uint8_t *buffer, uint32_t length)
{
    if (buffer == 0 || length == 0u || length > 32u) {
        return false;
    }
    const struct pios_i2c_txn transactions[] = {
        {
            .info = "litewing-mpu6050-register",
            .addr = device.address,
            .rw = PIOS_I2C_TXN_WRITE,
            .len = 1u,
            .buf = &reg,
        },
        {
            .info = "litewing-mpu6050-read",
            .addr = device.address,
            .rw = PIOS_I2C_TXN_READ,
            .len = length,
            .buf = buffer,
        },
    };
    return PIOS_I2C_Transfer(device.i2c_id, transactions,
                             sizeof(transactions) / sizeof(transactions[0])) == 0;
}

static bool read_who_am_i(uint8_t *who_am_i)
{
    return who_am_i != 0 && transfer_read(LITEWING_MPU6050_REG_WHO_AM_I,
                                           who_am_i, 1u);
}

static bool configure_sensor(void)
{
    uint8_t who_am_i = 0;

    if (!read_who_am_i(&who_am_i) ||
        !litewing_mpu6050_identity_valid(who_am_i)) {
        return false;
    }
    if (!transfer_write(LITEWING_MPU6050_REG_PWR_MGMT_1,
                        LITEWING_MPU6050_RESET)) {
        return false;
    }
    vTaskDelay(pdMS_TO_TICKS(100u));
    if (!transfer_write(LITEWING_MPU6050_REG_PWR_MGMT_1,
                        LITEWING_MPU6050_CLOCK_PLL_X)) {
        return false;
    }
    vTaskDelay(pdMS_TO_TICKS(10u));

    /* 1 kHz internal rate / (1 + 1) = 500 Hz, matching PIOS_SENSOR_RATE. */
    if (!transfer_write(LITEWING_MPU6050_REG_CONFIG,
                        LITEWING_MPU6050_DLPF_CFG) ||
        !transfer_write(LITEWING_MPU6050_REG_SMPLRT_DIV,
                        LITEWING_MPU6050_SAMPLE_DIVIDER) ||
        !transfer_write(LITEWING_MPU6050_REG_GYRO_CONFIG,
                        LITEWING_MPU6050_GYRO_CONFIG) ||
        !transfer_write(LITEWING_MPU6050_REG_ACCEL_CONFIG,
                        LITEWING_MPU6050_ACCEL_CONFIG) ||
        !transfer_write(LITEWING_MPU6050_REG_INT_PIN_CFG, 0x00u) ||
        !transfer_write(LITEWING_MPU6050_REG_INT_ENABLE,
                        LITEWING_MPU6050_INT_DATA_READY)) {
        return false;
    }

    return read_who_am_i(&who_am_i) &&
           litewing_mpu6050_identity_valid(who_am_i);
}

static void orient_sample(const struct litewing_mpu6050_sample *raw,
                          PIOS_SENSORS_3Axis_SensorsWithTemp *out)
{
    /* The OP body-frame convention follows the existing MPU6000 path: chip Y
     * becomes body X, chip X becomes body Y, and body Z is inverted. Physical
     * corner/IMU orientation is still a required props-off bench gate. */
    switch (device.orientation) {
    case LITEWING_MPU6050_ORIENTATION_TOP_0DEG:
    default:
        out->sample[0].x = raw->accel[1];
        out->sample[0].y = raw->accel[0];
        out->sample[1].x = raw->gyro[1];
        out->sample[1].y = raw->gyro[0];
        break;
    }
    out->sample[0].z = (int16_t)(-1 - raw->accel[2]);
    out->sample[1].z = (int16_t)(-1 - raw->gyro[2]);
    out->temperature = (int16_t)(3653 + ((int32_t)raw->temperature * 100) / 340);
    out->count = LITEWING_MPU6050_SENSOR_COUNT;
}

static void publish_sample(const uint8_t *frame)
{
    struct litewing_mpu6050_sample raw;
    if (!litewing_mpu6050_decode_frame(frame, 14u, &raw)) {
        return;
    }

    orient_sample(&raw, queue_data);
    if (xQueueSend(device.queue, queue_data, 0) != pdTRUE) {
        uint8_t discarded[LITEWING_MPU6050_DATA_SIZE];
        (void)xQueueReceive(device.queue, discarded, 0);
        (void)xQueueSend(device.queue, queue_data, 0);
    }
}

static void set_health(bool healthy)
{
    device.healthy = healthy;
    PIOS_LiteWing_BrushedPWM_SetImuHealthy(healthy);
}

static void IRAM_ATTR data_ready_isr(void *argument)
{
    struct litewing_mpu6050_device *imu = argument;
    BaseType_t higher_priority_task_woken = pdFALSE;

    if (imu != 0 && imu->task != 0) {
        vTaskNotifyGiveFromISR(imu->task, &higher_priority_task_woken);
    }
    if (higher_priority_task_woken == pdTRUE) {
        portYIELD_FROM_ISR();
    }
}

static bool configure_data_ready(void)
{
    const gpio_config_t input = {
        .pin_bit_mask = 1ULL << LITEWING_IMU_INT_GPIO,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_POSEDGE,
    };
    if (gpio_config(&input) != ESP_OK) {
        return false;
    }

    esp_err_t rc = gpio_install_isr_service(ESP_INTR_FLAG_IRAM);
    if (rc != ESP_OK && rc != ESP_ERR_INVALID_STATE) {
        return false;
    }
    return gpio_isr_handler_add(LITEWING_IMU_INT_GPIO, data_ready_isr,
                                &device) == ESP_OK;
}

static void sensor_task(__attribute__((unused)) void *argument)
{
    uint8_t frame[14];

    for (;;) {
        const uint32_t notified = ulTaskNotifyTake(
            pdTRUE, pdMS_TO_TICKS(LITEWING_MPU6050_STALE_TIMEOUT_MS));
        const uint32_t now_ms = (uint32_t)(xTaskGetTickCount() *
                                           portTICK_PERIOD_MS);

        if (notified == 0u || !transfer_read(LITEWING_MPU6050_REG_ACCEL_XOUT_H,
                                              frame, sizeof(frame))) {
            const bool fresh = litewing_mpu6050_sample_is_fresh(
                device.sample_seen, now_ms, device.last_sample_ms,
                LITEWING_MPU6050_STALE_TIMEOUT_MS);
            set_health(fresh);
            continue;
        }

        publish_sample(frame);
        device.sample_seen = true;
        device.last_sample_ms = now_ms;
        set_health(true);
    }
}

static bool driver_test(__attribute__((unused)) uintptr_t context)
{
    uint8_t who_am_i = 0;
    const bool valid = read_who_am_i(&who_am_i) &&
                       litewing_mpu6050_identity_valid(who_am_i);
    if (!valid) {
        set_health(false);
    }
    return valid;
}

static void driver_reset(__attribute__((unused)) uintptr_t context)
{
    set_health(false);
    (void)configure_sensor();
}

static QueueHandle_t driver_get_queue(__attribute__((unused)) uintptr_t context)
{
    return device.queue;
}

static void driver_get_scale(float *scales, uint8_t size,
                             __attribute__((unused)) uintptr_t context)
{
    PIOS_Assert(scales != 0 && size >= 2u);
    /* +/-2g accelerometer and +/-2000 deg/s gyro. */
    scales[0] = PIOS_CONST_MKS_GRAV_ACCEL_F / 16384.0f;
    scales[1] = 1.0f / 16.4f;
}

const PIOS_SENSORS_Driver PIOS_ICM20602_Driver = {
    .test = driver_test,
    .poll = NULL,
    .fetch = NULL,
    .reset = driver_reset,
    .get_queue = driver_get_queue,
    .get_scale = driver_get_scale,
    .is_polled = false,
};

int32_t PIOS_LiteWing_MPU6050_Init(uint32_t i2c_id, uint8_t address)
{
    /* The pinned ESP32 backend uses slot 0 for its first (I2C0) bus. Zero is
     * therefore a valid handle, not an uninitialized sentinel. */
    if (address > 0x7Fu || device.queue != 0) {
        return -1;
    }

    device.i2c_id = i2c_id;
    device.address = address;
    device.orientation = LITEWING_MPU6050_ORIENTATION_TOP_0DEG;
    device.healthy = false;
    device.sample_seen = false;
    device.last_sample_ms = 0;

    if (!PIOS_ESP32_I2C_Probe(i2c_id, address) || !configure_sensor()) {
        set_health(false);
        return -2;
    }

    device.queue = xQueueCreate(LITEWING_MPU6050_QUEUE_LENGTH,
                                LITEWING_MPU6050_DATA_SIZE);
    if (device.queue == 0) {
        set_health(false);
        return -3;
    }
    queue_data = pios_malloc(LITEWING_MPU6050_DATA_SIZE);
    if (queue_data == 0) {
        vQueueDelete(device.queue);
        device.queue = 0;
        set_health(false);
        return -4;
    }

    if (PIOS_SENSORS_Register(&PIOS_ICM20602_Driver,
                              PIOS_SENSORS_TYPE_3AXIS_GYRO_ACCEL,
                              (uintptr_t)&device) == 0) {
        set_health(false);
        return -5;
    }

    if (!configure_data_ready() ||
        xTaskCreate(sensor_task, "LWMPU6050",
                    1024u, 0, tskIDLE_PRIORITY + 4u,
                    &device.task) != pdPASS) {
        set_health(false);
        return -6;
    }

    /* Keep the output gate closed until the first valid data-ready sample. */
    set_health(false);
    return 0;
}

bool PIOS_LiteWing_MPU6050_IsHealthy(void)
{
    return device.healthy;
}

void PIOS_LiteWing_MPU6050_Shutdown(void)
{
    set_health(false);
}

#endif /* PIOS_INCLUDE_I2C */
