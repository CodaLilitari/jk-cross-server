/* Exercise the actual engine spawn selector, join allocator and serializer.
 * Collision and delivery are controlled fixtures; no game assets are needed.
 * This does not establish a live CTF match or transport interoperability. */
#include <assert.h>
#include <stdio.h>
#include "Dss/sithMulti.c"
#ifdef NDEBUG
#error Assertions must remain enabled for spawn/admission regressions
#endif

uint32_t jkPlayer_maxPlayers;
SithPlayer jkPlayer_playerInfos[JKPLAYER_NUM_INFOS];
int idx_13b4_related;
int32_t sithNet_MultiModeFlags, sithNet_isServer, sithNet_serverNetId;
int32_t sithNet_teamScore[5];
int jkGuiNetHost_bIsDedicated;
SithMessage sithComm_netMsgTmp;
const rdVector3 rdroid_zeroVector3={0};
static flex_t randomValue;
static int collisionDepth, sentCount;
static SithSector sectors[JKPLAYER_NUM_INFOS];

flex_t _frand(void) { return randomValue; }
char *_strncpy(char *out, const char *in, size_t size) { return strncpy(out,in,size); }
int stdString_WcharToChar(char *out, const char16_t *in, int maxChars)
{
    int i=0;
    for (;i<maxChars && in[i];i++) out[i]=(char)in[i];
    out[i]=0; return i;
}
int sithComm_SendMsgToPlayer(SithMessage *message, int to, int stream, int flags)
{
    (void)message; (void)to; (void)stream; (void)flags;
    sentCount++; return 1;
}
flex_t sithCollision_SearchForCollisions(SithSector *sector, SithThing *thing,
    const rdVector3 *from, const rdVector3 *direction, flex_t distance,
    flex_t radius, int flags)
{
    (void)thing; (void)from; (void)direction; (void)radius; (void)flags;
    assert(sector>=sectors && sector<sectors+JKPLAYER_NUM_INFOS);
    collisionDepth++; return distance;
}
SithCollision *sithCollision_PopStack(void) { return NULL; }
void sithCollision_DecreaseStackLevel(void) { assert(collisionDepth==1); collisionDepth--; }

static void authored_starts(unsigned count, int capacity)
{
    memset(jkPlayer_playerInfos,0,sizeof(jkPlayer_playerInfos));
    jkPlayer_maxPlayers=count; idx_13b4_related=capacity;
    for (unsigned i=0;i<count;i++) {
        jkPlayer_playerInfos[i].flags=2;
        jkPlayer_playerInfos[i].pInSector=&sectors[i];
    }
    /* The dedicated host already occupies the first ordinary record. */
    jkPlayer_playerInfos[0].playerNetId=1;
    sithNet_MultiModeFlags=MULTIMODEFLAG_TEAMS;
}

int main(void)
{
    SithThing self={0}; SithPlayer player={0};
    self.actorParams.pPlayer=&player; self.moveSize=0.065f;
    authored_starts(32,8);
    player.respawnMask=0x0000ffff;
    /* The old callback replaced the authored count with capacity. */
    jkPlayer_maxPlayers=8;
    assert(sithMulti_GetSpawnIdx(&self)==0);
    jkPlayer_maxPlayers=32;
    for (int i=0;i<16;i++) {
        randomValue=((flex_t)i+0.25f)/16.0f;
        assert(sithMulti_GetSpawnIdx(&self)==16+i);
    }
    puts("PASS stock CTF first-spawn mask uses all lobby starts 16..31 at session capacity 8");

    player.respawnMask=(int)0xffffff00u;
    for (int i=0;i<8;i++) {
        randomValue=((flex_t)i+0.25f)/8.0f;
        assert(sithMulti_GetSpawnIdx(&self)==i);
    }
    player.respawnMask=(int)0xffff00ffu;
    for (int i=0;i<8;i++) {
        randomValue=((flex_t)i+0.25f)/8.0f;
        assert(sithMulti_GetSpawnIdx(&self)==8+i);
    }
    assert(collisionDepth==0);
    puts("PASS red and gold stock respawn masks retain their distinct spawn ranges");

    for (int slot=1;slot<8;slot++) {
        assert(sithMulti_FindJoinSlot()==slot);
        jkPlayer_playerInfos[slot].playerNetId=100+slot;
    }
    assert(sithMulti_FindJoinSlot()==-1);
    assert(jkPlayer_playerInfos[8].flags==2 && !jkPlayer_playerInfos[8].playerNetId);
    jkPlayer_playerInfos[3].playerNetId=0;
    assert(sithMulti_FindJoinSlot()==3);
    jkPlayer_playerInfos[3].flags=0;
    assert(sithMulti_FindJoinSlot()==-1);
    assert(jkPlayer_maxPlayers==32);
    puts("PASS configured capacity includes host, rejects eighth human, reuses only eligible freed slots");

    authored_starts(4,8);
    for (int slot=1;slot<4;slot++) {
        assert(sithMulti_FindJoinSlot()==slot);
        jkPlayer_playerInfos[slot].playerNetId=slot+1;
    }
    assert(sithMulti_FindJoinSlot()==-1);
    idx_13b4_related=0; assert(sithMulti_FindJoinSlot()==-1);
    idx_13b4_related=-1; assert(sithMulti_FindJoinSlot()==-1);
    puts("PASS shorter maps and invalid capacity cannot allocate unavailable records");

    authored_starts(32,8);
    sithNet_isServer=jkGuiNetHost_bIsDedicated=1;
    sithNet_serverNetId=1;
    sithMulti_SyncPlayers(42,0);
    uint16_t synchronizedCount=0;
    memcpy(&synchronizedCount,(const uint8_t *)sithComm_netMsgTmp.pktData+8,sizeof(synchronizedCount));
    assert(sentCount==1 && sithComm_netMsgTmp.netMsg.cogMsgId==DSS_LEAVEJOIN);
    assert(synchronizedCount==32);
    assert(sithComm_netMsgTmp.netMsg.msg_size==10+32*4+5*2);
    assert(idx_13b4_related==8 && jkPlayer_maxPlayers==32);
    puts("PASS ordinary SyncPlayers serializes all 32 records without changing session capacity");
    return 0;
}
