#ifndef PIOS_LITEWING_MODULES_H
#define PIOS_LITEWING_MODULES_H

#include <stdint.h>

/* Boot-caller-only entry points. Zero means the selected functions accepted
 * the request, not that asynchronous module startup or flight checks passed.
 * Callers must latch output shutdown on any nonzero result. */
int32_t PIOS_LiteWing_ModulesInitialize(void);
int32_t PIOS_LiteWing_ModulesStart(void);

#endif
