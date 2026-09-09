/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) 2026 LRRK contributors. */
#include "litewing_settings_recovery.h"

int litewing_settings_recover(const struct litewing_settings_ops *ops, void *context)
{
    int states[3];
    if (!ops || !ops->inspect || !ops->load || !ops->defaults_and_save || !ops->mark) {
        return -1;
    }
    /* Inspect everything before the first write; a corrupt object is never
     * conflated with an absent one, even if a provisioning marker exists. */
    for (unsigned i = 0; i < 3; ++i) {
        states[i] = ops->inspect(context, i);
        if (states[i] != 0 && states[i] != 1) return -1;
    }
    for (unsigned i = 0; i < 3; ++i) {
        if (states[i] == 1 && ops->load(context, i) != 0) return -1;
    }
    for (unsigned i = 0; i < 3; ++i) {
        if (states[i] == 0 &&
            (ops->defaults_and_save(context, i) != 0 ||
             ops->inspect(context, i) != 1 || ops->load(context, i) != 0)) return -1;
    }
    return ops->mark(context);
}
