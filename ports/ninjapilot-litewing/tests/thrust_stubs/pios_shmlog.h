#pragma once
/* No shared-memory logging or external I/O in the host fixture. */
#define PIOS_SHMLOG_Printf(...) ((void)0)
