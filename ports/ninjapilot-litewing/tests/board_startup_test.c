/* Actual board/entry orchestration; OS, hardware and object storage boundaries
 * are scripted here. No real serial, scheduler, flash or motor APIs are linked. */
#include "board_test.h"
#include <actuatorsettings.h>
#include <firmwareiapobj.h>
#include <gcsreceiver.h>
#include <manualcontrolsettings.h>
#include <mixersettings.h>
#include <systemalarms.h>
#include <taskinfo.h>
#include "pios_litewing_board.h"
#include "pios_litewing_brushed_pwm.h"
#include "pios_litewing_flashfs.h"

#define CHECK(test) do { if (!(test)) { \
    fprintf(stderr, "scenario=%s line=%d: %s\ntrace=%s\n", scenario, __LINE__, #test, trace); \
    exit(1); \
} } while (0)

static const char *scenario;
static char trace[2048];
static unsigned calls, later_calls, modules, system_inits, shutdown_requests;
static unsigned critical_writes, success_writes, allocations, frees;
static bool failed, led_ready, alarms_ready, objects_ready, hardware_started;
static bool owned[2], transferred;
static uint8_t rx_buffer[2048], tx_buffer[512];
static MixerSettingsData mixer;
static ActuatorSettingsData actuator;
static ManualControlSettingsData manual;
static FirmwareIAPObjData identity;
static SystemAlarmsData alarm_data;
static GCSReceiverData receiver;

struct object { uint32_t id; size_t size; void *data; };
#define OBJECT(name, id) { id, sizeof(name), &name }
static struct object objects[] = {
    OBJECT(mixer, MIXERSETTINGS_OBJID), OBJECT(actuator, ACTUATORSETTINGS_OBJID),
    OBJECT(manual, MANUALCONTROLSETTINGS_OBJID), OBJECT(identity, FIRMWAREIAPOBJ_OBJID),
    OBJECT(alarm_data, SYSTEMALARMS_OBJID), OBJECT(receiver, GCSRECEIVER_OBJID),
};
const struct pios_com_driver pios_esp32_usart_com_driver = {0};
const struct pios_rcvr_driver pios_gcsrcvr_rcvr_driver = {0};
extern uint32_t pios_rcvr_group_map[];
extern uintptr_t pios_uavo_settings_fs_id;
extern void PIOS_Board_Init(void);
extern void app_main(void);

static int step(const char *name)
{
    /* Every board service is called while the sequence is still incomplete. */
    if (modules == 0) CHECK(!PIOS_LiteWing_BoardServicesInitialized());
    calls++;
    if (failed) later_calls++;
    CHECK(strlen(trace) + strlen(name) + 2 < sizeof(trace));
    strcat(trace, name);
    strcat(trace, " ");
    if (strcmp(scenario, name) == 0) { failed = true; return -1; }
    return 0;
}

static UAVObjHandle handle(unsigned i, const char *failure)
{
    CHECK(objects_ready);
    if (strcmp(scenario, failure) == 0) {
        if (!failed) (void)step(failure);
        return NULL;
    }
    return &objects[i];
}
UAVObjHandle MixerSettingsHandle(void) { return handle(0, "mixer-handle"); }
UAVObjHandle ActuatorSettingsHandle(void) { return handle(1, "actuator-handle"); }
UAVObjHandle ManualControlSettingsHandle(void) { return handle(2, "manual-handle"); }
UAVObjHandle FirmwareIAPObjHandle(void) { return handle(3, "identity-handle"); }
UAVObjHandle SystemAlarmsHandle(void) { return handle(4, "alarm-handle"); }
UAVObjHandle GCSReceiverHandle(void) { return handle(5, "gcs-handle"); }

