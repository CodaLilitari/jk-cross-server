/* Real driver and Unix datagrams, with the existing fixture's inventory and collision. */
#include <sys/socket.h>
#include <unistd.h>
#include <time.h>
#define TEST_CUSTOM_CHAT_HANDLER
#define main existing_driver_regressions
#include "test_bot_driver.c"
#undef main
SithWorld *sithWorld_g_pCurrentWorld;
SithPlayer *sithPlayer_g_pLocalPlayer;
int32_t sithNet_isMulti;
int g_submodeFlags, playerThingIdx;
#ifndef TEST_INTEGRATED_HEARING
int jkBot_GetHearing(jkBotHearing *out) { (void)out; return 0; }
#endif
static int lines;
void sithConsole_AlertSound(void) {}
void sithConsole_PrintWString(const char16_t *s) { (void)s; }
int jk_snwprintf(char16_t *buffer,size_t size,const char16_t *format,...)
{ (void)format; if (size) *buffer=0; return 0; }
void sithMulti_SendChat(const char *s,int dest,int source)
{
    assert(!strcmp(s,"hold the bridge") && dest==-1 && source==0);
    lines++;
}
static SithWorld world;
static SithThing self;
static SithSector sector;
static int channel[2];
static unsigned char frame[513];
static uint32_t epoch, life;
static unsigned callbackAcks, callbackStates;
static int countFrame(const uint8_t *data,size_t size)
{
    assert(size>=20 && size<=512 && !memcmp(data,"JKCP",4));
    if (data[5]==CP_ACK) callbackAcks++;
    else { assert(data[5]==CP_STATE); callbackStates++; }
    return 0; /* a saturated consumer discards its copies */
}
static uint32_t word(const unsigned char *p)
{
    return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static void setword(unsigned char *p,uint32_t v)
{
    for (int i=0;i<4;i++) p[i]=v>>(8*i);
}
static double clockseconds(void)
{
    struct timespec t; assert(!clock_gettime(CLOCK_MONOTONIC,&t));
    return t.tv_sec+t.tv_nsec/1e9;
}
static void command(int kind,uint32_t seq,int bytes,double expiry)
{
    memset(frame,0,sizeof(frame)); memcpy(frame,"JKCP",4); frame[4]=1;
    frame[5]=kind; frame[6]=bytes; frame[7]=bytes>>8;
    setword(frame+8,epoch); setword(frame+12,life); setword(frame+16,seq);
    uint64_t bits; memcpy(&bits,&expiry,8);
    setword(frame+20,bits); setword(frame+24,bits>>32);
}
static void tick(void) { jkBot_Tick(0.033f); }
static void submit(size_t n)
{
    assert(send(channel[1],frame,n,0)==(ssize_t)n);
    tick();
}
static int receive(int kind)
{
    int n;
    while ((n=recv(channel[1],frame,sizeof(frame),MSG_DONTWAIT))>0) {
        assert(n>=20 && n<=512 && !memcmp(frame,"JKCP",4) && frame[4]==1);
        assert(n==20+frame[6]+256*frame[7]);
        if (frame[5]==kind) return n;
    }
    return 0;
}
static void ack(int kind,int status,int seq)
{
    assert(receive(2)==24 && word(frame+16)==(uint32_t)seq);
    assert(frame[20]==status && frame[21]==kind);
}
/* Earlier acknowledgement reads discard queued states; ask for a fresh one. */
static void refresh(void)
{
    int states=0;
    companion.nextState=0; tick();
    while (receive(1)) { epoch=word(frame+8); life=word(frame+12); states++; }
    assert(states);
}
/* TACTICS: deadline, flags, count, then count (identifier, float) records. */
static void tactics_command(uint32_t seq,int flags,int count)
{
    command(21,seq,10+5*count,clockseconds()+5);
    frame[28]=flags; frame[29]=count;
}
static void tactic(int slot,int id,float value)
{
    uint32_t bits; memcpy(&bits,&value,4);
    frame[30+5*slot]=id; setword(frame+31+5*slot,bits);
}
static void test_companion_tactics(void)
{
    refresh();
    float conc=BT(VALUE_CONC), rail=BT(VALUE_RAIL), run=BT(RUN);
    uint32_t revision=tactics.revision;
    tactics_command(20,0,2); tactic(0,BT_VALUE_CONC,25); tactic(1,BT_WATER_ENTRY_COST,9); submit(40);
    ack(21,0,20);
    assert(BT(VALUE_CONC)==25 && BT(WATER_ENTRY_COST)==9 && BT(VALUE_RAIL)==rail);
    assert(tactics.revision==revision+1);
    /* A second plan inside the commitment window is refused and changes nothing. */
    tactics_command(21,0,1); tactic(0,BT_VALUE_CONC,30); submit(35);
    ack(21,4,21); assert(frame[22]==CP_TOO_FAST && BT(VALUE_CONC)==25 && tactics.revision==revision+1);
    /* A retransmission is answered from the receipt, not applied again. */
    tactics_command(20,0,2); tactic(0,BT_VALUE_CONC,25); tactic(1,BT_WATER_ENTRY_COST,9);
    memcpy(frame+20,companion.replies[20%64].request,8); submit(40);
    ack(21,0,20); assert(tactics.revision==revision+1);
    bot.now+=BOT_TACTICS_COMMIT_SECONDS+0.1f;
    /* Malformed or out-of-range requests apply nothing and start no window. */
    tactics_command(22,0,1); tactic(0,BT_VALUE_CONC,99); submit(35); ack(21,1,22);
    tactics_command(23,0,1); tactic(0,BT_COUNT,1); submit(35); ack(21,1,23);
    tactics_command(24,0,2); tactic(0,BT_VALUE_CONC,20); tactic(1,BT_VALUE_CONC,21); submit(40); ack(21,1,24);
    tactics_command(25,0,1); frame[29]=2; tactic(0,BT_VALUE_CONC,20); submit(35); ack(21,1,25);
    tactics_command(26,4,1); tactic(0,BT_VALUE_CONC,20); submit(35); ack(21,1,26);
    tactics_command(27,0,0); submit(30); ack(21,1,27);
    float nan; uint32_t quiet=0x7fc00000u; memcpy(&nan,&quiet,4);
    tactics_command(28,0,1); tactic(0,BT_VALUE_CONC,nan); submit(35); ack(21,1,28);
    assert(BT(VALUE_CONC)==25 && tactics.revision==revision+1);
    tactics_command(29,0,1); tactic(0,BT_RUN,1-run); submit(35); ack(21,0,29);
    assert(BT(RUN)==1-run && BT(VALUE_CONC)==25 && tactics.revision==revision+2);
    /* RELEASE ends a policy, not the standing table. */
    command(18,30,8,clockseconds()+5); submit(28); ack(18,0,30);
    assert(BT(VALUE_CONC)==25 && BT(RUN)==1-run);
    /* A coach may adjust between lives; a strategy still needs a living bot. */
    bot.now+=BOT_TACTICS_COMMIT_SECONDS+0.1f;
    self.actorParams.health=0; refresh();
    command(16,31,28,clockseconds()+5); frame[28]=1; submit(48); ack(16,1,31);
    tactics_command(32,0,1); tactic(0,BT_GUN_FAR,4); submit(35); ack(21,0,32);
    assert(BT(GUN_FAR)==4);
    self.actorParams.health=100; refresh();
    /* Flag bit 0 restores the baseline before merging the records. */
    bot.now+=BOT_TACTICS_COMMIT_SECONDS+0.1f;
    tactics_command(33,1,1); tactic(0,BT_VALUE_RAIL,7); submit(35); ack(21,0,33);
    assert(BT(VALUE_CONC)==conc && BT(RUN)==run && BT(VALUE_RAIL)==7);
    bot.now+=BOT_TACTICS_COMMIT_SECONDS+0.1f;
    tactics_command(34,1,0); submit(30); ack(21,0,34);
    assert(BT(VALUE_RAIL)==rail);
    /* Bit 1 restores the legacy column instead; both bits at once are refused. */
    bot.now+=BOT_TACTICS_COMMIT_SECONDS+0.1f;
    tactics_command(35,3,1); tactic(0,BT_VALUE_CONC,20); submit(35); ack(21,1,35);
    tactics_command(36,2,0); submit(30); ack(21,0,36);
    for (int i=0;i<BT_COUNT;i++) assert(tactics.value[i]==botTacticSpecs[i].legacy);
    bot.now+=BOT_TACTICS_COMMIT_SECONDS+0.1f;
    tactics_command(37,1,0); submit(30); ack(21,0,37);
    assert(BT(VALUE_RAIL)==rail && BT(RUN)==run);
    /* The largest request fits the receipt cache; one more record does not. */
    bot.now+=BOT_TACTICS_COMMIT_SECONDS+0.1f;
    tactics_command(38,0,BOT_TACTICS_WIRE_PAIRS);
    for (int i=0;i<BOT_TACTICS_WIRE_PAIRS;i++) tactic(i,i,botTacticSpecs[i].legacy);
    submit(30+5*BOT_TACTICS_WIRE_PAIRS); ack(21,0,38);
    tactics_command(39,0,BOT_TACTICS_WIRE_PAIRS+1);
    for (int i=0;i<=BOT_TACTICS_WIRE_PAIRS;i++) tactic(i,i,botTacticSpecs[i].legacy);
    submit(35+5*BOT_TACTICS_WIRE_PAIRS); assert(!receive(2) && "an oversized frame is ignored");
    puts("PASS companion tactics merge, commitment window, receipts, strict rejection, reset flag and adjustment between lives");
}
int main(void)
{
    assert(socketpair(AF_UNIX,SOCK_DGRAM,0,channel)==0);
    char fd[32]; snprintf(fd,sizeof(fd),"%d",channel[0]); setenv("JK_BOT_COMPANION_FD",fd,1);
    sithWorld_g_pCurrentWorld=&world; sithPlayer_g_pLocalPlayer=&jkPlayer_playerInfos[0];
    self.type=SITH_THING_PLAYER; self.sector=&sector; self.guid=65; self.signature=2;
    self.actorParams.health=100; self.actorParams.pPlayer=sithPlayer_g_pLocalPlayer;
    sithPlayer_g_pLocalPlayer->pLocalPlayer=&self; sithPlayer_g_pLocalPlayer->flags=1;
    sithPlayer_g_pLocalPlayer->playerNetId=73; jkPlayer_maxPlayers=1;
    sithPlayer_g_pLocalPlayerThing=&self; sithNet_isMulti=1;
    jkBot_Configure("Bot_Test","ky.3do"); jkBot_OnJoined(); tick();
    assert(receive(1)==164 && "a joined companion must publish a complete state");
    epoch=word(frame+8); life=word(frame+12);
    assert(epoch && life && word(frame+24)==73 && word(frame+88)==UINT32_MAX);
    double chatExpiry=clockseconds()+5;
    command(17,1,23,chatExpiry); memcpy(frame+28,"hold the bridge",15); submit(43);
    ack(17,0,1); assert(lines==1);
    command(17,1,23,chatExpiry); memcpy(frame+28,"hold the bridge",15); submit(43);
    ack(17,0,1); assert(lines==1);
    command(17,1,23,chatExpiry+0.1); memcpy(frame+28,"hold the bridge",15); submit(43);
    ack(17,1,1); assert(lines==1);
    command(17,2,16,clockseconds()+5); memcpy(frame+28,"  AdMin ",8); submit(36); ack(17,1,2);
    command(17,3,23,clockseconds()+5); memcpy(frame+28,"hold the bridge",15); submit(43);
    ack(17,4,3); assert(lines==1);
    SithThing pickup={0};
    pickup.type=SITH_THING_ITEM; pickup.sector=&sector; strcpy(pickup.aName,"shieldrecharge");
    world.aThings=&pickup; world.numThings=0; world.numThingsLoaded=1;
    flex_t ordinaryShield=Bot_ItemValue(&self,0); assert(ordinaryShield>0);
    for (int w=2;w<=3;w++) {
        sithPlayer_g_pLocalPlayer->aItems[w].amount=1;
        sithPlayer_g_pLocalPlayer->aItems[w].state=SITHINVENTORY_ITEM_AVAILABLE;
    }
    sithPlayer_g_pLocalPlayer->aItems[11].amount=5;
    sithPlayer_g_pLocalPlayer->curWeaponID=2;
    command(16,4,28,clockseconds()+5); frame[28]=2; frame[29]=3; frame[30]=60; submit(48);
    ack(16,0,4);
    assert(Bot_ItemValue(&self,0)>ordinaryShield && "resource strategy must favor a useful requested shield");
    bot.nextSelect=0; memset(bot.keys,0,sizeof(bot.keys)); Bot_SelectWeapon(&self,6);
    assert(bot.keys[INPUT_FUNC_SELECT1+2] && "ordinary weapon selection must consume the legal preference");
    bot.sabersOnly=1; bot.nextSelect=0; memset(bot.keys,0,sizeof(bot.keys)); Bot_SelectWeapon(&self,6);
    assert(!bot.keys[INPUT_FUNC_SELECT1+2]); bot.sabersOnly=0;
    command(18,5,8,clockseconds()-1); submit(28); ack(18,2,5);
    command(18,6,8,clockseconds()+5); setword(frame+12,life+1); submit(28); ack(18,3,6);
    command(18,7,8,clockseconds()+5); submit(28); ack(18,0,7);
    assert(Bot_ItemValue(&self,0)==ordinaryShield);
    SithMessage chat={0};
    chat.netMsg.idx=91; chat.netMsg.msg_size=18;
    chat.pktData[0]=(uint32_t)-1; chat.pktData[1]=1; chat.pktData[2]=6;
    memcpy(&chat.pktData[3],"hello",6);
    jkPlayer_maxPlayers=2; jkPlayer_playerInfos[1].flags=1; jkPlayer_playerInfos[1].playerNetId=91;
    assert(sithMulti_ProcessChat(&chat));
    assert(receive(3)==33 && word(frame+24)==91 && !memcmp(frame+28,"hello",5));
    chat.pktData[0]=0; assert(sithMulti_ProcessChat(&chat)); assert(!receive(3));
    chat.pktData[0]=(uint32_t)-1; chat.netMsg.idx=96;
    assert(sithMulti_ProcessChat(&chat)); assert(!receive(3));
    chat.netMsg.idx=91; memcpy(&chat.pktData[3],"AdMiN",6);
    assert(sithMulti_ProcessChat(&chat)); assert(!receive(3));
    chat.netMsg.msg_size=13; assert(!sithMulti_ProcessChat(&chat));
    command(16,8,28,clockseconds()+0.05); frame[28]=3; submit(48); ack(16,0,8);
    assert(Bot_EngagementForward(0,2)<0);
    struct timespec delay={0,85000000}; nanosleep(&delay,NULL);
    tick(); assert(Bot_EngagementForward(0,2)==0);
    command(16,9,28,clockseconds()+5); frame[28]=1; submit(48); ack(16,0,9);
    assert(Bot_EngagementForward(0,2)>0);
    self.signature++; tick(); assert(Bot_EngagementForward(0,2)==0);
    command(17,10,23,clockseconds()+5); memcpy(frame+28,"hold the bridge",15); submit(43);
    ack(17,3,10); assert(lines==1);
    test_companion_tactics();
    jkBotCompanion_SetTransport(countFrame);
    command(18,11,8,clockseconds()+5);
    assert(!jkBotCompanion_Receive(frame,513));
    for (int i=0;i<16;i++) assert(jkBotCompanion_Receive(frame,28));
    assert(!jkBotCompanion_Receive(frame,28));
    tick(); assert(callbackAcks==8 && callbackStates==1);
    tick(); assert(callbackAcks==16);
    assert(jkBotCompanion_Receive(frame,28));
    /* Saturate native egress entirely without draining; gameplay advances. */
    jkBotCompanion_SetTransport(NULL); tick();
    double start=clockseconds();
    for (int i=0;i<2000;i++) jkBot_ObserveChat(-1,1,91,"a bounded event");
    assert(clockseconds()-start<2.0);
    puts("PASS native and portable transport, applied strategy, expiry, identity, bounded backpressure and public chat");
    return 0;
}
