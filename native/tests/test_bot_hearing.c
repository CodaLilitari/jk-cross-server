/* Exercise the actual bot's view cone, sensory memory, and ordinary input. */
#define main driver_fixture_main
#include "test_bot_driver.c"
#undef main
#include "World/sithSoundClass.h"
#include "Devices/sithSoundMixer.h"
#include "Win95/stdSound.h"
flex_t stdMath_Clamp(flex_t value, flex_t lo, flex_t hi) { return Bot_Clamp(value,lo,hi); }
void stdSound_BufferSetVolume(stdSound_buffer_t *sound, flex_t vol) { (void)sound; (void)vol; }
int sithSoundMixer_bOpened, sithSoundMixer_numSoundsAvailable;
uint32_t sithTime_g_msecGameTime;
SithCamera *sithCamera_g_pCurCamera;
void rdVector_Zero3(rdVector3 *v) { *v=(rdVector3){0}; }


SithWorld *sithWorld_g_pCurrentWorld;
static SithWorld level;
static SithThing things[3];
static SithSector sectors[2];
static sithSound sample;

static void reset_scene(void)
{
    memset(&level,0,sizeof(level));
    memset(things,0,sizeof(things));
    memset(sectors,0,sizeof(sectors));
    memset(jkPlayer_playerInfos,0,sizeof(jkPlayer_playerInfos));
    memset(&nav,0,sizeof(nav));
    jkBot_Configure("Bot_Ears","ky.3do");
    jkBot_OnJoined();
    bot.world=sithWorld_g_pCurrentWorld=&level;
    level.aThings=things;
    level.numThings=2;
    level.numThingsLoaded=3;
    level.aSectors=sectors;
    level.numSectors=2;
    jkPlayer_maxPlayers=2;
    for (int i=0;i<2;i++) {
        SithPlayer *p=&jkPlayer_playerInfos[i];
        p->flags=1; p->playerNetId=10+i; p->pLocalPlayer=&things[i];
        things[i].type=SITH_THING_PLAYER; things[i].idx=i; things[i].guid=40+i;
        things[i].signature=50+i; things[i].sector=&sectors[0];
        things[i].actorParams.pPlayer=p; things[i].actorParams.health=100;
    }
    sithPlayer_g_pLocalPlayerThing=things;
    things[0].orient.lvec.y=things[0].orient.rvec.x=1;
    things[1].position=(rdVector3){0.12f,-0.40f,0};
    bot.now=2; bot.fistsPeace=0; bot.wasDead=0;
    testLOS=1;
    strcpy(sample.sound_fname,"walk.wav");
}

static void cue(SithThing *t,int mode,int flags)
{
    sithSoundMixer_PlaySpatial(&sample,t,&t->position,t->sector,1,.5f,2.5f,flags,mode);
}

static void test_portals(void)
{
    reset_scene();
    /* A small doorway to the left of the direct listener/source ray. */
    rdVector3 vertices[]={{-.45f,.5f,-.1f},{-.25f,.5f,-.1f},{-.25f,.5f,.15f},{-.45f,.5f,.15f}};
    int indices[]={0,1,2,3};
    SithSurface face={0};
    SithSurfaceAdjoin adj[2]={{0}};
    face.surfaceInfo.face.numVertices=4; face.surfaceInfo.face.vertexPosIdx=indices;
    face.surfaceInfo.face.normal.y=1;
    level.aVertices=vertices; level.numVertices=4;
    for (int i=0;i<2;i++) {
        sectors[i].adjoins=&adj[i]; adj[i].sector=&sectors[1-i];
        adj[i].mirror=&adj[1-i]; adj[i].surface=&face;
    }
    SithThing *remote=things+1;
    remote->sector=sectors+1; remote->position=(rdVector3){.30f,1,0};
    testLOS=0; bot.elite=1;
    jkBotHearing heard;
    cue(remote,JKBOT_SOUND_MUZZLE,SITHSOUNDFLAG_FOLLOWSTHING);
    assert(!jkBot_GetHearing(&heard));
    adj[0].flags=adj[1].flags=SITHSURF_ADJOIN_ALLOW_SOUND;
    cue(remote,JKBOT_SOUND_MUZZLE,SITHSOUNDFLAG_FOLLOWSTHING);
    assert(jkBot_GetHearing(&heard) && heard.kind==2 && heard.position.x<0);
    assert(heard.uncertainty>1 && heard.strength>0 && heard.strength<0.62f);
    assert(Bot_UpdateTarget(things)==NULL);
    bot.now+=.14f;
    assert(Bot_InvestigateSound(things) && !bot.keys[INPUT_FUNC_FIRE1] && !bot.keys[INPUT_FUNC_FIRE2]);
    puts("PASS closed acoustic doorway rejects muzzle fire; open doorway turns toward the opening with LOS blocked");
}

