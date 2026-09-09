/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) 2026 LRRK contributors. */
#pragma once

/* Three required board settings: mixer, actuator and manual-control mappings.
 * inspect: 1 present with valid layout, 0 confirmed absent, -1 error.
 * Other operations: zero success, nonzero failure. Runs before flight tasks.
 * The coordinator never overwrites present settings, and the marker is only
 * committed after every missing object has been saved and reloaded. */
struct litewing_settings_ops {
    int (*inspect)(void *, unsigned);
    int (*load)(void *, unsigned);
    int (*defaults_and_save)(void *, unsigned);
    int (*mark)(void *);
};
int litewing_settings_recover(const struct litewing_settings_ops *, void *);
