/* Normal dispatcher with controlled floor/LOS and replicated item snapshots.
   No test grants inventory as a result of a bot command. */
#include "World/sithItem.h"

uint32_t sithTime_g_msecGameTime;
int32_t Main_bMotsCompat;
static int testTouches, testDestroyTouched;
void sithCog_ThingSendMessage(SithThing *item,SithThing *player,int32_t message)
{
    (void)player;
    assert(message==SITH_MESSAGE_TOUCHED);
    testTouches++;
    if (testDestroyTouched) item->flags|=SITH_TF_DESTROYED;
}

/* Controlled sector/attachment samples model a bank, intervening dry air,
   first water, an unsuccessful gear attempt and a subsequent supported landing. */
static void test_supply_air_return(SithThing *self,SithSector *water,SithSector *air)
{
    self->attach_flags=0; self->sector=air; jkBot_Tick(.05f);
    self->sector=water; self->position=bot.nodes[1].pos;
    self->actorParams.endurance=100; jkBot_Tick(.05f);
    /* Advance the supplied game-clock sample with this same underwater pose. */
    bot.now+=7.9f; bot.stuckAt=bot.now;
    self->actorParams.endurance=8000; jkBot_Tick(.05f);
    assert(!bot.armItem && nav.diveEscape==BOT_DIVE_AIR);
    self->actorParams.endurance=0; self->sector=air; jkBot_Tick(.05f);
    assert(nav.diveEscape==BOT_DIVE_BANK);
}

