/* SPDX-License-Identifier: MIT
 * Session identity history and ordered ordinary DirectPlay surrogate renewal.
 * This changes transport membership, never Sith packet sequence numbers.
 */
#ifndef JKDP_SURROGATE_POOL_H
#define JKDP_SURROGATE_POOL_H

#include <stdint.h>
#include <string.h>

#ifndef JKDP_IDENTITY_LIMIT
#define JKDP_IDENTITY_LIMIT 65536u
#endif
#define JKDP_POOL_LIMIT 15u

struct jkdp_identity_record {
    uint32_t id, replacement, request;
    int completed;
};
struct jkdp_identity_history {
    unsigned count;
    struct jkdp_identity_record records[JKDP_IDENTITY_LIMIT];
};
struct jkdp_pool_rotation {
    uint32_t queued[JKDP_POOL_LIMIT];
    unsigned count, slot;
    uint32_t old_id, new_id, request, next_request;
};

static inline int jkdp_history_index(const struct jkdp_identity_history *history, uint32_t id) {
    unsigned i;
    for(i=0;i<history->count;i++)if(history->records[i].id==id)return (int)i;
    return -1;
}
static inline int jkdp_history_add(struct jkdp_identity_history *history, uint32_t id) {
    if(id<65 || id>=0xfffffffeu || history->count>=JKDP_IDENTITY_LIMIT ||
       jkdp_history_index(history,id)>=0)return 0;
    history->records[history->count++]=(struct jkdp_identity_record){id,0,0,0};
    return 1;
}
static inline int jkdp_pool_index(const uint32_t *pool,unsigned count,uint32_t id) {
    unsigned i;
    for(i=0;i<count;i++)if(pool[i]==id)return (int)i;
    return -1;
}
static inline int jkdp_rotation_enqueue(struct jkdp_pool_rotation *rotation,
        const struct jkdp_identity_history *history,const uint32_t *pool,unsigned count,uint32_t id) {
    unsigned i;int previous;
    if(!id || count>JKDP_POOL_LIMIT)return 0;
    if(rotation->old_id==id)return 1;
    for(i=0;i<rotation->count;i++)if(rotation->queued[i]==id)return 1;
    if(jkdp_pool_index(pool,count,id)<0) {
        previous=jkdp_history_index(history,id);
        return previous>=0 && history->records[previous].completed;
    }
    if(rotation->count>=JKDP_POOL_LIMIT)return 0;
    rotation->queued[rotation->count++]=id;
    return 1;
}
static inline int jkdp_rotation_begin(struct jkdp_pool_rotation *rotation,
        const uint32_t *pool,unsigned count) {
    int slot;
    if(rotation->old_id || !rotation->count)return 0;
    slot=jkdp_pool_index(pool,count,rotation->queued[0]);
    if(slot<0)return -1;
    rotation->old_id=rotation->queued[0];rotation->slot=(unsigned)slot;
    --rotation->count;
    memmove(rotation->queued,rotation->queued+1,rotation->count*sizeof(rotation->queued[0]));
    return 1;
}
static inline int jkdp_rotation_created(struct jkdp_pool_rotation *rotation,
        struct jkdp_identity_history *history,uint32_t *pool,unsigned count,uint32_t new_id) {
    int previous;
    if(!rotation->old_id || rotation->new_id || rotation->slot>=count ||
       pool[rotation->slot]!=rotation->old_id || rotation->next_request==0xffffffffu)return 0;
    previous=jkdp_history_index(history,rotation->old_id);
    if(previous<0 || !jkdp_history_add(history,new_id))return 0;
    rotation->new_id=new_id;rotation->request=++rotation->next_request;
    pool[rotation->slot]=new_id;
    history->records[previous].replacement=new_id;
    history->records[previous].request=rotation->request;
    return 1;
}
static inline int jkdp_rotation_ack(struct jkdp_pool_rotation *rotation,
        struct jkdp_identity_history *history,uint32_t old_id,uint32_t request,uint32_t new_id) {
    int previous=jkdp_history_index(history,old_id);
    struct jkdp_identity_record *record;
    if(previous<0 || !request)return 0;
    record=&history->records[previous];
    if(record->replacement!=new_id || record->request!=request)return 0;
    if(record->completed)return 1;
    if(rotation->old_id!=old_id || rotation->request!=request || rotation->new_id!=new_id)return 0;
    record->completed=1;
    rotation->old_id=rotation->new_id=rotation->request=0;
    return 1;
}

#endif
