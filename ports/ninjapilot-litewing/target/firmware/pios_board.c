/*
 * LiteWing V2.6.C board initialization.
 *
 * This is the boundary between generic NinjaPilot flight code and the
 * repository-owned MPU6050/brushed-output adapter. The order is deliberate:
 * NVS and UAVObjects come before settings reads, and the output backend is
 * initialized before the sensor so every failure path starts at zero duty.
 */
#include "inc/openpilot.h"

#include <string.h>

#include <pios_board_info.h>
#include <pios_com_priv.h>
#include <pios_debuglog.h>
#include <pios_gcsrcvr_priv.h>
#include <pios_rcvr_priv.h>
#include <pios_esp32_priv.h>

#include <actuatorsettings.h>
#include <firmwareiapobj.h>
#include <gcsreceiver.h>
#include <manualcontrolsettings.h>
#include <mixersettings.h>
#include <systemalarms.h>
#include <taskinfo.h>
#include <uavobjectsinit.h>

#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#include "fw_version_info.h"
#include "pios_litewing_board.h"
#include "pios_litewing_brushed_pwm.h"
#include "pios_litewing_flashfs.h"
#include "litewing_settings_recovery.h"

uint32_t pios_com_telem_rf_id;
uint32_t pios_com_aux_id;
uint32_t pios_rcvr_group_map[MANUALCONTROLSETTINGS_CHANNELGROUPS_NONE];

uintptr_t pios_uavo_settings_fs_id;
uintptr_t pios_user_fs_id;
static bool board_alarms_ready;
static bool board_boot_fault;
static bool board_leds_ready;
static bool board_init_started;
static bool board_services_initialized;

const struct pios_board_info pios_board_info_blob = {
    .magic      = PIOS_BOARD_INFO_BLOB_MAGIC,
    .board_type = 0x13,
    .board_rev  = 0x02,
    .bl_rev     = 0x00,
    .hw_type    = 0x00,
    .fw_base    = 0x00010000,
    .fw_size    = 1024u * 1024u,
    .desc_base  = 0,
    .desc_size  = 0,
    .ee_base    = 0,
    .ee_size    = 0,
};

/* LiteWing V2.6.C exposes three indicator LEDs on GPIO7/8/9. Use the first
 * two for the generic PiOS heartbeat/alarm channels. Exact color semantics
 * remain a bench verification item, not a safety assumption. */
static const struct pios_esp32_led litewing_leds[] = {
    { .pin = GPIO_NUM_7, .active_low = false },
    { .pin = GPIO_NUM_8, .active_low = false },
};

const struct pios_esp32_led_cfg pios_led_cfg = {
    .leds = litewing_leds,
    .num_leds = sizeof(litewing_leds) / sizeof(litewing_leds[0]),
};

/* The schematic labels the CH340K bridge's UART0 pins TXD0/RXD0 on the S3
 * module. ESP32-S3-WROOM maps those functions to GPIO43/GPIO44. Verify the
 * assembled board on the props-off serial gate before relying on telemetry. */
const struct pios_esp32_usart_cfg pios_usart_telem_cfg = {
    .port = UART_NUM_0,
    .rx_pin = GPIO_NUM_44,
    .tx_pin = GPIO_NUM_43,
    .init_baud = 115200,
    .rx_buffer_size = 1024,
    .tx_buffer_size = 1024,
    .invert_rx = false,
};

