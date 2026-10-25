/* SPDX-License-Identifier: MIT */
#ifndef JKDP_DEPARTURE_POLICY_H
#define JKDP_DEPARTURE_POLICY_H
#include <stdint.h>

#define JKDP_DEPARTURE_MAX_PLAYERS 32u
struct jkdp_player_snapshot {
    unsigned count;
    int complete;
    struct { uint32_t id; int local; } players[JKDP_DEPARTURE_MAX_PLAYERS];
};
enum jkdp_departure_decision {
    JKDP_DEPARTURE_BAD_SOURCE,
    JKDP_DEPARTURE_INCOMPLETE,
    JKDP_DEPARTURE_TARGET_PRESENT,
    JKDP_DEPARTURE_LIVE_BROADCAST,
    JKDP_DEPARTURE_DISCARD
};

/* Caller separately verifies an eligible failed Send and fresh DP queries.
 * Never infer a departure from an HRESULT or cached player list alone. */
static inline enum jkdp_departure_decision jkdp_departure_policy(
    const struct jkdp_player_snapshot *s, uint32_t from, uint32_t to,
    int sender_owned, int sender_local)
{
    unsigned i,remotes=0;int source_present=0,target_present=0;
    if(!sender_owned || !sender_local)return JKDP_DEPARTURE_BAD_SOURCE;
    if(!s->complete || s->count>JKDP_DEPARTURE_MAX_PLAYERS)return JKDP_DEPARTURE_INCOMPLETE;
    for(i=0;i<s->count;i++) {
        if(s->players[i].id==from && s->players[i].local)source_present=1;
        if(s->players[i].id==to)target_present=1;
        if(!s->players[i].local)remotes++;
    }
    if(!source_present)return JKDP_DEPARTURE_BAD_SOURCE;
    if(to)return target_present?JKDP_DEPARTURE_TARGET_PRESENT:JKDP_DEPARTURE_DISCARD;
    return remotes?JKDP_DEPARTURE_LIVE_BROADCAST:JKDP_DEPARTURE_DISCARD;
}
#endif
