/* Controlled regression checks; not a live multiplayer qualification. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
/* These groups were written against the behaviour before the tactic table.
   They pin its legacy column; test_bot_tactics.inc covers the new defaults.
   Compile with -DJKBOT_TEST_NEW_DEFAULTS to run them against the defaults. */
#ifndef JKBOT_TEST_NEW_DEFAULTS
#define JKBOT_TACTICS_BASELINE_LEGACY 1
#endif
#include "AI/jkBot.c"
#ifdef NDEBUG
#error Assertions must remain enabled for the driver regression tests
#endif
uint32_t jkPlayer_maxPlayers;
SithPlayer jkPlayer_playerInfos[JKPLAYER_NUM_INFOS];
int32_t sithNet_MultiModeFlags;
int32_t sithNet_tickrate=16;
SithThing *sithPlayer_g_pLocalPlayerThing;
flex_t sithTime_g_secGameTime;
int sithControl_death_msgtimer; /* quick_respawn reads the stock death message timer */
static int testLOS=1;
static SithThing *testGrenade;
static SithInventoryType testInventoryTypes[SITHBIN_NUMBINS];
static int corridorMode, queryDepth, pendingHit;
static flex_t corridorCeiling=-0.05f;
static SithSector *corridorSector;
static SithSurface corridorFloor;
static SithCollision corridorHit;
static int fixtureMode;
static SithCollision fixtureHit;
#include "test_bot_c1_geometry.inc"
#include "test_bot_static_bridge.inc"
#include "test_bot_slope_geometry.inc"
#include "test_bot_combat.inc"
#include "test_bot_plain_geometry.inc"
/* Bounded box matching stock m2 sector110; not a full level simulation. */
int sithIntersect_IsSphereInSector(const rdVector3 *p, flex_t radius, SithSector *sector)
{
    if (testPlainActive) return TestPlainSphere(p,radius,sector);
    if (testC1Active) return TestC1Sphere(p,radius,sector);
    if (testBridgeActive) return TestBridgeSphere(p,radius,sector);
    if (testSlopeActive) return TestSlopeSphere(p,radius,sector);
    if (!corridorMode) return sector!=NULL;
    return sector==corridorSector && p->x-radius>=-3.0f && p->x+radius<=-1.8f &&
        p->y-radius>=-2.0f && p->y+radius<=-1.65f &&
        p->z-radius>=-0.25f && p->z+radius<=corridorCeiling;
}
SithSector *sithSector_FindSectorAtPos(SithWorld *world, rdVector3 *position)
{
    (void)world;
    if (testPlainActive) return TestPlainSector(position);
    if (testC1Active) return TestC1Sector(position);
    if (testBridgeActive) return TestBridgeSector(position);
    if (testSlopeActive) return TestSlopeSectorAt(position);
    return sithIntersect_IsSphereInSector(position,0,corridorSector) ? corridorSector : NULL;
}
flex_t sithCollision_SearchForCollisions(SithSector *sector, SithThing *thing,
    const rdVector3 *from, const rdVector3 *direction, flex_t distance,
    flex_t radius, int flags)
{
    queryDepth++; pendingHit=0;
    if (testPlainActive) {
        pendingHit=TestPlainCollision(from,direction,distance,radius,&corridorHit);
        return distance;
    }
    if (testCombatArena) {
        pendingHit=TestCombatCollision(sector,from,direction,distance,radius,&corridorHit);
        if (thing && thing->type==SITH_THING_WEAPON && flags==0)
            TestBeamCollision(thing,from,direction,distance,radius,&corridorHit,&pendingHit);
        return distance;
    }
    if (testC1Active) {
        pendingHit=TestC1Collision(sector,from,direction,distance,radius,&corridorHit);
        return distance;
    }
    if (testBridgeActive) {
        pendingHit=TestBridgeCollision(sector,from,direction,distance,radius,flags,&corridorHit);
        return distance;
    }
    if (testSlopeActive) {
        pendingHit=TestSlopeCollision(from,direction,distance,radius,&corridorHit);
        return distance;
    }
    if (fixtureMode) {
        if (!(flags&RAYCAST_1)) { corridorHit=fixtureHit; pendingHit=1; }
        return distance;
    }
    if (corridorMode) {
        rdVector3 end={from->x+direction->x*distance,
            from->y+direction->y*distance,from->z+direction->z*distance};
        memset(&corridorHit,0,sizeof(corridorHit));
        corridorHit.type=SITHCOLLISION_WORLD;
        corridorHit.surface=&corridorFloor;
        corridorFloor.pSector=sector;
        corridorFloor.flags=SITH_SURFACE_HAS_COLLISION|SITH_SURFACE_FLOOR;
        if (direction->z<-0.99f && radius==0 && from->z>=-0.25f && end.z<=-0.25f) {
            pendingHit=1; corridorHit.distance=from->z+0.25f; corridorHit.hitNorm.z=1;
        } else if (Bot_Max(from->z,end.z)+radius>corridorCeiling ||
                   Bot_Min(from->z,end.z)-radius<-0.25f) {
            pendingHit=1; corridorHit.distance=0; corridorHit.hitNorm.z=-1;
        }
    }
    return distance;
}
SithCollision *sithCollision_PopStack(void)
{ if (!pendingHit) return NULL; pendingHit=0; return &corridorHit; }
void sithCollision_DecreaseStackLevel(void) { queryDepth--; assert(queryDepth>=0); }
int sithInventory_IsInventoryAvailable(SithThing *thing, int bin)
{ return thing->actorParams.pPlayer && (thing->actorParams.pPlayer->aItems[bin].state&SITHINVENTORY_ITEM_AVAILABLE); }
flex_t sithInventory_GetInventory(SithThing *thing, int bin)
{ return thing->actorParams.pPlayer ? thing->actorParams.pPlayer->aItems[bin].amount : 0; }
int sithInventory_IsInventoryActivated(SithThing *thing, int bin)
{ return thing->actorParams.pPlayer && (thing->actorParams.pPlayer->aItems[bin].state&SITHINVENTORY_ITEM_ACTIVATED); }
int sithInventory_GetCurrentWeapon(SithThing *thing)
{ return thing->actorParams.pPlayer->curWeaponID; }
SithInventoryType *sithInventory_GetType(int bin) { return &testInventoryTypes[bin]; }
int sithInventory_GetPowerKeybind(int index)
{ return index<14 ? SITHBIN_F_JUMP+index : index==14 ? SITHBIN_BACTATANK : -1; }
int sithCollision_HasLOS(SithThing *from, SithThing *to, int flags)
{ (void)from; (void)to; (void)flags; return testLOS; }
SithThing *sithTemplate_GetTemplate(const char *name)
{
    if (testCombatArena && !strcmp(name,"+concblast2")) return &testConcBeam;
    if (testCombatArena && !strcmp(name,"+concbullet")) return &testConcProjectile;
    if (testCombatArena && !strcmp(name,"+raildet")) return &testRailProjectile;
    if (testGrenade && !strcmp(name,"+grenade1")) return testGrenade;
    return NULL;
}
/* The turn the bot asked for this tick: a keyboard axis, or (turn_rate) a
   mouse-look rotation in degrees. Tests read its direction. */