static int board_com_init(uint32_t *com_id,
                          const struct pios_esp32_usart_cfg *usart_cfg)
{
    uint32_t usart_id;
    uint8_t *rx_buffer;
    uint8_t *tx_buffer;

    if (PIOS_ESP32_USART_Init(&usart_id, usart_cfg) != 0) {
        return -1;
    }
    rx_buffer = (uint8_t *)pios_malloc(PIOS_COM_TELEM_RF_RX_BUF_LEN);
    if (!rx_buffer) {
        return -2;
    }
    tx_buffer = (uint8_t *)pios_malloc(PIOS_COM_TELEM_RF_TX_BUF_LEN);
    if (!tx_buffer) {
        pios_free(rx_buffer);
        return -2;
    }
    int32_t result = PIOS_COM_Init(com_id, &pios_esp32_usart_com_driver, usart_id,
                                  rx_buffer, PIOS_COM_TELEM_RF_RX_BUF_LEN,
                                  tx_buffer, PIOS_COM_TELEM_RF_TX_BUF_LEN);
    if (result != 0) {
        /* At the pinned COM implementation its only reported error precedes
         * binding either buffer. Ownership transfers only on success. */
        pios_free(rx_buffer);
        pios_free(tx_buffer);
    }
    return result;
}

static UAVObjHandle board_setting_handle(unsigned index)
{
    switch (index) {
    case 0: return MixerSettingsHandle();
    case 1: return ActuatorSettingsHandle();
    case 2: return ManualControlSettingsHandle();
    default: return NULL;
    }
}

static int board_settings_inspect(void *context, unsigned index)
{
    (void)context;
    UAVObjHandle handle = board_setting_handle(index);
    if (!handle) return -1;
    return PIOS_LiteWing_FLASHFS_ObjectState(pios_uavo_settings_fs_id,
        UAVObjGetID(handle), 0, UAVObjGetNumBytes(handle));
}

static int board_settings_load(void *context, unsigned index)
{
    (void)context;
    UAVObjHandle handle = board_setting_handle(index);
    return handle ? UAVObjLoad(handle, 0) : -1;
}

static int board_defaults_and_save(void *context, unsigned index)
{
    (void)context;
    MixerSettingsData mixer;
    ActuatorSettingsData actuator;
    ManualControlSettingsData manual;

    /* Called only for a confirmed absent object. Valid stored settings are
     * loaded unchanged even when another required object is absent. */
    if (index == 0) {
        if (MixerSettingsGet(&mixer) != 0) return -1;
        mixer.ThrottleCurve1[0] = 0.0f;
        mixer.ThrottleCurve1[1] = 0.25f;
        mixer.ThrottleCurve1[2] = 0.5f;
        mixer.ThrottleCurve1[3] = 0.75f;
        mixer.ThrottleCurve1[4] = 1.0f;

        mixer.Mixer1Type = MIXERSETTINGS_MIXER1TYPE_MOTOR;
        mixer.Mixer1Vector.ThrottleCurve1 = 127;
        mixer.Mixer1Vector.Roll = 127;
        mixer.Mixer1Vector.Pitch = 127;
        mixer.Mixer1Vector.Yaw = -127;
        mixer.Mixer2Type = MIXERSETTINGS_MIXER2TYPE_MOTOR;
        mixer.Mixer2Vector.ThrottleCurve1 = 127;
        mixer.Mixer2Vector.Roll = -127;
        mixer.Mixer2Vector.Pitch = 127;
        mixer.Mixer2Vector.Yaw = 127;
        mixer.Mixer3Type = MIXERSETTINGS_MIXER3TYPE_MOTOR;
        mixer.Mixer3Vector.ThrottleCurve1 = 127;
        mixer.Mixer3Vector.Roll = -127;
        mixer.Mixer3Vector.Pitch = -127;
        mixer.Mixer3Vector.Yaw = -127;
        mixer.Mixer4Type = MIXERSETTINGS_MIXER4TYPE_MOTOR;
        mixer.Mixer4Vector.ThrottleCurve1 = 127;
        mixer.Mixer4Vector.Roll = 127;
        mixer.Mixer4Vector.Pitch = -127;
        mixer.Mixer4Vector.Yaw = 127;
        if (MixerSettingsSet(&mixer) != 0) return -1;
    } else if (index == 1) {

        /* LiteWing uses brushed duty, not 1000-2000us ESC pulses. */
        if (ActuatorSettingsGet(&actuator) != 0) return -1;
        for (uint8_t index = 0; index < 4; ++index) {
            actuator.ChannelType[index] = ACTUATORSETTINGS_CHANNELTYPE_PWM;
            actuator.ChannelAddr[index] = index;
            actuator.ChannelMin[index] = 0;
            actuator.ChannelNeutral[index] = 0;
            actuator.ChannelMax[index] = 1000;
        }
        actuator.MotorsSpinWhileArmed =
            ACTUATORSETTINGS_MOTORSSPINWHILEARMED_FALSE;
        if (ActuatorSettingsSet(&actuator) != 0) return -1;
    } else if (index == 2) {

        /* GCS is a configuration/bench input only. The ordinary controller and
         * explicit human arm path remain authoritative; no AI path is connected
         * to this receiver. */
        if (ManualControlSettingsGet(&manual) != 0) return -1;
        manual.ChannelGroups.Throttle = MANUALCONTROLSETTINGS_CHANNELGROUPS_GCS;
        manual.ChannelGroups.Roll = MANUALCONTROLSETTINGS_CHANNELGROUPS_GCS;
        manual.ChannelGroups.Pitch = MANUALCONTROLSETTINGS_CHANNELGROUPS_GCS;
        manual.ChannelGroups.Yaw = MANUALCONTROLSETTINGS_CHANNELGROUPS_GCS;
        manual.ChannelGroups.FlightMode = MANUALCONTROLSETTINGS_CHANNELGROUPS_GCS;
        manual.ChannelNumber.Throttle = 1;
        manual.ChannelNumber.Roll = 2;
        manual.ChannelNumber.Pitch = 3;
        manual.ChannelNumber.Yaw = 4;
        manual.ChannelNumber.FlightMode = 5;
        if (ManualControlSettingsSet(&manual) != 0) return -1;
    } else {
        return -1;
    }

    return UAVObjSave(board_setting_handle(index), 0);
}

