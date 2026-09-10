/* Appended inside the hash-checked object-manager translation unit.
 * The ordinary packer waits indefinitely. Acquire its recursive mutex with
 * zero wait first; the nested pack acquisition is then by its current owner.
 * Object IDs and instance sizes are fixed after registration in pinned source.
 */
int32_t lw_telemetry_try_pack(UAVObjHandle object, uint8_t *data, size_t capacity)
{
    if (!object || !data || !mutex || xSemaphoreTakeRecursive(mutex, 0) != pdTRUE)
        return -1;
    uint32_t size = 0;
    switch (UAVObjGetID(object)) {
    case UINT32_C(0xD7E0D964): size = 28; break;
    case UINT32_C(0xEF69B6BC): size = 8; break;
    case UINT32_C(0x6B7639EC): size = 25; break;
    case UINT32_C(0xB8229FE4): size = 29; break;
    default: break;
    }
    int32_t result = -1;
    if (size && capacity >= size && UAVObjGetNumBytes(object) == size)
        result = UAVObjPack(object, 0, data);
    xSemaphoreGiveRecursive(mutex);
    return result;
}