static void test_failed_supply_approach(void)
{
    SithWorld world={0}; SithSector bank={0},air={0},water={.flags=SITH_SECTOR_UNDERWATER};
    SithThing self={0},items[4]={0}; SithPlayer own={0};
    jkBot_Configure("Supply_Approach","ky.3do"); Bot_ResetHearing();
    bot.world=sithWorld_g_pCurrentWorld=&world;
    world.aThings=items; world.numThings=2; world.numThingsLoaded=3;
    sithPlayer_g_pLocalPlayer=&own; sithPlayer_g_pLocalPlayerThing=&self;
    jkPlayer_maxPlayers=0; testCombatArena=1; testCombatWall=0; corridorMode=0;
    bot.elite=bot.graphDone=bot.joined=sithNet_isMulti=1;
    bot.forceEnabled=0; bot.nextBehavior=bot.nextLog=100; bot.now=bot.stuckAt=1;
    self.type=SITH_THING_PLAYER; self.actorParams.health=100; self.actorParams.pPlayer=&own;
    self.actorParams.maxRotVelocity=200; self.moveSize=self.collideSize=.065f;
    self.sector=&bank; self.attach_flags=SITH_ATTACH_SURFACE;
    self.orient.lvec.y=self.orient.rvec.x=1;
    own.curWeaponID=SITHBIN_CONCUSSION_RIFLE;
    own.aItems[SITHBIN_CONCUSSION_RIFLE].state=SITHINVENTORY_ITEM_AVAILABLE;
    own.aItems[SITHBIN_CONCUSSION_RIFLE].amount=1; own.aItems[SITHBIN_POWER].amount=32;
    own.aItems[SITHBIN_SHIELDS].amount=120;
    bot.nNodes=5;
    bot.nodes[0]=(BotNode){.pos={0,0,.30f},.sector=&bank,.item=-1,.nEdges=2,
        .edges={{1,1,BOT_ROUTE_WATER_ENTRY},{4,1,BOT_ROUTE_WALK}}};
    bot.nodes[1]=(BotNode){.pos={.32f,0,.17f},.sector=&water,.item=-1,.nEdges=3,
        .edges={{0,1,BOT_ROUTE_SWIM},{2,1,BOT_ROUTE_SWIM},{3,1,BOT_ROUTE_SWIM}}};
    bot.nodes[2]=(BotNode){.pos={.9f,0,.17f},.sector=&water,.item=0};
    bot.nodes[3]=(BotNode){.pos={1.2f,0,.17f},.sector=&water,.item=1};
    bot.nodes[4]=(BotNode){.pos={-1,0,.30f},.sector=&bank,.item=2};
    for (int i=0;i<3;i++) {
        items[i]=(SithThing){.idx=i,.type=SITH_THING_ITEM,.sector=bot.nodes[i+2].sector,
            .position=bot.nodes[i+2].pos,.guid=100+i,.signature=400+i,
            .collide=SITH_COLLIDE_SPHERE,.collideSize=.075f};
    }
    strcpy(items[0].aName,"railgun"); strcpy(items[1].aName,"repeatergun");
    strcpy(items[2].aName,"shieldrecharge");
    self.position=bot.nodes[0].pos;
    jkBot_Tick(.05f);
    assert(bot.armItem==1 && bot.goal==2 && bot.route[0]==1);
    test_supply_air_return(&self,&water,&air);
    assert(Bot_FailedDive(&items[0]) && !Bot_FailedDive(&items[1]) && nav.diveBank==0);
    self.sector=&bank; self.attach_flags=SITH_ATTACH_SURFACE; self.position=bot.nodes[0].pos;
    jkBot_Tick(.05f);
    int gear=bot.armItem;
    flex_t slide=bot.axes[INPUT_FUNC_SLIDE];
    /* Check the ordinary planner independently even when a dedicated gear
       route currently owns movement. Item B remains live throughout. */
    bot.goal=-1; Bot_Plan(&self);
    fprintf(stderr,"SUPPLY_APPROACH first=0 second_gear=%d ordinary_goal=%d dry_goal=4\n",gear-1,bot.goal);
    assert(gear==3 && bot.goal==4 && slide<-.2f);
    flex_t retry=nav.supplyApproach.latestRetry;
    /* Dry equipment still drives real movement under recurring noise. */
    BotHeard *heard=&ears.records[0]; heard->cue.kind=BOT_HEARD_PROJECTILE;
    heard->cue.strength=1; heard->slot=-1; heard->first=bot.now-.4f;
    for (int i=0;i<4;i++) {
        heard->last=bot.now; jkBot_Tick(.05f);
        assert(bot.armItem==3 && bot.axes[INPUT_FUNC_SLIDE]<-.2f);
    }
    items[2].flags=SITH_TF_DISABLED; Bot_ResetHearing();
    jkBot_Tick(.05f); /* No remaining dry equipment; ordinary exploration owns movement. */
    assert(!bot.armItem && bot.goal==4 && bot.axes[INPUT_FUNC_SLIDE]<-.2f);
    /* An anonymous projectile can steer attention while the bot keeps
       pursuing a living opponent on dry ground, with no visible fire target. */
    SithThing enemy={.type=SITH_THING_PLAYER,.sector=&bank,.position=bot.nodes[4].pos};
    enemy.actorParams.health=100;
    jkPlayer_playerInfos[1]=(SithPlayer){.flags=1,.playerNetId=42,.pLocalPlayer=&enemy};
    jkPlayer_maxPlayers=2; testLOS=0; bot.nextPlan=0;
    heard->cue.kind=BOT_HEARD_PROJECTILE; heard->cue.position=(rdVector3){.4f,1,.30f};
    heard->cue.strength=1; heard->slot=-1; heard->first=bot.now-.4f;
    for (int i=0;i<4;i++) {
        heard->last=bot.now; jkBot_Tick(.05f);
        if (!i) fprintf(stderr,"SUPPLY_HEARING pursuit=%u slide=%.3f turn=%.3f\n",
            nav.pursuitNet,(double)bot.axes[INPUT_FUNC_SLIDE],(double)bot.axes[INPUT_FUNC_TURN]);
        assert(!bot.armItem && nav.pursuitNet==42 && bot.goal==4 && bot.axes[INPUT_FUNC_SLIDE]<-.2f);
        assert(bot.axes[INPUT_FUNC_TURN]<0 && !bot.keys[INPUT_FUNC_FIRE1] && !bot.keys[INPUT_FUNC_FIRE2]);
    }
    jkPlayer_maxPlayers=0; testLOS=1; Bot_ResetHearing();
    /* The failed entrance is also the sole transit to the far bank. A dry
       supply and then a pursuit must be able to cross, even with wet B live. */
    SithSector farBank={0};
    bot.nNodes=7; bot.nodes[1].edges[bot.nodes[1].nEdges++]=(BotEdge){5,1,BOT_ROUTE_SWIM};
    bot.nodes[5]=(BotNode){.pos={1.4f,.2f,.17f},.sector=&water,.item=-1,.nEdges=1,
        .edges={{6,1,BOT_ROUTE_SWIM}}};
    bot.nodes[6]=(BotNode){.pos={2.9f,.2f,.30f},.sector=&farBank,.item=2};
    bot.nodes[4].item=-1; items[2].position=bot.nodes[6].pos; items[2].sector=&farBank;
    items[2].flags=0; bot.armNext=0; bot.goal=-1;
    /* C4 trace: while holding a well-stocked concussion, an extra rail or
       repeater on dry ground repeatedly brought the bot back into the shaft. */
    own.aItems[SITHBIN_POWER].amount=88; own.aItems[SITHBIN_SHIELDS].amount=100;
    bot.nodes[4].visited=bot.now;
    bot.nNodes=8; bot.nodes[5].edges[bot.nodes[5].nEdges++]=(BotEdge){7,.4f,BOT_ROUTE_SWIM};
    bot.nodes[7]=(BotNode){.pos={2.6f,.2f,.30f},.sector=&farBank,.item=-1,.visited=-120};
    for (int gun=0;gun<2;gun++) {
        strcpy(items[2].aName,gun ? "repeatergun" : "railgun");
        self.position=bot.nodes[0].pos; Bot_ClearEquipment("fixture");
        bot.goal=-1; bot.armNext=bot.nextPlan=0;
        jkBot_Tick(.05f);
        int gear=bot.armItem; flex_t slide=bot.axes[INPUT_FUNC_SLIDE];
        bot.goal=-1; Bot_Plan(&self);
        fprintf(stderr,"DRY_UPGRADE gun=%d selected=%d ordinary_goal=%d slide=%.3f\n",gun,gear,bot.goal,(double)slide);
        assert(!gear && bot.goal==4 && slide<-.2f);
        flex_t before=Bot_Distance(self.position,bot.nodes[4].pos);
        self.position.x+=.10f*slide; jkBot_Tick(.05f);
        assert(bot.goal==4 && Bot_Distance(self.position,bot.nodes[4].pos)<before && bot.axes[INPUT_FUNC_SLIDE]<-.2f);
    }
    /* Same crossing, different marginal need. Stock considers power below
       15% of capacity low; a pack that only offers a spare gun is optional. */
    strcpy(items[2].aName,"powercell"); Bot_FindEquipment(&self); assert(!bot.armItem);
    own.aItems[SITHBIN_POWER].amount=32; Bot_FindEquipment(&self); assert(bot.armItem==3 && bot.route[0]==1);
    own.aItems[SITHBIN_POWER].amount=88; self.actorParams.health=62;
    strcpy(items[2].aName,"healthpack"); Bot_FindEquipment(&self); assert(bot.armItem==3);
    self.actorParams.health=100; self.position=bot.nodes[0].pos; Bot_ClearEquipment("fixture");
    /* A legal dry-rack route obtained before rearming cannot commit after
       the stock bins recover while the next search is still pending. */
    self.position=bot.nodes[0].pos; own.aItems[SITHBIN_POWER].amount=0;
    items[1].flags=SITH_TF_DISABLED; strcpy(items[2].aName,"railgun");
    Bot_FindEquipment(&self); assert(bot.armItem==3 && bot.goal==6 && bot.route[0]==1);
    own.aItems[SITHBIN_POWER].amount=88; bot.armNext=bot.nextPlan=bot.now+1;
    jkBot_Tick(.05f);
    fprintf(stderr,"DRY_UPGRADE_CACHED goal=%d slide=%.3f\n",bot.goal,(double)bot.axes[INPUT_FUNC_SLIDE]);
    assert(bot.goal!=6 && bot.axes[INPUT_FUNC_SLIDE]<=0);
    jkBot_Tick(.05f); assert(!bot.armItem && bot.goal==4 && bot.axes[INPUT_FUNC_SLIDE]<-.2f);
    /* If the local dry route is unavailable and there is no opponent,
       patrol may still use the crossing. Its final purpose is exploration. */
    bot.nodes[4].avoidUntil=bot.now+5; bot.goal=-1; bot.armNext=bot.nextPlan=0;
    jkBot_Tick(.05f);
    assert(!bot.armItem && (bot.goal==6 || bot.goal==7) && bot.route[0]==1 && bot.axes[INPUT_FUNC_SLIDE]>.2f);
    bot.nodes[4].avoidUntil=0; bot.goal=-1;
    /* A different bank entry may reach the same extra dry rack, with its
       checked parents used by both planners. No gun identity gets blacklisted. */
    SithSector detourBank={0}; bot.nNodes=9;
    bot.nodes[8]=(BotNode){.pos={-.5f,.3f,.30f},.sector=&detourBank,.item=-1,.nEdges=1,
        .edges={{1,1,BOT_ROUTE_WATER_ENTRY}}};
    bot.nodes[0].edges[bot.nodes[0].nEdges++]=(BotEdge){8,1,BOT_ROUTE_WALK};
    Bot_FindEquipment(&self); assert(bot.armItem==3 && bot.route[0]==8);
    bot.goal=-1; Bot_Plan(&self); assert(bot.goal==6 && bot.route[0]==8);
    bot.nodes[0].nEdges=2; items[1].flags=0;
    self.position=bot.nodes[0].pos; bot.nNodes=7; bot.nodes[5].nEdges=1;
    strcpy(items[2].aName,"shieldrecharge"); bot.armNext=0; bot.goal=-1;
    jkBot_Tick(.05f);
    fprintf(stderr,"SUPPLY_TRANSIT gear=%d goal=%d slide=%.3f\n",bot.armItem,bot.goal,(double)bot.axes[INPUT_FUNC_SLIDE]);
    assert(bot.armItem==3 && bot.goal==6 && bot.route[0]==1 && bot.axes[INPUT_FUNC_SLIDE]>.2f);
    self.attach_flags=0; self.sector=&air; jkBot_Tick(.05f);
    self.sector=&water; self.position=bot.nodes[1].pos;
    /* This extra dry rack appears only after entering for the needed shield. */
    items[3]=items[2]; items[3].idx=3; items[3].guid=333; items[3].signature=444;
    strcpy(items[3].aName,"railgun"); items[3].position=bot.nodes[7].pos;
    bot.nNodes=8; bot.nodes[7].item=3; bot.nodes[5].nEdges=2;
    world.numThings=3; world.numThingsLoaded=4;
    for (int i=0;i<5;i++) {
        self.actorParams.endurance=150+200*i;
        jkBot_Tick(.2f);
        assert(bot.armItem==3 && bot.goal==6 && bot.axes[INPUT_FUNC_SLIDE]>.2f);
    }
    own.aItems[SITHBIN_POWER].amount=32;
    items[2].flags=SITH_TF_DISABLED; enemy.sector=&farBank; enemy.position=bot.nodes[6].pos;
    jkPlayer_maxPlayers=2; testLOS=0; bot.armNext=bot.nextPlan=0;
    /* Even a pursuit proxy sharing a submerged rack's slot has a combat
       destination. Its crossing is allowed on the bank and after a rescan. */
    bot.nodes[6].item=1;
    self.attach_flags=SITH_ATTACH_SURFACE; self.sector=&bank; self.position=bot.nodes[0].pos;
    self.actorParams.endurance=0; jkBot_Tick(.05f);
    assert(!bot.armItem && nav.pursuitNet==42 && bot.goal==6 && bot.axes[INPUT_FUNC_SLIDE]>.2f);
    self.attach_flags=0; self.sector=&air; jkBot_Tick(.05f);
    self.sector=&water; self.position=bot.nodes[1].pos; self.actorParams.endurance=200;
    heard->cue.kind=BOT_HEARD_PROJECTILE; heard->cue.position=(rdVector3){.8f,1,.17f};
    heard->cue.strength=1; heard->slot=-1; heard->first=bot.now-.4f;
    for (int i=0;i<5;i++) {
        heard->last=bot.now; jkBot_Tick(.2f);
        assert(!bot.armItem && nav.pursuitNet==42 && bot.goal==6 && bot.axes[INPUT_FUNC_SLIDE]>.2f);
    }
    jkPlayer_maxPlayers=0; testLOS=1; Bot_ResetHearing(); self.actorParams.endurance=0;
    self.position=bot.nodes[0].pos; self.sector=&bank; self.attach_flags=SITH_ATTACH_SURFACE;
    /* The final approach node to a moving dry pack can itself carry a wet
       item reference. Its slot and actual pack sector determine the purpose. */
    items[3].flags=SITH_TF_DISABLED; bot.nodes[5].nEdges=1; bot.nNodes=7;
    items[2].flags=0; items[2].itemParams.flags=SITH_ITEM_BACKPACK; items[2].itemParams.numBins=1;
    items[2].itemParams.contents[0].binIdx=SITHBIN_POWER; items[2].itemParams.contents[0].value=32;
    items[2].position.z=bot.nodes[6].pos.z=BOT_FOOT_HEIGHT; bot.armNext=bot.nextPlan=0;
    jkBot_Tick(.05f);
    assert(bot.armItem==3 && bot.goal==6 && !bot.armDirect && bot.axes[INPUT_FUNC_SLIDE]>.2f);
    items[2].itemParams.numBins=2; items[2].itemParams.contents[0].binIdx=SITHBIN_RAIL_DETONATOR;
    items[2].itemParams.contents[0].value=1; items[2].itemParams.contents[1].binIdx=SITHBIN_RAILCHARGES;
    items[2].itemParams.contents[1].value=2; own.aItems[SITHBIN_RAIL_DETONATOR].state=SITHINVENTORY_ITEM_AVAILABLE;
    assert(Bot_PackValue(&self,&items[2])>0); Bot_FindEquipment(&self); assert(!bot.armItem);
    items[2].flags=SITH_TF_DISABLED; items[2].itemParams.flags=0; items[2].itemParams.numBins=0;
    bot.nNodes=5; bot.nodes[1].nEdges=3; bot.nodes[4].item=2;
    items[2].position=bot.nodes[4].pos; items[2].sector=&bank; jkBot_Tick(.05f);
    /* Target B is still valuable, including through a different bank into
       the same water or the same bank into different water. */
    SithSector otherBank={0},otherWater={.flags=SITH_SECTOR_UNDERWATER};
    /* The shortest path still uses the failed pair. An alternate dry-bank
       detour reaches the same live rack; both planners must install it. */
    bot.nNodes=6;
    bot.nodes[5]=(BotNode){.sector=&otherBank,.pos={-.5f,.3f,.30f},.item=-1,.nEdges=1,
        .edges={{1,2,BOT_ROUTE_WATER_ENTRY}}};
    bot.nodes[0].edges[bot.nodes[0].nEdges++]=(BotEdge){5,2,BOT_ROUTE_WALK};
    Bot_FindEquipment(&self); assert(bot.armItem==2 && bot.routeCount==3 && bot.route[0]==5 && bot.route[1]==1);
    bot.goal=-1; Bot_Plan(&self); assert(bot.goal==3 && bot.routeCount==3 && bot.route[0]==5 && bot.route[1]==1);
    bot.nNodes=5; bot.nodes[0].nEdges=2;
    bot.nodes[0].sector=self.sector=&otherBank; Bot_FindEquipment(&self); assert(bot.armItem==2);
    bot.nodes[0].sector=self.sector=&bank;
    bot.nodes[1].sector=&otherWater; Bot_FindEquipment(&self); assert(bot.armItem==2);
    bot.nodes[1].sector=&water; Bot_FindEquipment(&self); assert(!bot.armItem);
    /* One shot short of the existing four-shot reserve, an empty heavy,
       a disarm and urgent health all allow necessary restocking. */
    own.aItems[SITHBIN_POWER].amount=31; Bot_FindEquipment(&self); assert(bot.armItem==2);
    own.aItems[SITHBIN_POWER].amount=0; Bot_FindEquipment(&self); assert(bot.armItem==2);
    own.aItems[SITHBIN_POWER].amount=32; own.aItems[SITHBIN_CONCUSSION_RIFLE].amount=0;
    Bot_FindEquipment(&self); assert(bot.armItem==2);
    own.aItems[SITHBIN_CONCUSSION_RIFLE].amount=1; self.actorParams.health=39;
    Bot_FindEquipment(&self); assert(bot.armItem==2);
    /* A previously legal cached route cannot carry a newly healthy,
       stocked player back into the failed opening before the next scan. */
    self.actorParams.health=100; bot.nextPlan=bot.armNext=bot.now+1;
    jkBot_Tick(.05f);
    fprintf(stderr,"SUPPLY_CACHED goal=%d slide=%.3f\n",bot.goal,(double)bot.axes[INPUT_FUNC_SLIDE]);
    assert(bot.goal!=3 && bot.axes[INPUT_FUNC_SLIDE]<=0);
    bot.nodes[0].sector=&otherBank; bot.nodes[4].sector=&otherBank;
    self.attach_flags=0; self.sector=&air; self.position=bot.nodes[1].pos;
    assert(Bot_Nearest(&self)==1 && Bot_NearestApproach(&self,1)!=1);
    /* Transit may take the nearest wet anchor; optional wet supply may not. */
    bot.nodes[0].sector=bot.nodes[4].sector=self.sector=&bank;
    self.attach_flags=SITH_ATTACH_SURFACE; self.position=bot.nodes[0].pos;
    /* A second failed excursion retains the original bank's deadline.
       No identity replacement or route write should evict an active entry. */
    bot.nodes[0].sector=self.sector=&otherBank;
    bot.nodes[1].sector=bot.nodes[3].sector=items[1].sector=&otherWater;
    bot.armNext=0; jkBot_Tick(.05f); assert(bot.armItem==2);
    test_supply_air_return(&self,&otherWater,&air);
    assert(Bot_ApproachDeferred(&bank,&water) && Bot_ApproachDeferred(&otherBank,&otherWater));
    bot.nodes[0].sector=self.sector=&bank; self.attach_flags=SITH_ATTACH_SURFACE;
    bot.nodes[1].sector=bot.nodes[3].sector=items[1].sector=&water; self.position=bot.nodes[0].pos;
    jkBot_Tick(.05f);
    /* A legitimately expired route can be tried again. */
    bot.now=retry; bot.stuckAt=bot.now;
    Bot_FindEquipment(&self); assert(bot.armItem==1);
    assert(!Bot_ApproachDeferred(&bank,&water) && Bot_ApproachDeferred(&otherBank,&otherWater));
    /* Both reset paths clear live failures, including accumulated bank/entry
       evidence. Reusing the same sector addresses must not revive them. */
    self.actorParams.health=0; jkBot_Tick(.05f);
    self.actorParams.health=100; jkBot_Tick(.05f);
    assert(!Bot_ApproachDeferred(&otherBank,&otherWater) && bot.armItem==1);
    test_supply_air_return(&self,&water,&air); assert(Bot_ApproachDeferred(&bank,&water));
    SithWorld nextWorld={0};
    self.sector=&bank; self.attach_flags=SITH_ATTACH_SURFACE; self.position=bot.nodes[0].pos;
    sithWorld_g_pCurrentWorld=&nextWorld; jkBot_Tick(.05f);
    assert(bot.world==&nextWorld && !Bot_ApproachDeferred(&bank,&water) && !nav.supplyApproach.water);
    puts("PASS dry extra guns yield to active bank patrol, alternate entries, cached rearming and underwater dry-transit rescans");
    puts("PASS independent failed approach expiries and ordinary life/world reset; reverse air route, dry pursuit and projectile attention");
    puts("PASS loaded heavy defers a failed water approach across item identities in both planners; dry movement, other banks/pools, rearming, cached routes and expiry");
    assert(queryDepth==0); testCombatArena=0; Bot_ResetHearing();
}

