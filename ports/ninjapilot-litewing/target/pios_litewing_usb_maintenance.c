/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "pios.h"
#include "uavobjectmanager.h"
#include "litewing_arming_maintenance.h"
#include "pios_litewing_usb_maintenance.h"
#include "pios_litewing_gcsrcvr.h"
#include "pios_litewing_wifi_command.h"
#include "litewing_wifi_config.h"
#include "litewing_wifi_store.h"
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <esp_timer.h>
#include <string.h>

enum phase { UNAVAILABLE=0, IDLE=1, QUEUED=2, WAIT_STOP=3,
             STORING=4, CLEANUP_BLOCKED=5, FINISHED=6 };
enum { NOT_ATTEMPTED=0, INVALID=1, NOT_WRITTEN=2, UNCERTAIN=3, VERIFIED=4 };
static portMUX_TYPE lock=portMUX_INITIALIZER_UNLOCKED;
static TaskHandle_t task;
static int launching;
static uint8_t phase, result, transaction[16], pending[LW_WIFI_CONFIG_SIZE];

static void wipe(void *data, size_t size)
{
    volatile uint8_t *p=data;
    while (size--) *p++=0;
}

static void set_phase(uint8_t value)
{
    portENTER_CRITICAL(&lock);
    phase=value;
    portEXIT_CRITICAL(&lock);
}

static void delay_ms(unsigned ms)
{
    TickType_t ticks=pdMS_TO_TICKS(ms);
    vTaskDelay(ticks ? ticks : 1);
}

static int within_deadline(int64_t start, int64_t *previous)
{
    const int64_t now=esp_timer_get_time();
    if (start<0 || now<*previous || now-start>=INT64_C(2000000)) return 0;
    *previous=now;
    return 1;
}

static int stop_and_wait(uint64_t token, uint64_t arming, int64_t *start, int64_t *previous)
{
    *start=esp_timer_get_time();
    if (*start<0) return -1;
    *previous=*start;
    lw_wifi_command_request_stop();
    for (;;) {
        /* Deadline wins even if shutdown finishes on/after the boundary. */
        if (!within_deadline(*start,previous)) return -1;
        if (!lw_arming_maintenance_held(arming) ||
            !PIOS_LiteWing_GCSReceiver_MaintenanceHeld(token)) return -1;
        const int quiet=lw_wifi_command_is_quiescent();
        /* Revalidate after observations, even though object-lock acquisition
         * is now nonblocking; scheduling can still delay this task. */
        if (!within_deadline(*start,previous)) return -1;
        if (quiet) return 0;
        delay_ms(10);
    }
}

static uint8_t wire_result(enum lw_wifi_store_result stored)
{
    switch (stored) {
    case LW_WIFI_STORE_INVALID: return INVALID;
    case LW_WIFI_STORE_NOT_WRITTEN: return NOT_WRITTEN;
    case LW_WIFI_STORE_VERIFIED: return VERIFIED;
    default: return UNCERTAIN;
    }
}

static void maintenance_task(void *arg)
{
    (void)arg;
    for (;;) {
        (void)ulTaskNotifyTake(pdTRUE,portMAX_DELAY);
        uint8_t blob[LW_WIFI_CONFIG_SIZE];
        portENTER_CRITICAL(&lock);
        if (phase!=QUEUED) {
            portEXIT_CRITICAL(&lock);
            continue;
        }
        memcpy(blob,pending,sizeof(blob));
        wipe(pending,sizeof(pending));
        phase=WAIT_STOP;
        portEXIT_CRITICAL(&lock);
        uint64_t token=0, arming=0;
        int64_t stop_started=0, previous=0;
        uint8_t outcome=NOT_ATTEMPTED;
        /* Atomically observe Disarmed and inhibit actual status writes before
         * reserving ingress. Neither mutex is held across shutdown/storage. */
        if (lw_arming_maintenance_begin(&arming)==0 &&
            PIOS_LiteWing_GCSReceiver_BeginMaintenance(1,&token)==0 &&
            lw_arming_maintenance_held(arming) &&
            stop_and_wait(token,arming,&stop_started,&previous)==0 &&
            lw_arming_maintenance_held(arming) &&
            PIOS_LiteWing_GCSReceiver_MaintenanceHeld(token) &&
            within_deadline(stop_started,&previous)) {
            set_phase(STORING);
            outcome=wire_result(lw_wifi_config_store(blob,sizeof(blob)));
        }
        wipe(blob,sizeof(blob));
        portENTER_CRITICAL(&lock);
        wipe(pending,sizeof(pending));
        result=outcome;
        portEXIT_CRITICAL(&lock);
        /* Retain only the token/result when cleanup fails. No credential
         * retries, radio restart, forced task deletion or owner release. */
        while (token && PIOS_LiteWing_GCSReceiver_EndMaintenance(token)!=0) {
            set_phase(CLEANUP_BLOCKED);
            delay_ms(100);
        }
        while (arming && lw_arming_maintenance_end(arming)!=0) {
            set_phase(CLEANUP_BLOCKED);
            delay_ms(100);
        }
        set_phase(FINISHED);
    }
}

int lw_usb_maintenance_start(void)
{
    portENTER_CRITICAL(&lock);
    if (launching || phase!=UNAVAILABLE) {
        portEXIT_CRITICAL(&lock);
        return -1;
    }
    launching=1;
    portEXIT_CRITICAL(&lock);
    TaskHandle_t created=NULL;
    BaseType_t rc=xTaskCreate(maintenance_task,"lw_usb_maint",4096,NULL,
                              tskIDLE_PRIORITY+1,&created);
    portENTER_CRITICAL(&lock);
    launching=0;
    if (rc==pdPASS) { task=created; phase=IDLE; }
    portEXIT_CRITICAL(&lock);
    return rc==pdPASS ? 0 : -1;
}

int lw_usb_maintenance_submit(const uint8_t *payload, size_t size)
{
    if (!payload || size!=16+LW_WIFI_CONFIG_SIZE) return -1;
    uint8_t copy[16+LW_WIFI_CONFIG_SIZE];
    struct lw_wifi_config decoded;
    memcpy(copy,payload,sizeof(copy));
    unsigned nonzero=0;
    for (size_t i=0;i<16;++i) nonzero|=copy[i];
    const int valid=lw_wifi_config_decode(copy+16,LW_WIFI_CONFIG_SIZE,&decoded)==0;
    lw_wifi_config_clear(&decoded);
    TaskHandle_t notify=NULL;
    portENTER_CRITICAL(&lock);
    if (nonzero && valid && (phase==IDLE || phase==FINISHED) &&
        memcmp(copy,transaction,16)!=0) {
        memcpy(transaction,copy,16);
        memcpy(pending,copy+16,sizeof(pending));
        phase=QUEUED;
        result=NOT_ATTEMPTED;
        notify=task;
    }
    portEXIT_CRITICAL(&lock);
    wipe(copy,sizeof(copy));
    if (!notify) return -1;
    xTaskNotifyGive(notify);
    return 0;
}

int lw_usb_maintenance_status(uint8_t *out, size_t capacity)
{
    if (!out || capacity<24) return -1;
    memset(out,0,24);
    out[0]=1;
    portENTER_CRITICAL(&lock);
    out[1]=phase; out[2]=result;
    memcpy(out+4,transaction,16);
    portEXIT_CRITICAL(&lock);
    return 24;
}