static void test_identification_lifetime(void)
{
    reset_scene();
    jkBotHearing heard;
    strcpy(sample.sound_fname,"ForceThrow01.WAV");
    cue(things,JKBOT_SOUND_RAW,SITHSOUNDFLAG_FOLLOWSTHING);
    assert(!jkBot_GetHearing(&heard));
    cue(things+1,JKBOT_SOUND_RAW,SITHSOUNDFLAG_FOLLOWSTHING);
    assert(jkBot_GetHearing(&heard) && heard.kind==4);
    rdVector3 anchor=heard.position;
    things[1].position.x+=4; bot.now+=.12f;
    assert(jkBot_GetHearing(&heard) && !memcmp(&anchor,&heard.position,sizeof(anchor)));
    jkPlayer_playerInfos[1].playerNetId++;
    assert(!jkBot_GetHearing(&heard));
    things[1].position.x=0; cue(things+1,JKBOT_SOUND_RAW,0);
    things[1].signature++;
    assert(!jkBot_GetHearing(&heard));
    cue(things+1,JKBOT_SOUND_RAW,0); bot.now+=2;
    assert(!jkBot_GetHearing(&heard));
    cue(things+1,JKBOT_SOUND_RAW,0); things[0].flags|=SITH_TF_DEAD;
    assert(!jkBot_GetHearing(&heard)); things[0].flags=0;
    assert(!jkBot_GetHearing(&heard));
    cue(things+1,JKBOT_SOUND_RAW,0); things[0].signature++;
    assert(!jkBot_GetHearing(&heard));
    cue(things+1,JKBOT_SOUND_RAW,0); jkBot_OnJoined();
    assert(!jkBot_GetHearing(&heard));
    puts("PASS own sounds ignored; Force/arrival remains ambiguous, fixed in memory, expires and clears on slot/life/join changes");
}

static void test_projectiles(void)
{
    reset_scene();
    jkBotHearing heard;
    SithThing *weapon=things+2;
    weapon->idx=2; weapon->signature=80; weapon->type=SITH_THING_WEAPON;
    weapon->sector=sectors; weapon->position=(rdVector3){0,3,0};
    int loop=SITHSOUNDFLAG_FOLLOWSTHING|SITHSOUNDFLAG_LOOP;
    cue(weapon,SITH_SC_CREATE,loop);
    assert(!jkBot_GetHearing(&heard));
    weapon->position.y=.9f; bot.now+=.1f;
    Bot_UpdateAudioLoops(things);
    assert(jkBot_GetHearing(&heard) && heard.kind==3 && heard.strength>.7f);
    sithPlayingSound channel={0};
    channel.thing=weapon; channel.sound=&sample; channel.flags=loop; channel.vol_2=1;
    sithSoundMixer_FadeVolume(&channel,0,.20f);
    bot.now+=1; Bot_UpdateAudioLoops(things);
    assert(!jkBot_GetHearing(&heard));
    sithSoundMixer_SetVolume(&channel,1); bot.now+=.1f; Bot_UpdateAudioLoops(things);
    assert(jkBot_GetHearing(&heard) && heard.kind==3);
    sithSoundClass_StopSound(weapon,&sample);
    bot.now+=1; Bot_UpdateAudioLoops(things); assert(!jkBot_GetHearing(&heard));
    /* A recycled weapon slot is silent unless its own new sound is requested. */
    cue(weapon,SITH_SC_CREATE,loop); weapon->signature++; bot.now+=1;
    Bot_UpdateAudioLoops(things); assert(!jkBot_GetHearing(&heard));
    weapon->pParent=things; weapon->parentSignature=things->signature;
    cue(weapon,SITH_SC_CREATE,loop); assert(!jkBot_GetHearing(&heard));
    weapon->pParent=NULL;
    jkBot_ObserveSound(weapon,sectors,&weapon->position,NULL,1,.5f,2.5f,loop,SITH_SC_CREATE);
    assert(!jkBot_GetHearing(&heard));
    cue(weapon,SITH_SC_CREATE,SITHSOUNDFLAG_AMBIENT_NOPAN);
    assert(!jkBot_GetHearing(&heard));
    puts("PASS audible projectile can enter range after launch; stops, stale slots, silent and own weapons and ambience stay quiet");
}