static int board_settings_mark(void *context)
{
    (void)context;
    return PIOS_LiteWing_FLASHFS_MarkProvisioned();
}

static int board_apply_safe_defaults(void)
{
    static const struct litewing_settings_ops ops = {
        board_settings_inspect, board_settings_load,
        board_defaults_and_save, board_settings_mark
    };
    if (!PIOS_LiteWing_FLASHFS_Healthy()) return -1;
    return litewing_settings_recover(&ops, NULL);
}

static void board_set_boot_fault(void)
{
    board_boot_fault = true;
    /* Before PWM initialization this is a no-op: early returns and the entry
     * gate must prevent later hardware/module initialization. After PWM init,
     * Shutdown uses the existing output latch. Neither path enables outputs. */
    PIOS_LiteWing_BrushedPWM_Shutdown();
    if (board_alarms_ready) {
        AlarmsSet(SYSTEMALARMS_ALARM_BOOTFAULT, SYSTEMALARMS_ALARM_CRITICAL);
    }
    if (board_leds_ready) {
        PIOS_LED_On(PIOS_LED_ALARM);
    }
}

static int32_t board_set_firmware_identity(void)
{
    FirmwareIAPObjData iap;

    if (FirmwareIAPObjGet(&iap) != 0) {
        return -1;
    }
    iap.BoardType = pios_board_info_blob.board_type;
    iap.BoardRevision = pios_board_info_blob.board_rev;
    memset(iap.Description, 0, sizeof(iap.Description));
    memcpy(&iap.Description[0], "OpFw", 4);
    {
        uint32_t value = FW_VERSION_HASH32;
        memcpy(&iap.Description[4], &value, sizeof(value));
        value = FW_VERSION_UNIXTIME;
        memcpy(&iap.Description[8], &value, sizeof(value));
    }
    iap.Description[12] = pios_board_info_blob.board_type;
    iap.Description[13] = pios_board_info_blob.board_rev;
    strncpy((char *)&iap.Description[14], FW_VERSION_FWTAG, 25);
    memcpy(&iap.Description[60], fw_version_uavo_sha1,
           sizeof(fw_version_uavo_sha1));
    return FirmwareIAPObjSet(&iap);
}

