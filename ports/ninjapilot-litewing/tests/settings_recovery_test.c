#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include "litewing_settings_recovery.h"

struct store {
    bool exists[3], marker;
    int persisted[3], ram[3], writes[3], probes[3], loads[3];
    int fail_index, fail_stage, mark_count;
};
static int inspect(void *context, unsigned i)
{
    struct store *s = context; assert(i < 3); ++s->probes[i];
    if (s->fail_index == (int)i && (s->fail_stage == 1 ||
        (s->fail_stage == 4 && s->probes[i] > 1))) return -1;
    return s->exists[i] ? 1 : 0;
}
static int load(void *context, unsigned i)
{
    struct store *s = context; assert(i < 3); ++s->loads[i];
    if (s->fail_index == (int)i && s->fail_stage == 2) return -1;
    if (!s->exists[i]) return -1;
    s->ram[i] = s->persisted[i]; return 0;
}
static int defaults_and_save(void *context, unsigned i)
{
    struct store *s = context; assert(i < 3 && !s->exists[i]); ++s->writes[i];
    s->ram[i] = 10 + (int)i;
    if (s->fail_index == (int)i && s->fail_stage == 3) return -1;
    if (s->fail_stage == 6) return 0; /* reproduce a no-op save reporting success */
    s->persisted[i] = s->ram[i]; s->exists[i] = true; return 0;
}
static int mark(void *context)
{
    struct store *s = context; ++s->mark_count;
    assert(s->exists[0] && s->exists[1] && s->exists[2]);
    if (s->fail_stage == 5) return -1;
    s->marker = true; return 0;
}
static const struct litewing_settings_ops ops = { inspect, load, defaults_and_save, mark };

int main(int argc, char **argv)
{
    assert(argc == 4);
    struct store s = { .fail_index = atoi(argv[2]), .fail_stage = atoi(argv[3]) };
    bool existing = strcmp(argv[1], "existing") == 0;
    bool partial = strcmp(argv[1], "partial") == 0;
    bool initial[3];
    for (unsigned i = 0; i < 3; ++i) {
        initial[i] = strncmp(argv[1], "mask", 4) == 0 ?
            (atoi(argv[1] + 4) & (1 << i)) != 0 : existing || (partial && i != 1);
        s.exists[i] = initial[i];
        s.persisted[i] = 100 + (int)i;
    }
    s.marker = existing || partial; /* a stale marker must not mask missing settings */
    int result = litewing_settings_recover(&ops, &s);
    if (s.fail_stage) {
        assert(result != 0);
        if (s.fail_stage != 5) assert(s.mark_count == 0);
        if (s.fail_stage == 1 || (s.fail_stage == 2 && existing)) {
            assert(s.writes[0] == 0 && s.writes[1] == 0 && s.writes[2] == 0);
        }
        /* Retry after simulated reboot, including each interrupted stage. */
        s.fail_stage = 0; s.fail_index = -1;
        memset(s.ram, 0, sizeof(s.ram));
        assert(litewing_settings_recover(&ops, &s) == 0);
        for (unsigned i = 0; i < 3; ++i) {
            assert(s.ram[i] == (initial[i] ? 100 + (int)i : 10 + (int)i));
        }
        return 0;
    }
    assert(result == 0 && s.marker && s.mark_count == 1);
    for (unsigned i = 0; i < 3; ++i) {
        bool preserved = initial[i];
        assert(s.persisted[i] == (preserved ? 100 + (int)i : 10 + (int)i));
        assert(s.writes[i] == (preserved ? 0 : 1));
        assert(s.ram[i] == s.persisted[i]);
    }
    /* Reboot: volatile values disappear; valid storage survives untouched. */
    memset(s.ram, 0, sizeof(s.ram)); memset(s.writes, 0, sizeof(s.writes));
    assert(litewing_settings_recover(&ops, &s) == 0);
    assert(s.writes[0] == 0 && s.writes[1] == 0 && s.writes[2] == 0);
    assert(s.ram[0] == s.persisted[0] && s.ram[1] == s.persisted[1] && s.ram[2] == s.persisted[2]);
    return 0;
}