static flex_t TestTurn(void) { return bot.axes[INPUT_FUNC_TURN]!=0 ? bot.axes[INPUT_FUNC_TURN] : bot.rawTurn; }
static flex_t TestPitch(void) { return bot.axes[INPUT_FUNC_PITCH]!=0 ? bot.axes[INPUT_FUNC_PITCH] : bot.rawPitch; }
#include "test_bot_behavior.inc"
#include "test_bot_navigation.inc"
#include "test_bot_movement_tick.inc"
#include "test_bot_combat_jump.inc"
#include "test_bot_equipment.inc"
#include "test_bot_tactics.inc"
#include "test_bot_tactic_fixes.inc"

int main(void)
{
    SithSector sector={0};
    SithThing self={0}, peer={0};
    SithPlayer own={0};
    self.sector=&sector; self.type=SITH_THING_PLAYER;
    self.actorParams.pPlayer=&own; self.actorParams.health=100;
    peer.sector=&sector; peer.type=SITH_THING_PLAYER;
    jkPlayer_maxPlayers=2;
    jkPlayer_playerInfos[1].flags=1;
    jkPlayer_playerInfos[1].playerNetId=42;
    jkPlayer_playerInfos[1].pLocalPlayer=&peer;
    peer.actorParams.health=0;
    assert(Bot_EnemyAllowed(&self,1)==1);
    peer.flags=SITH_TF_DEAD;
    assert(Bot_EnemyAllowed(&self,1)==0);
    peer.flags=0;
    assert(Bot_EnemyAllowed(&self,1)==1);
    peer.flags=SITH_TF_DISABLED;
    assert(Bot_EnemyAllowed(&self,1)==0);
    peer.flags=0;
    sithNet_MultiModeFlags=MULTIMODEFLAG_TEAMS;
    own.teamNum=jkPlayer_playerInfos[1].teamNum=1;
    assert(Bot_EnemyAllowed(&self,1)==0);
    sithNet_MultiModeFlags=0;
    jkPlayer_playerInfos[1].flags=0;
    assert(Bot_EnemyAllowed(&self,1)==0);
    puts("PASS remote-zero-health respawn eligibility and inactive/dead/team rejection");
    jkBot_Configure("Bot_Test","ky.3do");
    bot.now=5; bot.goal=0; bot.goalSetAt=4; bot.nNodes=2;
    bot.nodes[0].pos=(rdVector3){0.25f,0,0};
    bot.nodes[1].pos=(rdVector3){0.8f,0,0};
    for (int i=0;i<2;i++) {
        bot.nodes[i].sector=&sector; bot.nodes[i].item=-1;
        bot.nodes[i].visited=-120;
    }
    bot.nodes[0].nEdges=1;
    bot.nodes[0].edges[0]=(BotEdge){1,0.55f,0};
    Bot_Plan(&self);
    assert(bot.goal==0 && bot.routeCount==1 && bot.route[0]==0);
    self.position=bot.nodes[0].pos;
    Bot_Plan(&self);
    assert(bot.goal==1 && bot.routeCount==1 && bot.route[0]==1);
    puts("PASS unreached nearest-node goal retained until actually reached");
    self.position=(rdVector3){0,0,0};
    self.orient.rvec=(rdVector3){1,0,0};
    self.orient.lvec=(rdVector3){0,1,0};
    self.actorParams.maxRotVelocity=200;
    /* The keyboard path (turn_rate 0): rate-limited turn and pitch axes. */
    flex_t turnRate=BT(TURN_RATE); BT(TURN_RATE)=0;
    Bot_Aim(&self,(rdVector3){1,1,0},1);
    assert(jkBot_GetAxis(INPUT_FUNC_TURN)<0 && jkBot_GetRawAxis(INPUT_FUNC_TURN)==0);
    Bot_Aim(&self,(rdVector3){-1,1,0.2f},1);
    assert(jkBot_GetAxis(INPUT_FUNC_TURN)>0 && jkBot_GetAxis(INPUT_FUNC_PITCH)>0);
    assert(jkBot_GetAxis(-1)==0 && jkBot_GetAxis(INPUT_FUNC_MAX)==0);
    /* The mouse-look path: this frame's rotation in degrees, capped by turn_rate. */
    BT(TURN_RATE)=1800; bot.frameDt=0.02f;
    Bot_Aim(&self,(rdVector3){1,1,0},1);
    assert(jkBot_GetAxis(INPUT_FUNC_TURN)==0 && fabsf(jkBot_GetRawAxis(INPUT_FUNC_TURN)+36.0f)<0.01f && "45 degrees right, 36 this frame");
    Bot_Aim(&self,(rdVector3){-0.1f,1,0.1f},1);
    assert(fabsf(jkBot_GetRawAxis(INPUT_FUNC_TURN)-5.711f)<0.01f && fabsf(jkBot_GetRawAxis(INPUT_FUNC_PITCH)-5.682f)<0.01f && "a small error closes in one frame");
    bot.axes[INPUT_FUNC_TURN]=0.5f; assert(jkBot_GetRawAxis(INPUT_FUNC_TURN)==0 && "a key turn set after the aim wins");
    assert(jkBot_GetRawAxis(INPUT_FUNC_FORWARD)==0);
    bot.axes[INPUT_FUNC_TURN]=0; bot.rawTurn=bot.rawPitch=0; BT(TURN_RATE)=turnRate;
    bot.keys[INPUT_FUNC_ACTIVATE]=1; bot.presses[INPUT_FUNC_ACTIVATE]=1;
    int pressed=-1;
    assert(jkBot_GetKey(INPUT_FUNC_ACTIVATE,NULL)==1);
    assert(jkBot_GetKey(INPUT_FUNC_ACTIVATE,&pressed)==1 && pressed==1);
    assert(jkBot_GetKey(INPUT_FUNC_ACTIVATE,&pressed)==1 && pressed==0);
    assert(jkBot_GetKey(-1,&pressed)==0 && pressed==0);
    puts("PASS normal yaw/pitch axes and single-consumption press edge");
    jkBot_Configure("Bot_Test","ky.3do");
    bot.now=5; bot.stuckAt=1; bot.goal=0; bot.routeCount=1; bot.route[0]=0;
    bot.progressPos=(rdVector3){0,0,0};
    self.position=(rdVector3){0,0,0.20f};
    self.attach_flags=0;
    bot.followingRoute=1; bot.frameDt=0.05f; bot.stuckAt=bot.now;
    for (int i=0;i<41;i++) {
        bot.now+=bot.frameDt;
        Bot_Recovery(&self);
    }
    assert(bot.goal==-1 && bot.routeCount==0);
    assert(bot.keys[INPUT_FUNC_ACTIVATE]==1 && bot.nodes[0].avoidUntil>bot.now);
    puts("PASS vertical jumping alone does not conceal a navigation stall");
    jkBot_Configure("Bot_Test","ky.3do");
    corridorMode=1; corridorSector=&sector; corridorCeiling=-0.05f;
    BotNode tunnelA={0},tunnelB={0};
    tunnelA.pos=(rdVector3){-2.0f,-1.850050f,-0.129886f};
    tunnelB.pos=(rdVector3){-2.4f,-1.850050f,-0.129886f};
    tunnelA.sector=tunnelB.sector=&sector;
    int drop=-1;
    assert(Bot_Walkable(&tunnelA,&tunnelB,&drop)==1 && drop==0);
    self.position=tunnelA.pos; self.sector=&sector; self.collideSize=0.065f;
    self.physicsParams.vel=(rdVector3){0,0,0};
    rdVector3 blocked;
    assert(Bot_SafeDirection(&self,(rdVector3){-1,0,0},0,0.4f,&blocked)==1);
    corridorCeiling=-0.16f;
    assert(Bot_Walkable(&tunnelA,&tunnelB,&drop)==0);
    assert(Bot_SafeDirection(&self,(rdVector3){-1,0,0},0,0.4f,&blocked)==0);
    assert(queryDepth==0);
    puts("PASS sector110 low-ceiling graph/steering and actual obstruction rejection");
    corridorMode=0; fixtureMode=1;
    SithThing fixture={0}; fixture.type=SITH_THING_COG; fixture.collide=SITH_COLLIDE_FACE;
    fixture.sector=&sector; fixture.moveType=SITH_MT_PATH;
    fixtureHit=(SithCollision){0}; fixtureHit.type=SITHCOLLISION_THING;
    fixtureHit.pThingCollided=&fixture; fixtureHit.distance=0.25f; fixtureHit.hitNorm.z=1;
    rdVector3 sample={0,0,1}, standing; SithSector *supportSector=NULL;
    assert(Bot_Floor(sample,&sector,1,&standing,&supportSector));
    assert(supportSector==&sector && fabsf(standing.z-(0.75f+BOT_FOOT_HEIGHT))<0.00001f);
    assert(!Bot_Clear(NULL,&sector,(rdVector3){0,0,0},(rdVector3){1,0,0},0.04f,1));
    fixture.trackParams.loadedFrames=2;
    assert(!Bot_Floor(sample,&sector,1,&standing,&supportSector));
    assert(Bot_Clear(NULL,&sector,(rdVector3){0,0,0},(rdVector3){1,0,0},0.04f,1));
    fixture.trackParams.loadedFrames=0; fixture.trackParams.flags=1;
    assert(!Bot_Floor(sample,&sector,1,&standing,&supportSector));
    fixture.trackParams.flags=0; fixture.flags=SITH_TF_DISABLED;
    assert(!Bot_Floor(sample,&sector,1,&standing,&supportSector));
    fixture.flags=0; fixture.type=SITH_THING_PLAYER;
    assert(!Bot_Floor(sample,&sector,1,&standing,&supportSector));
    fixture.type=SITH_THING_COG; fixtureHit.hitNorm.z=0.4f;
    assert(!Bot_Floor(sample,&sector,1,&standing,&supportSector));
    fixtureHit.hitNorm.z=1; fixture.moveType=SITH_MT_NONE;
    assert(Bot_Floor(sample,&sector,1,&standing,&supportSector));
    assert(queryDepth==0); fixtureMode=0;
    puts("PASS stationary mesh floors/blockers and moving/disabled/actor/steep-support exclusions");
    test_bot_slope_steering();
    test_bot_behavior();
    test_bot_navigation();
    test_bot_gunshots();
    test_bot_arming();
    test_bot_equipment();
    test_bot_movement_ownership();
    test_combat_supply_jump();
    test_bot_tactics();
    test_bot_tactic_fixes();
    return 0;
}
