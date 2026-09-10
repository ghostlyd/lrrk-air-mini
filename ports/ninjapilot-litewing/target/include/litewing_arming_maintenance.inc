/* SPDX-License-Identifier: GPL-3.0-or-later
 * Included only inside the hash-checked object-manager translation unit.
 * All state is protected by its existing recursive mutex, including writes.
 */
static uint64_t lw_arming_generation, lw_arming_token;
_Static_assert(offsetof(FlightStatusData,Armed)==0,"review changed Armed layout");
_Static_assert(sizeof(((FlightStatusData *)0)->Armed)==1,"review changed Armed width");

static int lw_arming_write_allowed(UAVObjHandle object,const void *data,
                                   uint32_t offset,uint32_t size)
{
    /* Caller already owns object-manager mutex. Full writes and unpack call
     * this with offset zero; field writes cannot smuggle an overlapping Armed
     * byte. Allow disarming and unrelated fields/objects normally. */
    if (!lw_arming_token || object!=FlightStatusHandle() || offset!=0 || !size) return 1;
    return data && ((const uint8_t *)data)[0]==FLIGHTSTATUS_ARMED_DISARMED;
}

int32_t lw_arming_maintenance_begin(uint64_t *token)
{
    if (token) *token=0;
    if (!token || !mutex || xSemaphoreTakeRecursive(mutex,0)!=pdTRUE) return -1;
    FlightStatusData flight;
    int32_t rc=-1;
    if (!lw_arming_token && lw_arming_generation!=UINT64_MAX && FlightStatusHandle() &&
        FlightStatusGet(&flight)==0 && flight.Armed==FLIGHTSTATUS_ARMED_DISARMED) {
        lw_arming_token=++lw_arming_generation;
        *token=lw_arming_token;
        rc=0;
    }
    xSemaphoreGiveRecursive(mutex);
    return rc;
}

int32_t lw_arming_maintenance_held(uint64_t token)
{
    if (!token || !mutex || xSemaphoreTakeRecursive(mutex,0)!=pdTRUE) return 0;
    FlightStatusData flight;
    int32_t held=token==lw_arming_token && FlightStatusHandle() &&
        FlightStatusGet(&flight)==0 && flight.Armed==FLIGHTSTATUS_ARMED_DISARMED;
    xSemaphoreGiveRecursive(mutex);
    return held;
}

int32_t lw_arming_maintenance_end(uint64_t token)
{
    if (!token || !mutex || xSemaphoreTakeRecursive(mutex,0)!=pdTRUE) return -1;
    int32_t rc=-1;
    if (token==lw_arming_token) { lw_arming_token=0; rc=0; }
    xSemaphoreGiveRecursive(mutex);
    return rc;
}
