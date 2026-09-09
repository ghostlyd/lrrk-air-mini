/* Execute the production backend; only ESP-IDF NVS is replaced by storage. */
#include "pios.h"
#include "pios_flashfs.h"
#include "nvs_flash.h"
#include "pios_litewing_flashfs.h"
#include "uavobjectmanager.h"

uintptr_t pios_uavo_settings_fs_id;
uint32_t UAVObjGetID(UAVObjHandle obj) { assert(obj); return *(uint32_t *)obj; }

static uint8_t blob[256];
static size_t blob_size;
static char blob_key[16];
static bool present;
static int init_error, commit_error, write_error, read_error, partial_read_error, marker_read_error;
static int partition_erases, key_erases, writes, erase_error;
static uint8_t marker;
static int allocation_error, short_read;
void *litewing_test_malloc(size_t size) { return allocation_error ? NULL : calloc(1, size); }

esp_err_t nvs_flash_init_partition(const char *name)
{ assert(strcmp(name, "settings") == 0); return init_error; }
esp_err_t nvs_flash_erase_partition(const char *name)
{ assert(strcmp(name, "settings") == 0); ++partition_erases; present = false; init_error = 0; return ESP_OK; }
esp_err_t nvs_open_from_partition(const char *part, const char *space, int mode, nvs_handle_t *out)
{ assert(strcmp(part, "settings") == 0 && strcmp(space, "uavo") == 0 && mode == NVS_READWRITE); *out = 42; return ESP_OK; }
esp_err_t nvs_get_u8(nvs_handle_t h, const char *key, uint8_t *out)
{ assert(h == 42 && strcmp(key, "provisioned") == 0); *out = marker; return marker_read_error; }
esp_err_t nvs_set_u8(nvs_handle_t h, const char *key, uint8_t value)
{ assert(h == 42 && strcmp(key, "provisioned") == 0); marker = value; return write_error; }
esp_err_t nvs_commit(nvs_handle_t h)
{ assert(h == 42); return commit_error; }
esp_err_t nvs_set_blob(nvs_handle_t h, const char *key, const void *data, size_t size)
{
    assert(h == 42 && size <= sizeof(blob) && strlen(key) == 12);
    ++writes;
    if (write_error) return write_error;
    strcpy(blob_key, key); memcpy(blob, data, size); blob_size = size; present = true;
    return ESP_OK;
}
esp_err_t nvs_get_blob(nvs_handle_t h, const char *key, void *data, size_t *size)
{
    assert(h == 42);
    if (read_error) return read_error;
    if (!present || strcmp(key, blob_key) != 0) return ESP_ERR_NVS_NOT_FOUND;
    if (!data) { *size = blob_size; return ESP_OK; }
    if (partial_read_error) { ((uint8_t *)data)[0] = 0x99; return ESP_FAIL; }
    if (short_read) { memcpy(data, blob, 2); *size = 2; return ESP_OK; }
    if (*size < blob_size) return ESP_FAIL;
    memcpy(data, blob, blob_size); *size = blob_size; return ESP_OK;
}
esp_err_t nvs_erase_key(nvs_handle_t h, const char *key)
{
    assert(h == 42); ++key_erases;
    if (erase_error) return erase_error;
    if (!present || strcmp(key, blob_key) != 0) return ESP_ERR_NVS_NOT_FOUND;
    present = false; return ESP_OK;
}
esp_err_t nvs_erase_all(nvs_handle_t h)
{ assert(h == 42); ++key_erases; present = false; return ESP_OK; }
esp_err_t nvs_get_stats(const char *part, nvs_stats_t *out)
{ assert(strcmp(part, "settings") == 0); out->used_entries = present; out->free_entries = 100; return ESP_OK; }