static void test_bot_equipment(void)
{
    SithWorld world={0}; SithSector dry={0}; SithThing self={0},enemy={0},items[8]={0};
    SithPlayer own={0};
    jkBot_Configure("Supply_Test","ky.3do"); Bot_ResetHearing();
    bot.world=sithWorld_g_pCurrentWorld=&world; world.aThings=items;
    world.numThings=0; world.numThingsLoaded=3;
    sithPlayer_g_pLocalPlayer=&own; sithPlayer_g_pLocalPlayerThing=&self;
    bot.elite=bot.graphDone=bot.joined=sithNet_isMulti=1;
    bot.forceEnabled=bot.fistsPeace=0; bot.nextLog=bot.nextBehavior=100; bot.now=bot.stuckAt=1;
    corridorMode=0; testCombatArena=1; testCombatWall=0; testLOS=1;
    self.type=enemy.type=SITH_THING_PLAYER; self.sector=enemy.sector=&dry;
    self.actorParams.pPlayer=&own; self.actorParams.health=enemy.actorParams.health=100;
    self.actorParams.maxRotVelocity=200; self.moveSize=self.collideSize=.065f;
    self.position.z=BOT_FOOT_HEIGHT; self.orient.lvec.y=self.orient.rvec.x=1;
    self.attach_flags=SITH_ATTACH_SURFACE;
    own.curWeaponID=SITHBIN_BRYARPISTOL;
    for (int i=2;i<=10;i++) own.aItems[i].state=SITHINVENTORY_ITEM_AVAILABLE;
    own.aItems[SITHBIN_BRYARPISTOL].amount=1; own.aItems[SITHBIN_ENERGY].amount=50;
    memset(jkPlayer_playerInfos,0,sizeof(jkPlayer_playerInfos));
    jkPlayer_maxPlayers=2; jkPlayer_playerInfos[1].flags=1;
    jkPlayer_playerInfos[1].playerNetId=42; jkPlayer_playerInfos[1].pLocalPlayer=&enemy;
    enemy.position=self.position; enemy.position.y+=4;
    bot.targetSlot=1; bot.targetNetId=42;
    bot.nNodes=4;
    for (int i=0;i<4;i++) {
        bot.nodes[i]=(BotNode){.sector=&dry,.pos={i*1.4f,0,BOT_FOOT_HEIGHT},.item=-1};
        if (i<3) {
            bot.nodes[i].edges[0]=(BotEdge){i+1,1.4f,BOT_ROUTE_WALK};
            bot.nodes[i].nEdges=1;
        }
    }
    items[0].type=SITH_THING_ITEM; items[0].sector=&dry; items[0].guid=14; items[0].signature=51;
    items[0].collide=SITH_COLLIDE_SPHERE; items[0].collideSize=.1f;
    items[0].position=bot.nodes[3].pos; strcpy(items[0].aName,"concrifle"); bot.nodes[3].item=0;
    /* Opponent stays in the physical aim cone, the gun rack lies 90 degrees
       off-axis and over four units away. Hurt, incoming Force and projectile
       noise do not replace the actual routed leg with duel footwork. */
    bot.previousHealth=105; bot.forceThreatUntil=bot.now+3;
    for (int i=0;i<10;i++) {
        BotHeard *heard=&ears.records[0]; heard->cue.kind=BOT_HEARD_PROJECTILE;
        heard->cue.strength=1; heard->slot=-1; heard->last=bot.now;
        jkBot_Tick(.05f);
        assert(bot.targetSlot==1 && bot.armItem==1 && !bot.armDirect && bot.goal==3);
        assert(bot.route[bot.routePos]==1 && bot.axes[INPUT_FUNC_SLIDE]>.65f);
        assert(bot.keys[INPUT_FUNC_FIRE1] && own.aItems[SITHBIN_CONCUSSION_RIFLE].amount==0);
    }
    assert(bot.hurtUntil>bot.now);
    /* Only one E11/rail shot is available. A newly replicated distant pack
       with a concussion and power uses the existing graph to its final leg. */
    own.aItems[SITHBIN_STORMTROOPER_RIFLE].amount=1;
    own.aItems[SITHBIN_RAIL_DETONATOR].amount=1; own.aItems[SITHBIN_RAILCHARGES].amount=1;
    items[0].flags=SITH_TF_DISABLED; world.numThings=2;
    SithThing *pack=&items[2]; pack->type=SITH_THING_ITEM; pack->sector=&dry; pack->idx=2;
    pack->guid=28; pack->signature=98; pack->collide=SITH_COLLIDE_SPHERE; pack->collideSize=.1f;
    pack->position=(rdVector3){3.7f,0,BOT_FOOT_HEIGHT};
    pack->itemParams.flags=SITH_ITEM_BACKPACK; pack->itemParams.numBins=2;
    pack->itemParams.contents[0].binIdx=SITHBIN_CONCUSSION_RIFLE; pack->itemParams.contents[0].value=1;
    pack->itemParams.contents[1].binIdx=SITHBIN_POWER; pack->itemParams.contents[1].value=24;
    for (int i=0;i<8;i++) jkBot_Tick(.05f);
    assert(bot.armItem==3 && bot.armGuid==28 && bot.armSignature==98 && !bot.armDirect);
    assert(bot.nNodes==4 && bot.goal>=1 && bot.goal<=3 && bot.axes[INPUT_FUNC_SLIDE]>.65f);
    assert(bot.armContact.item==2 && own.aItems[SITHBIN_CONCUSSION_RIFLE].amount==0);
    /* No LOS to the enemy: continuing a valid route cannot emit a gunshot. */
    testLOS=0; jkBot_Tick(.05f);
    assert(bot.armItem==3 && bot.axes[INPUT_FUNC_SLIDE]>.65f && !bot.keys[INPUT_FUNC_FIRE1]);
    testLOS=1;
    /* Slot reuse, a moving drop, depletion and expiry all break the old
       identity immediately. A replacement is discovered on a later scan. */
    pack->signature++; jkBot_Tick(.05f); assert(!bot.armItem);
    self.position.x=2.1f;
    for (int i=0;i<18;i++) jkBot_Tick(.05f);
    assert(bot.armItem==3 && bot.armDirect && bot.armSignature==99 && bot.axes[INPUT_FUNC_SLIDE]>.7f);
    pack->position.x+=.2f; jkBot_Tick(.05f); assert(!bot.armItem);
    for (int i=0;i<16;i++) jkBot_Tick(.05f);
    assert(bot.armItem==3 && bot.armPosition.x==pack->position.x);
    pack->itemParams.numBins=0; jkBot_Tick(.05f); assert(!bot.armItem);
    pack->itemParams.numBins=2; pack->guid++; pack->flags=SITH_TF_DESTROYED;
    for (int i=0;i<16;i++) jkBot_Tick(.05f);
    assert(!bot.armItem && bot.nNodes==4);
    /* Actual stock availability changes while a player is in sight. A pulled
       heavy is pursued again and a full-ammo bot still follows a shield route. */
    /* Fresh supported pose for this phase of the fixed-pose fixture. */
    self.position.x=1.9f; bot.nextRecovery=0; bot.stuckAt=bot.now;
    pack->flags=0; pack->guid=30;
    items[1]=items[0]; items[1].flags=0; strcpy(items[1].aName,"shieldrecharge");
    items[1].idx=1; items[1].position=bot.nodes[2].pos; bot.nodes[2].item=1;
    own.aItems[SITHBIN_CONCUSSION_RIFLE].amount=1; own.aItems[SITHBIN_POWER].amount=500;
    own.aItems[SITHBIN_RAILCHARGES].amount=30; own.aItems[SITHBIN_SHIELDS].amount=50;
    for (int i=0;i<18;i++) jkBot_Tick(.05f);
    assert(bot.armItem==2 && bot.axes[INPUT_FUNC_SLIDE]>.2f);
    own.aItems[SITHBIN_CONCUSSION_RIFLE].amount=0;
    for (int i=0;i<17;i++) jkBot_Tick(.05f);
    assert(bot.armItem==3 && bot.armGuid==30);
    /* Four high-value but disconnected racks rank ahead of the fifth rack
       by straight-line distance. Keep the proven path to the fifth rack. */
    self.position=(rdVector3){0,0,BOT_FOOT_HEIGHT}; enemy.position=(rdVector3){0,4,BOT_FOOT_HEIGHT};
    bot.nextRecovery=0; bot.stuckAt=bot.now; bot.armNext=0;
    world.numThings=7; world.numThingsLoaded=8; bot.nNodes=8; testCombatWall=1;
    pack->flags=SITH_TF_DISABLED; items[1].flags=SITH_TF_DISABLED;
    items[0].flags=0; strcpy(items[0].aName,"railgun"); own.aItems[SITHBIN_RAIL_DETONATOR].amount=0;
    for (int i=4;i<=7;i++) {
        items[i]=items[0]; items[i].idx=i; strcpy(items[i].aName,"concrifle");
        items[i].position=(rdVector3){0.03f*i,0.8f,BOT_FOOT_HEIGHT};
        bot.nodes[i]=(BotNode){.pos=items[i].position,.sector=&dry,.item=i};
    }
    jkBot_Tick(.05f);
    assert(bot.armItem==1 && !bot.armDirect && bot.goal==3 && bot.axes[INPUT_FUNC_SLIDE]>.65f);
    /* Similarly, a fifth dynamic pack can get a geometry probe even when
       four richer drops have no connection through the wall. */
    items[0].flags=SITH_TF_DISABLED; items[1]=*pack; items[1].idx=1; items[1].flags=0;
    items[1].position=(rdVector3){1.60f,0,BOT_FOOT_HEIGHT}; items[1].itemParams.contents[0].binIdx=SITHBIN_REPEATER;
    for (int i=4;i<=7;i++) {
        rdVector3 pos=items[i].position; items[i]=*pack; items[i].flags=0; items[i].idx=i; items[i].position=pos;
        bot.nodes[i].item=-1;
    }
    bot.armNext=0; int found=0;
    for (int i=0;i<8 && !found;i++) {
        bot.now+=.76f; bot.stuckAt=bot.now;
        found=Bot_ArmingMove(&self,3) && bot.armItem==2;
    }
    assert(found);
    /* One isolated anchor splits an overlong direct leg into two legal spans. */
    for (int i=0;i<8;i++) items[i].flags=SITH_TF_DISABLED;
    BotNode savedFirst=bot.nodes[0];
    bot.nNodes=1; testCombatWall=0; pack->flags=0;
    bot.nodes[0]=(BotNode){.sector=&dry,.pos={1.2f,0,BOT_FOOT_HEIGHT},.item=-1};
    pack->position=(rdVector3){2.4f,0,BOT_FOOT_HEIGHT};
    Bot_FindEquipment(&self);
    assert(bot.armItem==3 && !bot.armDirect && bot.goal==0 && bot.routeCount==1 && bot.route[0]==0);
    memset(bot.axes,0,sizeof(bot.axes));
    assert(Bot_ArmingMove(&self,3) && bot.axes[INPUT_FUNC_SLIDE]>0);
    self.position.x=1.2f; memset(bot.axes,0,sizeof(bot.axes));
    assert(Bot_ArmingMove(&self,3) && bot.armDirect && bot.axes[INPUT_FUNC_SLIDE]>0);
    self.position.x=0; Bot_ClearEquipment("fixture");
    /* The initial span must also be traversable, even with a clear ray. */
    SithSector submerged={.flags=SITH_SECTOR_UNDERWATER}; self.sector=&submerged;
    assert(Bot_Nearest(&self)==0); Bot_FindEquipment(&self); assert(!bot.armItem);
    self.sector=&dry;
    /* A wall on the final leg rejects the same anchor. */
    testCombatWall=1; pack->position=(rdVector3){1.2f,1.7f,BOT_FOOT_HEIGHT};
    Bot_FindEquipment(&self); assert(!bot.armItem);
    bot.nodes[0]=savedFirst;
    /* Actual decoded resource/recover policies own a graph goal while the
       opponent remains visible. Pressure keeps its separate range controls. */
    testCombatWall=0; bot.nNodes=4; bot.nextRecovery=0; bot.stuckAt=bot.now;
    for (int i=0;i<8;i++) items[i].flags=SITH_TF_DISABLED;
    items[1]=items[0]; items[1].flags=0; items[1].idx=1;
    items[1].position=bot.nodes[2].pos; strcpy(items[1].aName,"shieldrecharge"); bot.nodes[2].item=1;
    for (int mode=CP_RESOURCE;mode<=CP_RECOVER;mode++) {
        unsigned char request[28]={0}; request[8]=mode; request[10]=SITHBIN_SHIELDS;
        assert(Companion_SetPolicy(&self,request,bot.now+8)==CP_OK);
        for (int frame=0;frame<4;frame++) {
            jkBot_Tick(.05f);
            assert(!bot.armItem && bot.goal==2 && bot.followingRoute);
            assert(bot.axes[INPUT_FUNC_SLIDE]>.65f && bot.keys[INPUT_FUNC_FIRE1]);
        }
    }
    jkPlayer_playerInfos[1].flags=0;
    BotHeard *heard=&ears.records[0]; heard->cue.kind=BOT_HEARD_PROJECTILE;
    heard->cue.strength=1; heard->slot=-1; heard->first=bot.now-.4f; heard->last=bot.now;
    jkBot_Tick(.05f);
    assert(bot.targetSlot<0 && bot.goal==2 && bot.axes[INPUT_FUNC_SLIDE]>.65f);
    jkPlayer_playerInfos[1].flags=1; bot.nextScan=0;
    unsigned char pressure[28]={0}; pressure[8]=CP_PRESSURE;
    assert(Companion_SetPolicy(&self,pressure,bot.now+8)==CP_OK);
    for (int frame=0;frame<5;frame++) jkBot_Tick(.05f);
    assert(!bot.followingRoute && bot.keys[INPUT_FUNC_FIRE1]);
    Companion_ResetPlan();

    /* A conservative air deadline abandons the actual item incarnation. Only
       a real stock breath starts the brief bank approach; a replacement in
       the same thing slot is immediately eligible. */
    SithSector wet={.flags=SITH_SECTOR_UNDERWATER};
    self.sector=items[0].sector=&wet; self.attach_flags=0;
    items[0].flags=0; items[0].guid=600; items[0].signature=3;
    bot.armItem=1; bot.armGuid=600; bot.armSignature=3; bot.armDirect=1;
    nav.waterSince=bot.now-1; self.actorParams.endurance=7999;
    Bot_CheckGearDive(&self); assert(bot.armItem==1 && !nav.diveEscape);
    self.actorParams.endurance=8000; Bot_CheckGearDive(&self);
    assert(!bot.armItem && nav.diveEscape==BOT_DIVE_AIR && Bot_FailedDive(&items[0]));
    assert(!Bot_EquipmentValue(&self,0));
    items[0].signature++; assert(!Bot_FailedDive(&items[0])); items[0].signature--;
    self.actorParams.endurance=7000; Bot_CheckGearDive(&self); assert(nav.diveEscape==BOT_DIVE_AIR);
    self.actorParams.endurance=0; self.physicsParams.flags|=SITH_PF_ONWATERSURFACE;
    bot.goal=2; Bot_CheckGearDive(&self); assert(nav.diveEscape==BOT_DIVE_BANK && nav.diveBank==2);
    self.sector=&dry; self.attach_flags=SITH_ATTACH_SURFACE; Bot_CheckGearDive(&self);
    assert(!nav.diveEscape && Bot_FailedDive(&items[0]));
    flex_t firstFailure=bot.now;
    bot.now+=1; self.sector=items[1].sector=&wet; self.actorParams.endurance=8000;
    bot.armItem=2; bot.armGuid=items[1].guid; bot.armSignature=items[1].signature;
    Bot_CheckGearDive(&self);
    assert(Bot_FailedDive(&items[0]) && Bot_FailedDive(&items[1]));
    items[1].guid++; assert(!Bot_FailedDive(&items[1])); items[1].guid--;
    bot.now=firstFailure+45; assert(!Bot_FailedDive(&items[0]) && Bot_FailedDive(&items[1]));
    bot.now+=1; assert(!Bot_FailedDive(&items[1])); nav.diveEscape=BOT_DIVE_NONE;
    /* A low-health swimmer escaping without an equipment goal can reach air
       mid-hop, too. One genuine breath starts a bounded bank approach once. */
    nav.objective=BOT_OBJECTIVE_AIR; nav.objectiveRouteNode=bot.goal=2;
    self.sector=&wet; self.attach_flags=0; self.physicsParams.flags&=~SITH_PF_ONWATERSURFACE;
    self.actorParams.endurance=500; Bot_CheckGearDive(&self); assert(!nav.diveEscape);
    self.sector=&dry; self.actorParams.endurance=0; Bot_CheckGearDive(&self);
    assert(nav.diveEscape==BOT_DIVE_BANK && nav.diveBank==2);
    bot.now=nav.diveBankUntil+.01f; Bot_CheckGearDive(&self);
    assert(!nav.diveEscape); Bot_CheckGearDive(&self); assert(!nav.diveEscape);
    /* The stock touch may precede an ACK by several control ticks, or the
       COG may destroy a drop before the next tick. Neither fixture grants it. */
    self.sector=&wet; self.attach_flags=0; self.actorParams.endurance=4000;
    nav.waterSince=bot.now; nav.objective=BOT_OBJECTIVE_NONE;
    for (int destroyed=0;destroyed<=1;destroyed++) {
        SithThing *supply=destroyed ? pack : &items[0];
        supply->flags=0; supply->sector=&wet; supply->position=self.position;
        bot.armItem=(int)supply->idx+1; bot.armGuid=supply->guid; bot.armSignature=supply->signature;
        bot.armPosition=supply->position; bot.armNext=bot.now+2;
        nav.diveEscape=BOT_DIVE_NONE; testDestroyTouched=destroyed;
        testTouches=0; sithTime_g_msecGameTime+=1000;
        flex_t inventory=own.aItems[SITHBIN_CONCUSSION_RIFLE].amount;
        Bot_CheckGearDive(&self); assert(!nav.diveEscape);
        testLOS=0; sithItem_PlayerCollisionHandler(supply,&self,NULL,0); testLOS=1;
        assert(!testTouches && !nav.diveEscape);
        /* These callbacks cannot satisfy the current dive. */
        self.actorParams.endurance=3999; jkBot_ObserveItemTouch(&self,supply); self.actorParams.endurance=4000;
        jkBot_ObserveItemTouch(&enemy,supply);
        jkBot_ObserveItemTouch(&self,&items[1]);
        supply->signature++; jkBot_ObserveItemTouch(&self,supply); supply->signature--;
        supply->guid++; jkBot_ObserveItemTouch(&self,supply); supply->guid--;
        bot.wasDead=1; jkBot_ObserveItemTouch(&self,supply); bot.wasDead=0;
        sithNet_isMulti=0; jkBot_ObserveItemTouch(&self,supply); sithNet_isMulti=1;
        sithWorld_g_pCurrentWorld=NULL; jkBot_ObserveItemTouch(&self,supply); sithWorld_g_pCurrentWorld=&world;
        assert(!nav.diveEscape && bot.armItem==(int)supply->idx+1);
        Bot_ArmingMove(&self,3); /* A control frame may see overlap before physics dispatch. */
        sithItem_PlayerCollisionHandler(supply,&self,NULL,0);
        Bot_CheckGearDive(&self); Bot_ArmingMove(&self,3);
        assert(testTouches==1 && nav.diveEscape==BOT_DIVE_AIR && !bot.armItem);
        assert(supply->flags==(destroyed ? SITH_TF_DESTROYED : 0));
        assert(!Bot_FailedDive(supply) && own.aItems[SITHBIN_CONCUSSION_RIFLE].amount==inventory);
    }
    testDestroyTouched=0;
    /* Crowding the cooldown memory must preserve every outstanding failure
       and still allow dry supplies. All of these independent dives expire. */
    SithThing crowded[24]; int count=(int)(sizeof(crowded)/sizeof(crowded[0]));
    world.aThings=crowded; world.numThings=count-1; world.numThingsLoaded=count;
    self.actorParams.endurance=8000;
    for (int round=0;round<2;round++) {
        for (int i=0;i<count-1;i++) {
            crowded[i]=items[0]; crowded[i].idx=i; crowded[i].guid=100+i; crowded[i].flags=0;
            bot.armItem=i+1; bot.armGuid=crowded[i].guid; bot.armSignature=crowded[i].signature;
            Bot_CheckGearDive(&self);
        }
        for (int i=0;i<count-1;i++) assert(Bot_FailedDive(&crowded[i]));
        crowded[count-1]=items[0]; crowded[count-1].idx=count-1; crowded[count-1].sector=&dry;
        assert(!Bot_FailedDive(&crowded[count-1]));
        if (!round) bot.now+=45;
        else { bot.wasDead=1; self.actorParams.endurance=0; jkBot_Tick(.05f); }
        for (int i=0;i<count-1;i++) assert(!Bot_FailedDive(&crowded[i]));
    }
    assert(queryDepth==0); testCombatArena=0; Bot_ResetHearing();
    test_failed_supply_approach();
    puts("PASS stock underwater touch before delayed ACK or destroyed drop, independent bounded dive cooldowns, and two-leg single-anchor packs");
    puts("PASS underwater gear yields to air, honors an actual stock breath plus bank approach, and retries by item identity");
    puts("PASS full-frame ranged fire plus multi-edge supply movement through hurt, noise and Force threat; one-shot reserves and fresh pack approach");
    puts("PASS reachable rack and fifth transient pack survive four blocked shortcuts; resource/recover orders keep route plus fire while pressure retains its movement");
    puts("PASS dynamic pack contact and identity, moved/reused/expired/depleted targets, shield patrol and stock disarm reacquisition");
}
