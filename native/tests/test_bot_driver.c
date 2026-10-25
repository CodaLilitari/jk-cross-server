/* Controlled regression checks; not a live multiplayer qualification. */
#include <assert.h>
#include <stdio.h>
#include "AI/jkBot.c"
#ifdef NDEBUG
#error Assertions must remain enabled for the driver regression tests
#endif
uint32_t jkPlayer_maxPlayers;
SithPlayer jkPlayer_playerInfos[JKPLAYER_NUM_INFOS];
int32_t sithNet_MultiModeFlags;
flex_t sithCollision_SearchForCollisions(SithSector *sector, SithThing *thing,
    const rdVector3 *from, const rdVector3 *direction, flex_t distance,
    flex_t radius, int flags)
{
    (void)sector; (void)thing; (void)from; (void)direction; (void)radius; (void)flags;
    return distance;
}
SithCollision *sithCollision_PopStack(void) { return NULL; }
void sithCollision_DecreaseStackLevel(void) {}
int sithInventory_IsInventoryAvailable(SithThing *thing, int bin)
{ (void)thing; (void)bin; return 0; }
flex_t sithInventory_GetInventory(SithThing *thing, int bin)
{ (void)thing; (void)bin; return 0; }
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
    Bot_Aim(&self,(rdVector3){1,1,0},1);
    assert(jkBot_GetAxis(INPUT_FUNC_TURN)<0);
    Bot_Aim(&self,(rdVector3){-1,1,0.2f},1);
    assert(jkBot_GetAxis(INPUT_FUNC_TURN)>0 && jkBot_GetAxis(INPUT_FUNC_PITCH)>0);
    assert(jkBot_GetAxis(-1)==0 && jkBot_GetAxis(INPUT_FUNC_MAX)==0);
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
    Bot_Recovery(&self);
    assert(bot.goal==-1 && bot.routeCount==0);
    assert(bot.keys[INPUT_FUNC_ACTIVATE]==1 && bot.nodes[0].avoidUntil>bot.now);
    puts("PASS vertical jumping alone does not conceal a navigation stall");
    return 0;
}
