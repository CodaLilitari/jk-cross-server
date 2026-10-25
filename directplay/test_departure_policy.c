/* SPDX-License-Identifier: MIT */
#include "departure_policy.h"
#include <assert.h>
#include <stdio.h>

int main(void) {
    /* The local host and surrogate persist after retail player900 leaves.
     * Another retail player901 may still be present: only the obsolete
     * unicast can be discarded, never a broadcast to that remaining peer. */
    struct jkdp_player_snapshot s={2,1,{{101,1},{102,1}}};
    assert(jkdp_departure_policy(&s,101,900,1,1)==JKDP_DEPARTURE_DISCARD);
    assert(jkdp_departure_policy(&s,102,0,1,1)==JKDP_DEPARTURE_DISCARD);
    s.players[s.count].id=901;s.players[s.count++].local=0;
    assert(jkdp_departure_policy(&s,102,900,1,1)==JKDP_DEPARTURE_DISCARD);
    assert(jkdp_departure_policy(&s,102,901,1,1)==JKDP_DEPARTURE_TARGET_PRESENT);
    assert(jkdp_departure_policy(&s,102,0,1,1)==JKDP_DEPARTURE_LIVE_BROADCAST);

    /* A present local destination is not evidence of a departed player. */
    assert(jkdp_departure_policy(&s,101,102,1,1)==JKDP_DEPARTURE_TARGET_PRESENT);
    assert(jkdp_departure_policy(&s,101,900,0,1)==JKDP_DEPARTURE_BAD_SOURCE);
    assert(jkdp_departure_policy(&s,101,900,1,0)==JKDP_DEPARTURE_BAD_SOURCE);
    assert(jkdp_departure_policy(&s,999,900,1,1)==JKDP_DEPARTURE_BAD_SOURCE);
    assert(jkdp_departure_policy(&s,901,900,1,1)==JKDP_DEPARTURE_BAD_SOURCE);

    /* Enum failure, early-stop/overflow and empty snapshots cannot establish
     * absence, even when the cached owned-ID check succeeded. */
    s.complete=0;
    assert(jkdp_departure_policy(&s,101,900,1,1)==JKDP_DEPARTURE_INCOMPLETE);
    assert(jkdp_departure_policy(&s,101,0,1,1)==JKDP_DEPARTURE_INCOMPLETE);
    s.complete=1;s.count=JKDP_DEPARTURE_MAX_PLAYERS+1;
    assert(jkdp_departure_policy(&s,101,900,1,1)==JKDP_DEPARTURE_INCOMPLETE);
    s.count=0;
    assert(jkdp_departure_policy(&s,101,900,1,1)==JKDP_DEPARTURE_BAD_SOURCE);
    assert(jkdp_departure_policy(&s,101,0,1,1)==JKDP_DEPARTURE_BAD_SOURCE);
    puts("PASS: verified departed destination and empty broadcast; reject live targets/remotes, invalid or absent sender, incomplete enumeration and overflow");
    return 0;
}
