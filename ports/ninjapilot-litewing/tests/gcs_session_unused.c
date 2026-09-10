/* USB-only regressions must never enter session publication. The dedicated
 * pilot receiver integration fixture links real session/SDK dependencies. */
#include "litewing_pilot_session.h"
#include <stdlib.h>
void lw_session_retire(struct lw_pilot_session *state)
{ (void)state; abort(); }
enum lw_session_result lw_session_commit_control(struct lw_pilot_session *state,
    int64_t now, int owner, struct lw_pilot_candidate *out)
{ (void)state; (void)now; (void)owner; (void)out; abort(); }
