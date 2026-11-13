/* SPDX-License-Identifier: MIT */
#define JKDP_IDENTITY_LIMIT 32u
#include "surrogate_pool.h"
#include <assert.h>
#include <stdio.h>

static struct jkdp_identity_history history;
static struct jkdp_pool_rotation rotation;
static uint32_t ids[JKDP_POOL_LIMIT];

static void setup(unsigned count) {
    unsigned i;
    memset(&history,0,sizeof(history));memset(&rotation,0,sizeof(rotation));
    assert(jkdp_history_add(&history,90)); /* Physical DirectPlay host. */
    for(i=0;i<count;i++){ids[i]=100+i;assert(jkdp_history_add(&history,ids[i]));}
}
static void acknowledged(uint32_t fresh,unsigned count) {
    uint32_t old=rotation.old_id,request;
    assert(jkdp_rotation_created(&rotation,&history,ids,count,fresh));
    request=rotation.request;
    assert(jkdp_rotation_ack(&rotation,&history,old,request,fresh));
    assert(jkdp_rotation_ack(&rotation,&history,old,request,fresh));
}
int main(void) {
    uint32_t request;unsigned i;
    setup(2);
    assert(!jkdp_history_add(&history,90));
    assert(!jkdp_history_add(&history,0));
    assert(!jkdp_history_add(&history,0xfffffffeu));
    assert(jkdp_history_add(&history,500)); /* A now-departed retail identity. */
    assert(jkdp_rotation_enqueue(&rotation,&history,ids,2,100));
    assert(jkdp_rotation_begin(&rotation,ids,2)==1);
    assert(!jkdp_rotation_created(&rotation,&history,ids,2,90));
    assert(!jkdp_rotation_created(&rotation,&history,ids,2,100));
    assert(!jkdp_rotation_created(&rotation,&history,ids,2,101));
    assert(!jkdp_rotation_created(&rotation,&history,ids,2,500));
    assert(ids[0]==100 && ids[1]==101);
    acknowledged(600,2);

    setup(3);
    assert(jkdp_rotation_enqueue(&rotation,&history,ids,3,100));
    assert(jkdp_rotation_enqueue(&rotation,&history,ids,3,101));
    assert(jkdp_rotation_enqueue(&rotation,&history,ids,3,100));
    assert(rotation.count==2);
    assert(jkdp_rotation_begin(&rotation,ids,3)==1 && rotation.old_id==100);
    assert(jkdp_rotation_created(&rotation,&history,ids,3,200));
    assert(!jkdp_rotation_begin(&rotation,ids,3));
    assert(ids[1]==101 && ids[2]==102);
    request=rotation.request;
    assert(!jkdp_rotation_ack(&rotation,&history,101,request,200));
    assert(!jkdp_rotation_ack(&rotation,&history,100,request+1,200));
    assert(!jkdp_rotation_ack(&rotation,&history,100,request,201));
    assert(rotation.old_id==100);
    assert(jkdp_rotation_ack(&rotation,&history,100,request,200));
    assert(jkdp_rotation_begin(&rotation,ids,3)==1 && rotation.old_id==101);
    acknowledged(201,3);
    assert(ids[0]==200 && ids[1]==201 && ids[2]==102);
    assert(jkdp_rotation_enqueue(&rotation,&history,ids,3,100));
    assert(rotation.count==0); /* Duplicate retirement never destroys the new seat. */

    setup(2);
    assert(jkdp_rotation_enqueue(&rotation,&history,ids,2,100));
    assert(jkdp_rotation_begin(&rotation,ids,2)==1);
    assert(jkdp_rotation_created(&rotation,&history,ids,2,200));
    request=rotation.request;
    assert(jkdp_rotation_enqueue(&rotation,&history,ids,2,200));
    assert(jkdp_rotation_enqueue(&rotation,&history,ids,2,101));
    assert(rotation.count==2); /* Retirement while the preceding ACK is in flight. */
    assert(jkdp_rotation_ack(&rotation,&history,100,request,200));
    assert(jkdp_rotation_begin(&rotation,ids,2)==1 && rotation.old_id==200);
    acknowledged(201,2);
    assert(jkdp_rotation_begin(&rotation,ids,2)==1 && rotation.old_id==101);
    acknowledged(202,2);
    assert(ids[0]==201 && ids[1]==202);

    setup(JKDP_POOL_LIMIT);
    for(i=0;i<JKDP_POOL_LIMIT;i++)assert(jkdp_rotation_enqueue(&rotation,&history,ids,JKDP_POOL_LIMIT,ids[i]));
    assert(rotation.count==JKDP_POOL_LIMIT);
    assert(!jkdp_rotation_enqueue(&rotation,&history,ids,JKDP_POOL_LIMIT,999));
    for(i=0;i<JKDP_POOL_LIMIT;i++) {
        assert(jkdp_rotation_begin(&rotation,ids,JKDP_POOL_LIMIT)==1);
        assert(rotation.old_id==100+i);acknowledged(200+i,JKDP_POOL_LIMIT);
    }
    assert(!rotation.count && !rotation.old_id);

    setup(1);
    for(i=history.count;i<JKDP_IDENTITY_LIMIT;i++)assert(jkdp_history_add(&history,1000+i));
    assert(jkdp_rotation_enqueue(&rotation,&history,ids,1,100));
    assert(jkdp_rotation_begin(&rotation,ids,1)==1);
    assert(!jkdp_rotation_created(&rotation,&history,ids,1,9999));
    assert(history.count==JKDP_IDENTITY_LIMIT && ids[0]==100);

    setup(1);
    assert(!jkdp_rotation_enqueue(&rotation,&history,ids,1,90));
    assert(!jkdp_rotation_enqueue(&rotation,&history,ids,1,999));
    assert(!jkdp_rotation_ack(&rotation,&history,100,1,200));
    assert(jkdp_rotation_enqueue(&rotation,&history,ids,1,100));
    assert(jkdp_rotation_begin(&rotation,ids,1)==1);
    rotation.next_request=0xffffffffu;
    assert(!jkdp_rotation_created(&rotation,&history,ids,1,200));
    assert(ids[0]==100); /* Correlation exhaustion also fails closed. */
    puts("surrogate pool: 6 groups passed (freshness, ordering, ACKs, concurrent retirement, lifetime bound, invalid events)");
    return 0;
}
