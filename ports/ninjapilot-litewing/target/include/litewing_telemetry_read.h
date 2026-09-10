#pragma once
#include "litewing_telemetry_wire.h"

/* Command-task-only rotating selection 0..4. No allocation, writes or waiting
 * for the object-manager mutex. Contention/schema/clock failures zero out.
 * Caller owns out exclusively. Four cached objects have unknown sample age;
 * battery bytes/voltage age come from the coherent acquisition exporter. */
int lw_telemetry_read(unsigned index, struct lw_telemetry_record *out);