bool PIOS_LiteWing_BoardServicesInitialized(void)
{
    /* This synchronous status is not proof of complete module/task startup.
     * In particular, it must never be used to publish BootFault OK. */
    return board_services_initialized && !board_boot_fault;
}

void PIOS_Board_Init(void)
{
    uint32_t gcs_id;
    uint32_t gcs_rcvr_id;

    /* Called only from app_main, not a concurrent reset/retry interface. A
     * failed or partial initialization cannot be retried in this boot. */
    if (board_init_started) {
        return;
    }
    board_init_started = true;
    if (PIOS_DELAY_Init() != 0) {
        board_set_boot_fault();
        return;
    }
    if (PIOS_LED_Init(&pios_led_cfg) != 0) {
        board_set_boot_fault();
        return;
    }
    board_leds_ready = true;
    PIOS_LED_On(PIOS_LED_HEARTBEAT);

    if (PIOS_TASK_MONITOR_Initialize(TASKINFO_RUNNING_NUMELEM) != 0) {
        board_set_boot_fault();
        return;
    }
    if (PIOS_CALLBACKSCHEDULER_Initialize() != 0) {
        board_set_boot_fault();
        return;
    }
    if (EventDispatcherInitialize() != 0) {
        board_set_boot_fault();
        return;
    }

    /* Settings storage must exist before registration because the real
     * persistence implementation loads settings during object registration. */
    if (PIOS_ESP32_FLASHFS_Init(&pios_uavo_settings_fs_id) != 0) {
        pios_uavo_settings_fs_id = 0;
        board_set_boot_fault();
        printf("[LiteWing] settings storage unavailable; outputs blocked\n");
        return;
    }
    pios_user_fs_id = 0;

    if (UAVObjInitialize() != 0) {
        board_set_boot_fault();
        return;
    }
    UAVObjectsInitializeAll();
    if (board_set_firmware_identity() != 0) {
        board_set_boot_fault();
        return;
    }
    if (board_apply_safe_defaults() != 0) {
        board_set_boot_fault();
        return;
    }
    PIOS_DEBUGLOG_Initialize();
    if (!SystemAlarmsHandle() || AlarmsInitialize() != 0) {
        board_set_boot_fault();
        return;
    }
    board_alarms_ready = true;
    /* Return value is previous-reset watchdog flags, not an init status.
     * Internal task/subscription success remains a separate startup gate. */
    (void)PIOS_WDG_Init();

    if (board_com_init(&pios_com_telem_rf_id, &pios_usart_telem_cfg) != 0) {
        board_set_boot_fault();
        return;
    }

    /* GCS receiver data arrives through UAVTalk; it is never an implicit arm
     * source. Map it only so a disconnected or props-off bench can exercise
     * the same control path without a physical RC protocol. */
    /* Already registered by UAVObjectsInitializeAll. Reinitializing an
     * existing generated object returns -2, not a fresh success indication. */
    if (!GCSReceiverHandle()) {
        board_set_boot_fault();
        return;
    }
    if (PIOS_GCSRCVR_Init(&gcs_id) != 0 ||
        PIOS_RCVR_Init(&gcs_rcvr_id, &pios_gcsrcvr_rcvr_driver, gcs_id) != 0) {
        board_set_boot_fault();
        return;
    } else {
        pios_rcvr_group_map[MANUALCONTROLSETTINGS_CHANNELGROUPS_GCS] =
            gcs_rcvr_id;
    }

    if (PIOS_LiteWing_Board_Init() != 0) {
        /* The target adapter has already forced zero duty before returning. */
        board_set_boot_fault();
        return;
    }
    board_services_initialized = true;
}