int main(int argc, char **argv)
{
    assert(argc == 2);
    const char *scenario = argv[1];
    uintptr_t fs = 0;
    uint8_t input[] = {0x91, 0x02, 0x73, 0x44}, output[] = {9, 9, 9, 9};
    if (strcmp(scenario, "full-preserved") == 0 || strcmp(scenario, "new-format-preserved") == 0) {
        init_error = strcmp(scenario, "full-preserved") == 0 ? ESP_ERR_NVS_NO_FREE_PAGES : ESP_ERR_NVS_NEW_VERSION_FOUND;
        assert(PIOS_ESP32_FLASHFS_Init(&fs) != 0);
        assert(partition_erases == 0 && writes == 0);
        return 0;
    }
    assert(PIOS_ESP32_FLASHFS_Init(&fs) == 0 && fs != 0);
    pios_uavo_settings_fs_id = fs;
    if (strcmp(scenario, "delete-absent") == 0) {
        uint32_t id = 0x12345678;
        assert(UAVObjDelete(&id, 0x9abc) == 0 && !present); return 0;
    }
    if (strcmp(scenario, "state-missing") == 0) {
        assert(PIOS_LiteWing_FLASHFS_ObjectState(fs, 0x12345678, 0x9abc, 4) == 0);
        assert(PIOS_LiteWing_FLASHFS_Healthy()); return 0;
    }
    if (strcmp(scenario, "marker-commit-error") == 0 || strcmp(scenario, "marker-write-error") == 0 ||
        strcmp(scenario, "marker-read-error") == 0 || strcmp(scenario, "marker-invalid") == 0) {
        if (strcmp(scenario, "marker-commit-error") == 0) commit_error = ESP_FAIL;
        if (strcmp(scenario, "marker-write-error") == 0) write_error = ESP_FAIL;
        if (strcmp(scenario, "marker-read-error") == 0) marker_read_error = ESP_FAIL;
        if (strcmp(scenario, "marker-invalid") == 0) marker = 7;
        assert(PIOS_LiteWing_FLASHFS_MarkProvisioned() != 0);
        assert(!PIOS_LiteWing_FLASHFS_Healthy()); return 0;
    }
    if (strcmp(scenario, "marker-success") == 0) {
        assert(PIOS_LiteWing_FLASHFS_MarkProvisioned() == 0);
        assert(marker == 1 && PIOS_LiteWing_FLASHFS_Healthy()); return 0;
    }
    if (strcmp(scenario, "missing") == 0) {
        assert(PIOS_FLASHFS_ObjLoad(fs, 0x12345678, 0x9abc, output, 4) != 0);
        assert(output[0] == 9 && key_erases == 0 && writes == 0); return 0;
    }
    assert(PIOS_FLASHFS_ObjSave(fs, 0x12345678, 0x9abc, input, 4) == 0);
    assert(strcmp(blob_key, "123456789ABC") == 0);
    if (strncmp(scenario, "delete-", 7) == 0) {
        uint32_t id = 0x12345678;
        bool failed = strcmp(scenario, "delete-success") != 0;
        if (strcmp(scenario, "delete-erase-error") == 0) erase_error = ESP_FAIL;
        if (strcmp(scenario, "delete-commit-error") == 0) commit_error = ESP_FAIL;
        int result = UAVObjDelete(&id, 0x9abc);
        assert(failed ? result != 0 : result == 0);
        if (erase_error) assert(present);
        else assert(!present);
        return 0;
    }
    if (strcmp(scenario, "state-present") == 0) {
        assert(PIOS_LiteWing_FLASHFS_ObjectState(fs, 0x12345678, 0x9abc, 4) == 1);
        assert(PIOS_LiteWing_FLASHFS_Healthy());
    } else if (strcmp(scenario, "state-error") == 0) {
        read_error = ESP_FAIL;
        assert(PIOS_LiteWing_FLASHFS_ObjectState(fs, 0x12345678, 0x9abc, 4) == -1);
        assert(!PIOS_LiteWing_FLASHFS_Healthy() && present && key_erases == 0);
    } else if (strcmp(scenario, "state-mismatch") == 0) {
        assert(PIOS_LiteWing_FLASHFS_ObjectState(fs, 0x12345678, 0x9abc, 3) == -1);
        assert(!PIOS_LiteWing_FLASHFS_Healthy() && present && key_erases == 0);
    } else if (strcmp(scenario, "round-trip") == 0) {
        assert(PIOS_FLASHFS_ObjLoad(fs, 0x12345678, 0x9abc, output, 4) == 0);
        assert(memcmp(output, input, 4) == 0);
    } else if (strcmp(scenario, "mismatch-preserved") == 0) {
        assert(PIOS_FLASHFS_ObjLoad(fs, 0x12345678, 0x9abc, output, 3) != 0);
        assert(present && key_erases == 0 && output[0] == 9);
    } else if (strcmp(scenario, "read-error") == 0 || strcmp(scenario, "partial-read-error") == 0 ||
               strcmp(scenario, "short-read") == 0 || strcmp(scenario, "allocation-error") == 0) {
        if (strcmp(scenario, "partial-read-error") == 0) partial_read_error = 1;
        else if (strcmp(scenario, "short-read") == 0) short_read = 1;
        else if (strcmp(scenario, "allocation-error") == 0) allocation_error = 1;
        else read_error = ESP_FAIL;
        assert(PIOS_FLASHFS_ObjLoad(fs, 0x12345678, 0x9abc, output, 4) != 0);
        assert(present && key_erases == 0 && output[0] == 9);
        assert(output[1] == 9 && output[2] == 9 && output[3] == 9);
        assert(!PIOS_LiteWing_FLASHFS_Healthy());
        /* A transient storage recovery cannot clear the boot fault latch. */
        read_error = partial_read_error = 0;
        assert(PIOS_LiteWing_FLASHFS_ObjectState(fs, 0x12345678, 0x9abc, 4) == -1);
    } else if (strcmp(scenario, "commit-error") == 0) {
        commit_error = ESP_FAIL;
        assert(PIOS_FLASHFS_ObjSave(fs, 0x12345678, 0x9abc, input, 4) != 0);
    } else if (strcmp(scenario, "write-error") == 0) {
        write_error = ESP_FAIL;
        assert(PIOS_FLASHFS_ObjSave(fs, 0x12345678, 0x9abc, input, 4) != 0);
    } else { assert(!"unknown scenario"); }
    assert(partition_erases == 0);
    return 0;
}