static void test_elite_acquisition(void)
{
    reset_scene(); bot.elite=1;
    jkBotHearing heard;
    assert(!jkBot_GetHearing(&heard));
    assert(Bot_UpdateTarget(things)==things+1);
    assert(bot.nextScan-bot.now<=.061f && bot.reactionUntil-bot.now>=.079f && bot.reactionUntil-bot.now<=.121f);
    assert(!jkBot_GetHearing(&heard));
    /* The old target identity cannot ride the cached scan into a reused slot. */
    things[1].signature++;
    assert(Bot_UpdateTarget(things)==NULL);
    things[1].position.y=-29.0f;
    bot.now+=.065f;
    assert(Bot_UpdateTarget(things)==things+1);
    things[0].actorParams.flags|=SITH_AF_BLIND; things[1].jkFlags|=JKFLAG_PERSUASION;
    assert(!Bot_EnemyAllowed(things,1) && Bot_KineticEnemyAllowed(things,1));
    assert(Bot_UpdateTarget(things)==things+1 && !jkBot_GetHearing(&heard));
    testLOS=0; assert(Bot_UpdateTarget(things)==NULL);
    puts("PASS elite 360-degree acquisition in 60ms scan / 80–120ms reaction, independent of hearing; no cached target through a wall or slot reuse");
}

static void test_elite_route(void)
{
    reset_scene();
    setenv("JK_BOT_ELITE","1",1);
    jkBot_Configure("Bot_Route","ky.3do");
    unsetenv("JK_BOT_ELITE");
    bot.world=&level; bot.joined=1; bot.now=5; bot.fistsPeace=0;
    things[1].sector=&sectors[1];
    things[1].position=(rdVector3){3.1f,0,0};
    testLOS=0;
    /* A short alternate wander goal (1), an around-corner route (2 -> 3),
       and an isolated node (4) even closer to the enemy. */
    bot.nNodes=5;
    for (int i=0;i<5;i++) {
        bot.nodes[i].item=-1;
        bot.nodes[i].sector=i>=3 ? &sectors[1] : sectors;
        bot.nodes[i].pos.x=(flex_t)i;
    }
    bot.nodes[1].pos.x=-.3f; bot.nodes[4].pos.x=3.1f;
    bot.nodes[0].nEdges=2; bot.nodes[0].edges[0]=(BotEdge){1,.3f,BOT_ROUTE_WALK};
    bot.nodes[0].edges[1]=(BotEdge){2,2,BOT_ROUTE_WALK};
    bot.nodes[2].nEdges=1; bot.nodes[2].edges[0]=(BotEdge){3,1,BOT_ROUTE_WALK};
    bot.goal=1; bot.goalSetAt=4;
    assert(!Bot_UpdateTarget(things));
    Bot_Plan(things);
    assert(bot.goal==3 && bot.routeCount==2 && bot.route[0]==2 && bot.route[1]==3);
    rdVector3 before=things[0].position;
    Bot_Navigate(things);
    assert(bot.axes[INPUT_FUNC_TURN]!=0 && Bot_Distance(before,things[0].position)==0);
    assert(!bot.keys[INPUT_FUNC_FIRE1] && !bot.keys[INPUT_FUNC_FIRE2] && bot.targetSlot==-1);
    assert(bot.nextPlan-bot.now<.401f && nav.pursuitNet==jkPlayer_playerInfos[1].playerNetId);
    jkPlayer_playerInfos[1].playerNetId++;
    Bot_CheckPursuit(things); assert(bot.goal==-1 && !nav.pursuitNet && !bot.routeCount);
    sithNet_MultiModeFlags=MULTIMODEFLAG_TEAMS;
    Bot_Plan(things); assert(!nav.pursuitNet);
    sithNet_MultiModeFlags=0; things[1].flags|=SITH_TF_DEAD;
    Bot_Plan(things); assert(!nav.pursuitNet);
    things[1].flags=0; bot.now+=1; Bot_Plan(things); assert(nav.pursuitNet);
    things[0].actorParams.health=30; Bot_CheckPursuit(things);
    Bot_Plan(things); assert(!nav.pursuitNet);
    things[0].actorParams.health=100; companion.policy.mode=CP_RESOURCE;
    Bot_Plan(things); assert(!nav.pursuitNet);
    puts("PASS elite silently pursues around a wall through reachable anchors, with no firing target");
}

/* The v1 hub establishes an epoch only from STATE. Inspect the emitted
   records in transport order, without the fixture's kind-filtered receive. */
static struct {
    uint32_t world,life,seq;
    int kind;
} epochFrames[16];
static unsigned epochCount;

static int capture_epoch_frame(const uint8_t *frame,size_t size)
{
    assert(size>=20 && epochCount<16);
    epochFrames[epochCount].kind=frame[5];
    epochFrames[epochCount].world=Companion_Word(frame+8);
    epochFrames[epochCount].life=Companion_Word(frame+12);
    epochFrames[epochCount].seq=Companion_Word(frame+16);
    epochCount++;
    return 1;
}

