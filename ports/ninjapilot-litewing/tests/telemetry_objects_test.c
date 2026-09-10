#include <assert.h>
#include <pthread.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>

/* Real recursive pthread mutex, with a contending thread. Object storage and
 * instance lookup model only the pinned packer's external data boundary. */
typedef void *UAVObjHandle;
struct UAVOData { uint32_t id; uint16_t instance_size; uint8_t data[30]; };
struct UAVOMeta { uint8_t data[30]; };
typedef struct UAVOData *InstanceHandle;
static pthread_mutex_t object_mutex;
static pthread_mutex_t *mutex = &object_mutex;
static pthread_mutex_t signal_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t condition = PTHREAD_COND_INITIALIZER;
static int held, release_holder;
#define pdTRUE 1
#define portMAX_DELAY UINT32_MAX
#define PIOS_Assert assert
#define UAVObjIsMetaobject(object) ((void)(object), 0)
#define MetaNumBytes 30
#define MetaDataPtr(object) ((object)->data)
#define InstanceData(object) ((object)->data)
static InstanceHandle getInstance(struct UAVOData *obj, uint16_t instance) { return instance ? NULL : obj; }
static uint32_t UAVObjGetID(UAVObjHandle obj) { return ((struct UAVOData *)obj)->id; }
static uint32_t UAVObjGetNumBytes(UAVObjHandle obj) { return ((struct UAVOData *)obj)->instance_size; }
static int xSemaphoreTakeRecursive(pthread_mutex_t *m, uint32_t wait)
{ return (wait == 0 ? pthread_mutex_trylock(m) : pthread_mutex_lock(m)) == 0; }
static void xSemaphoreGiveRecursive(pthread_mutex_t *m) { assert(pthread_mutex_unlock(m) == 0); }
#include "pack.inc"

static void *hold(void *arg)
{
    (void)arg;
    assert(pthread_mutex_lock(&object_mutex) == 0);
    pthread_mutex_lock(&signal_mutex);
    held = 1;
    pthread_cond_broadcast(&condition);
    while (!release_holder) pthread_cond_wait(&condition, &signal_mutex);
    pthread_mutex_unlock(&signal_mutex);
    assert(pthread_mutex_unlock(&object_mutex) == 0);
    return NULL;
}

int main(void)
{
    pthread_mutexattr_t attr;
    assert(pthread_mutexattr_init(&attr) == 0);
    assert(pthread_mutexattr_settype(&attr, PTHREAD_MUTEX_RECURSIVE) == 0);
    assert(pthread_mutex_init(&object_mutex, &attr) == 0);
    pthread_mutexattr_destroy(&attr);
    uint32_t ids[] = {0xD7E0D964, 0xEF69B6BC, 0x6B7639EC, 0xB8229FE4};
    uint16_t sizes[] = {28, 8, 25, 29};
    struct UAVOData obj = {0};
    uint8_t buffer[32];
    for (size_t i = 0; i < 4; ++i) {
        obj.id = ids[i]; obj.instance_size = sizes[i];
        memset(obj.data, 0x37, sizeof(obj.data));
        for (size_t cap = 0; cap <= 30; ++cap) {
            memset(buffer, 0xa5, sizeof(buffer));
            int rc = lw_telemetry_try_pack(&obj, buffer + 1, cap);
            assert(rc == (cap < sizes[i] ? -1 : 0));
            for (size_t j = 0; j < 32; ++j)
                assert(buffer[j] == (rc == 0 && j >= 1 && j <= sizes[i] ? 0x37 : 0xa5));
        }
        ++obj.instance_size;
        assert(lw_telemetry_try_pack(&obj, buffer, sizeof(buffer)) == -1);
    }
    /* Cached battery must not pass this path; it needs age-aware packing. */
    obj.id = 0x26962352; obj.instance_size = 30;
    assert(lw_telemetry_try_pack(&obj, buffer, sizeof(buffer)) == -1);
    assert(lw_telemetry_try_pack(NULL, buffer, sizeof(buffer)) == -1);
    assert(lw_telemetry_try_pack(&obj, NULL, sizeof(buffer)) == -1);
    obj.id = ids[0]; obj.instance_size = sizes[0];
    pthread_t holder;
    assert(pthread_create(&holder, NULL, hold, NULL) == 0);
    pthread_mutex_lock(&signal_mutex);
    while (!held) pthread_cond_wait(&condition, &signal_mutex);
    pthread_mutex_unlock(&signal_mutex);
    memset(buffer, 0xa5, sizeof(buffer));
    assert(lw_telemetry_try_pack(&obj, buffer, sizeof(buffer)) == -1);
    for (size_t i = 0; i < sizeof(buffer); ++i) assert(buffer[i] == 0xa5);
    pthread_mutex_lock(&signal_mutex);
    release_holder = 1;
    pthread_cond_broadcast(&condition);
    pthread_mutex_unlock(&signal_mutex);
    pthread_join(holder, NULL);
    assert(lw_telemetry_try_pack(&obj, buffer, sizeof(buffer)) == 0);
    mutex = NULL;
    assert(lw_telemetry_try_pack(&obj, buffer, sizeof(buffer)) == -1);
    pthread_mutex_destroy(&object_mutex);
    return 0;
}