int32_t UAVObjGetData(UAVObjHandle obj, void *out)
{
    if (!obj) return -1;
    if (obj == &objects[3] && step("identity-get") != 0) return -1;
    struct object *object = obj;
    memcpy(out, object->data, object->size);
    return 0;
}
int32_t UAVObjSetData(UAVObjHandle obj, const void *data)
{
    if (!obj) return -1;
    if (obj == &objects[3]) {
        if (step("identity-set") != 0) return -1;
        const FirmwareIAPObjData *iap = data;
        CHECK(iap->BoardType == 0x13 && iap->BoardRevision == 2);
        CHECK(memcmp(iap->Description, "OpFw", 4) == 0);
        CHECK(iap->Command == 0x1234); /* Preserve unrelated initialized fields. */
    } else {
        CHECK(false); /* Existing settings must never be defaulted in this fixture. */
    }
    struct object *object = obj;
    memcpy(object->data, data, object->size);
    return 0;
}
uint32_t UAVObjGetID(UAVObjHandle obj) { CHECK(obj); return ((struct object *)obj)->id; }
uint32_t UAVObjGetNumBytes(UAVObjHandle obj) { CHECK(obj); return ((struct object *)obj)->size; }
int32_t UAVObjInitialize(void) { return step("manager"); }
void UAVObjectsInitializeAll(void)
{
    CHECK(step("objects") == 0);
    objects_ready = true;
    identity.Command = 0x1234;
}
int32_t GCSReceiverInitialize(void)
{
    /* The generated API returns -2 for an already registered object. */
    CHECK(objects_ready);
    return -2;
}

int32_t PIOS_LiteWing_FLASHFS_ObjectState(uintptr_t fs, uint32_t id, uint16_t instance, uint16_t size)
{
    CHECK(fs == 42 && instance == 0);
    for (unsigned i = 0; i < 3; i++) {
        if (id == objects[i].id) {
            CHECK(size == objects[i].size);
            char name[] = "inspect0"; name[7] += i;
            return step(name) == 0 ? 1 : -1;
        }
    }
    CHECK(false); return -1;
}
int32_t UAVObjLoad(UAVObjHandle obj, uint16_t instance)
{
    CHECK(instance == 0);
    for (unsigned i = 0; i < 3; i++) {
        if (obj == &objects[i]) {
            char name[] = "load0"; name[4] += i;
            return step(name);
        }
    }
    CHECK(false); return -1;
}
int32_t UAVObjSave(UAVObjHandle obj, uint16_t instance)
{ (void)obj; (void)instance; CHECK(false); return -1; }
bool PIOS_LiteWing_FLASHFS_Healthy(void) { return step("settings-health") == 0; }
int32_t PIOS_LiteWing_FLASHFS_MarkProvisioned(void) { return step("marker"); }