static void test_companion_epoch_events(void)
{
    reset_scene();
    sithNet_isMulti=1; playerThingIdx=0; bot.graphDone=1;
    sithPlayer_g_pLocalPlayer=&jkPlayer_playerInfos[0];
    epochCount=0;
    jkBotCompanion_SetTransport(capture_epoch_frame);
    cue(things+1,JKBOT_SOUND_MUZZLE,SITHSOUNDFLAG_FOLLOWSTHING);
    jkBot_Tick(.02f);
    if (epochCount!=2 || epochFrames[0].kind!=CP_STATE || epochFrames[1].kind!=CP_SOUND)
        fprintf(stderr,"epoch fixture received %u records, first kinds %d then %d\n",epochCount,epochFrames[0].kind,epochFrames[1].kind);
    assert(epochCount==2 && epochFrames[0].kind==CP_STATE && epochFrames[1].kind==CP_SOUND &&
           "a world with an immediately audible cue must establish its epoch before SOUND");
    uint32_t world=epochFrames[0].world, life=epochFrames[0].life;
    assert(world && life && epochFrames[1].world==world && epochFrames[1].life==life);
    companion.nextState=1e30; /* Keep the regular publication deadline pending. */
    jkBot_Tick(.02f);
    assert(epochCount==2 && "ordinary frames retain the 5 Hz publication budget");

    things[0].actorParams.health=0;
    jkBot_Tick(.02f);
    jkBot_ObserveChat(-1,1,11,"between ticks");
    assert(epochCount==4 && epochFrames[2].kind==CP_STATE && epochFrames[3].kind==CP_CHAT);
    life=Companion_Next(life);
    assert(epochFrames[2].life==life && epochFrames[3].life==life);

    things[0].actorParams.health=100;
    cue(things+1,JKBOT_SOUND_MUZZLE,SITHSOUNDFLAG_FOLLOWSTHING);
    jkBot_Tick(.02f);
    assert(epochCount==6 && epochFrames[4].kind==CP_STATE && epochFrames[5].kind==CP_SOUND);
    life=Companion_Next(life);
    assert(epochFrames[4].life==life && epochFrames[5].life==life && epochFrames[5].world==world);

    SithWorld nextLevel=level;
    sithWorld_g_pCurrentWorld=&nextLevel;
    jkBot_Tick(.02f);
    jkBot_ObserveChat(-1,1,11,"new world");
    assert(epochCount==8 && epochFrames[6].kind==CP_STATE && epochFrames[7].kind==CP_CHAT);
    for (unsigned i=6;i<8;i++)
        assert(epochFrames[i].world==Companion_Next(world) && epochFrames[i].life==1);
    for (unsigned i=1;i<epochCount;i++)
        assert(epochFrames[i].seq==Companion_Next(epochFrames[i-1].seq));
    jkBotCompanion_SetTransport(NULL);
    bot.world=sithWorld_g_pCurrentWorld=NULL;
    puts("PASS companion publishes new world, death and respawn states before hearing/chat while preserving continuous event sequence and ordinary state rate");
}

int main(void)
{
    reset_scene();
    assert(Bot_UpdateTarget(things)==NULL);
    puts("PASS silent opponent directly behind remains unseen");
    jkBotHearing heard;
    assert(!jkBot_GetHearing(&heard));
    sithSoundClass klass={0};
    sithSoundClassEntry entry={0};
    entry.sound=&sample; entry.minRadius=.5f; entry.maxRadius=2.5f; entry.maxVolume=1;
    entry.playflags=SITHSOUNDFLAG_ABSOLUTE;
    klass.entries[SITH_SC_LWALKHARD]=&entry; things[1].pSoundClass=&klass;
    assert(!sithSoundMixer_bOpened && !sithCamera_g_pCurCamera);
    sithSoundClass_PlayModeFirst(things+1,SITH_SC_LWALKHARD);
    assert(jkBot_GetHearing(&heard) && heard.kind==1 && heard.uncertainty>0);
    assert(Bot_UpdateTarget(things)==NULL);
    bot.now+=.07f;
    assert(Bot_InvestigateSound(things) && bot.axes[INPUT_FUNC_TURN]!=0);
    assert(!bot.keys[INPUT_FUNC_FIRE1] && !bot.keys[INPUT_FUNC_FIRE2]);
    puts("PASS audible rear footstep turns the bot within 70ms without firing");
    test_portals(); test_identification_lifetime(); test_projectiles(); test_elite_acquisition(); test_elite_route(); test_companion_epoch_events();
    return 0;
}
