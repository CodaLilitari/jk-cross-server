/* Input arbitration on a dry supply leg. Stock flight and blast damage are
   measured separately with the engine's controls, collision and physics. */
static void test_combat_supply_jump(void)
{
    SithWorld world={0}; SithSector sector={0}; SithThing actors[3]={0};
    SithThing *self=&actors[0],*enemy=&actors[1],*item=&actors[2];
    SithPlayer own={0}; jkPlayerInfo remote={0};
    rdModel3 conc={0},railItem={0};
    jkBot_Configure("jump","ky.3do"); Bot_ResetHearing();
    memset(&nav,0,sizeof(nav)); memset(jkPlayer_playerInfos,0,sizeof(jkPlayer_playerInfos));
    bot.world=sithWorld_g_pCurrentWorld=&world; world.gravity=4;
    world.aThings=actors; world.numThings=2; world.numThingsLoaded=3;
    bot.elite=bot.enabled=bot.graphDone=bot.joined=bot.competitiveForce=bot.forceEnabled=sithNet_isMulti=1;
    bot.fistsPeace=0; bot.nextBehavior=bot.nextLog=100; bot.now=bot.stuckAt=1;
    self->type=enemy->type=SITH_THING_PLAYER; self->sector=enemy->sector=item->sector=&sector;
    self->physicsParams.mass=150; self->physicsParams.flags=SITH_PF_USEGRAVITY;
    self->actorParams.maxRotVelocity=200; self->actorParams.pPlayer=&own;
    self->physicsParams.airDrag=.5f; self->physicsParams.surfDrag=3; self->physicsParams.staticDrag=.3f;
    self->physicsParams.vel.y=.68f; self->actorParams.health=enemy->actorParams.health=100;
    self->moveSize=self->collideSize=.065f; self->position.z=BOT_FOOT_HEIGHT;
    self->orient.lvec.y=self->orient.rvec.x=1; enemy->orient.lvec.y=-1;
    self->attach_flags=SITH_ATTACH_SURFACE; self->attachedSurface=&corridorFloor;
    corridorFloor.surfaceInfo.face.normal.z=1;
    self->actorParams.pPlayer->curWeaponID=SITHBIN_BRYARPISTOL;
    own.aItems[SITHBIN_BRYARPISTOL].state=own.aItems[SITHBIN_F_JUMP].state=SITHINVENTORY_ITEM_AVAILABLE;
    own.aItems[SITHBIN_BRYARPISTOL].amount=1; own.aItems[SITHBIN_ENERGY].amount=50;
    own.aItems[SITHBIN_F_JUMP].amount=4; own.aItems[SITHBIN_FORCEMANA].amount=50;
    sithPlayer_g_pLocalPlayerThing=self; sithPlayer_g_pLocalPlayer=&own;
    enemy->position=self->position; enemy->position.y=4; enemy->idx=1; enemy->playerInfo=&remote;
    remote.rd_thing.model3=&conc; strcpy(conc.filename,"cong.3do");
    jkPlayer_maxPlayers=2; jkPlayer_playerInfos[1].flags=1; jkPlayer_playerInfos[1].playerNetId=42;
    jkPlayer_playerInfos[1].pLocalPlayer=enemy; bot.targetSlot=1; bot.targetNetId=42;
    item->type=SITH_THING_ITEM; item->renderData.model3=&railItem; strcpy(railItem.filename,"rldp.3do");
    item->idx=2; item->position=self->position; item->position.y=1.8f;
    bot.nNodes=2; bot.nodes[0]=(BotNode){.item=-1,.sector=&sector,.pos=self->position};
    bot.nodes[1]=(BotNode){.item=2,.sector=&sector,.pos=item->position};
    testCombatArena=testLOS=1; testCombatWall=corridorMode=0; corridorSector=&sector;

    /* Turning a gun away removes the anticipated threat. A dry, aligned
       positive must be solely a consequence of the next visible pose. */
    const int jump=Bot_PowerKey(SITHBIN_F_JUMP);
    /* Actual rail and concussion shots push their shooter. Neither can
       initiate this coast, even when the shot and the pickup are legal. */
    const int recoilGuns[]={SITHBIN_RAIL_DETONATOR,SITHBIN_CONCUSSION_RIFLE};
    own.aItems[SITHBIN_RAILCHARGES].amount=1; own.aItems[SITHBIN_POWER].amount=16;
    for (unsigned i=0;i<2;i++) {
        int gun=recoilGuns[i];
        own.aItems[gun].state=SITHINVENTORY_ITEM_AVAILABLE;
        own.aItems[gun].amount=1; own.curWeaponID=gun;
        jkBot_Tick(.04f); assert(!bot.keys[jump] && !nav.combatJumpUntil && bot.armItem==3);
        own.aItems[gun].amount=0;
    }
    own.curWeaponID=SITHBIN_BRYARPISTOL;
    enemy->orient.lvec.y=1;
    jkBot_Tick(.04f); assert(!bot.keys[jump] && bot.armItem==3);
    enemy->orient.lvec.y=-1;
    jkBot_Tick(.04f); assert(bot.keys[jump] && bot.presses[jump] && bot.keys[INPUT_FUNC_FIRE1]);
    assert(nav.combatJumpUntil>bot.now && bot.armItem==3 && !bot.axes[INPUT_FUNC_FORWARD]);
    assert(own.aItems[SITHBIN_FORCEMANA].amount==50 && self->physicsParams.vel.z==0);
    int holds=0;
    do { jkBot_Tick(.04f); holds++; } while(bot.keys[jump] && holds<5);
    assert(holds>=2 && holds<5 && bot.forceBin<0);
    self->attach_flags=0;
    jkBot_Tick(.04f); assert(nav.combatJumpAirborne && bot.keys[INPUT_FUNC_FIRE1]);
    assert(!bot.axes[INPUT_FUNC_FORWARD] && !bot.axes[INPUT_FUNC_SLIDE] && !bot.routeAim);
    /* A new inventory snapshot can expose either heavy during the flight.
       It must neither be drawn nor discharge if a stock auto-switch mounts it. */
    for (unsigned i=0;i<2;i++) {
        int gun=recoilGuns[i];
        own.aItems[gun].amount=1; bot.nextSelect=0;
        jkBot_Tick(.04f);
        assert(!bot.keys[INPUT_FUNC_SELECT1+gun-1] && bot.keys[INPUT_FUNC_FIRE1]);
        own.curWeaponID=gun;
        jkBot_Tick(.04f); assert(!bot.keys[INPUT_FUNC_FIRE1] && !bot.keys[INPUT_FUNC_FIRE2]);
        own.curWeaponID=SITHBIN_BRYARPISTOL; own.aItems[gun].amount=0;
    }
    enemy->position.x=2;
    jkBot_Tick(.04f); assert(!bot.keys[INPUT_FUNC_FIRE1] && fabsf(bot.axes[INPUT_FUNC_TURN])>.1f);
    self->attach_flags=SITH_ATTACH_SURFACE; enemy->position.x=0;
    jkBot_Tick(.04f); jkBot_Tick(.04f);
    assert(!nav.combatJumpUntil && bot.armItem==3 && bot.axes[INPUT_FUNC_FORWARD]>.5f && !bot.keys[jump]);

    /* The same moving launch must decline a missed pickup, a missing floor,
       insufficient mana, and a control cadence outside the checked regime. */
    flex_t flight;
    assert(!Bot_CombatJumpSpace(self,(rdVector3){0,.2f,BOT_FOOT_HEIGHT},4,&flight));
    SithSurface otherFloor={0}; self->attachedSurface=&otherFloor;
    assert(!Bot_CombatJumpSpace(self,item->position,4,&flight)); self->attachedSurface=&corridorFloor;
    nav.nextCombatJump=0; own.aItems[SITHBIN_FORCEMANA].amount=19;
    jkBot_Tick(.04f); assert(!bot.keys[jump]);
    own.aItems[SITHBIN_FORCEMANA].amount=50;
    jkBot_Tick(.16f); assert(!bot.keys[jump]);
    testCombatArena=0; assert(queryDepth==0);
    puts("PASS moving supply jump uses normal Force press/hold/release and aligned gunfire; coast permits aim and resumes the pickup");
}