int32_t PIOS_DELAY_Init(void) { return step("delay"); }
int32_t PIOS_LED_Init(const struct pios_esp32_led_cfg *cfg)
{
    CHECK(cfg->num_leds == 2 && cfg->leds[0].pin == 7 && cfg->leds[1].pin == 8);
    int rc = step("led"); led_ready = rc == 0; return rc;
}
void PIOS_LED_On(uint32_t led)
{ CHECK(led_ready); CHECK(led == PIOS_LED_HEARTBEAT || led == PIOS_LED_ALARM); }
int32_t PIOS_TASK_MONITOR_Initialize(uint16_t max)
{ CHECK(max == TASKINFO_RUNNING_NUMELEM); return step("monitor"); }
int32_t PIOS_CALLBACKSCHEDULER_Initialize(void) { return step("scheduler"); }
int32_t EventDispatcherInitialize(void) { return step("events"); }
int32_t PIOS_ESP32_FLASHFS_Init(uintptr_t *id)
{ int rc = step("storage"); *id = rc == 0 ? 42 : 0; return rc; }
void PIOS_DEBUGLOG_Initialize(void) { CHECK(step("debuglog") == 0); }
int32_t AlarmsInitialize(void)
{ int rc = step("alarms"); alarms_ready = rc == 0; return rc; }
int32_t AlarmsSet(SystemAlarmsAlarmElem alarm, SystemAlarmsAlarmOptions severity)
{
    CHECK(alarms_ready && alarm == SYSTEMALARMS_ALARM_BOOTFAULT);
    if (severity == SYSTEMALARMS_ALARM_CRITICAL) critical_writes++;
    else success_writes++;
    return 0;
}
uint16_t PIOS_WDG_Init(void)
{ CHECK(step("wdg") == 0); return strcmp(scenario, "watchdog-flags") == 0 ? 0xffff : 0; }
int32_t PIOS_ESP32_USART_Init(uint32_t *id, const struct pios_esp32_usart_cfg *cfg)
{
    CHECK(cfg->port == 0 && cfg->rx_pin == 44 && cfg->tx_pin == 43);
    int rc = step("uart"); *id = rc == 0 ? 43 : 0; return rc;
}
void *pios_malloc(size_t size)
{
    bool rx = allocations++ == 0;
    CHECK(size == (rx ? sizeof(rx_buffer) : sizeof(tx_buffer)));
    if (step(rx ? "rx" : "tx") != 0) return NULL;
    owned[rx ? 0 : 1] = true;
    return rx ? rx_buffer : tx_buffer;
}
void pios_free(void *buffer)
{
    CHECK(buffer == rx_buffer || buffer == tx_buffer);
    unsigned index = buffer == rx_buffer ? 0 : 1;
    CHECK(owned[index] && !transferred);
    owned[index] = false;
    frees++;
}
int32_t PIOS_COM_Init(uint32_t *id, const struct pios_com_driver *driver, uint32_t uart,
                      uint8_t *rx, uint16_t rx_len, uint8_t *tx, uint16_t tx_len)
{
    CHECK(driver == &pios_esp32_usart_com_driver && uart == 43);
    CHECK(rx == rx_buffer && tx == tx_buffer && rx_len == 2048 && tx_len == 512);
    CHECK(owned[0] && owned[1] && !transferred);
    int rc = step("com");
    *id = rc == 0 ? 44 : 0;
    transferred = rc == 0;
    return rc;
}
int32_t PIOS_GCSRCVR_Init(uint32_t *id)
{ int rc = step("gcs"); *id = rc == 0 ? 45 : 0; return rc; }
int32_t PIOS_RCVR_Init(uint32_t *id, const struct pios_rcvr_driver *driver, uint32_t gcs)
{
    CHECK(driver == &pios_gcsrcvr_rcvr_driver && gcs == 45);
    int rc = step("rcvr"); *id = rc == 0 ? 46 : 0; return rc;
}
int32_t PIOS_LiteWing_Board_Init(void)
{
    CHECK(pios_rcvr_group_map[MANUALCONTROLSETTINGS_CHANNELGROUPS_GCS] == 46);
    hardware_started = true;
    return step("hardware");
}
void PIOS_LiteWing_BrushedPWM_Shutdown(void) { shutdown_requests++; }
void PIOS_SYS_Init(void) {}
int32_t PIOS_LiteWing_ModulesInitialize(void) { modules++; return step("modules"); }
int32_t SystemModInitialize(void) { system_inits++; return step("system"); }
unsigned xPortGetFreeHeapSize(void) { (void)step("heap"); return 10000; }

int main(int argc, char **argv)
{
    CHECK(argc == 2);
    scenario = argv[1];
    bool nominal = strcmp(scenario, "nominal") == 0 || strcmp(scenario, "watchdog-flags") == 0;
    CHECK(!PIOS_LiteWing_BoardServicesInitialized());
    app_main();
    CHECK(PIOS_LiteWing_BoardServicesInitialized() == nominal);
    CHECK(success_writes == 0);
    if (nominal) {
        CHECK(!failed && shutdown_requests == 0 && modules == 1 && system_inits == 1);
        CHECK(hardware_started && critical_writes == 0);
        CHECK(owned[0] && owned[1] && transferred && frees == 0);
        CHECK(strcmp(trace, "delay led monitor scheduler events storage manager objects identity-get identity-set settings-health inspect0 inspect1 inspect2 load0 load1 load2 marker debuglog alarms wdg uart rx tx com gcs rcvr hardware modules system heap ") == 0);
    } else {
        CHECK(failed);
        CHECK(modules == 0 && system_inits == 0);
        CHECK(later_calls == 0);
        CHECK(shutdown_requests == 1);
        CHECK(critical_writes == (alarms_ready ? 1u : 0u));
        CHECK(!hardware_started || strcmp(scenario, "hardware") == 0);
        if (strcmp(scenario, "storage") == 0) CHECK(pios_uavo_settings_fs_id == 0);
        if (strcmp(scenario, "tx") == 0) CHECK(frees == 1);
        if (strcmp(scenario, "com") == 0) CHECK(frees == 2);
    }
    /* Clearing the scripted fault must not allow reinitialization in this boot. */
    unsigned before = calls, shutdown_before = shutdown_requests;
    failed = false;
    scenario = "nominal";
    PIOS_Board_Init();
    CHECK(calls == before && shutdown_requests == shutdown_before);
    CHECK(PIOS_LiteWing_BoardServicesInitialized() == nominal);
    return 0;
}
