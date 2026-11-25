/* Fixes from the review of bot and human match footage: respawn timing,
 * swimming and climbing out while fighting, the Grip answer during a climb
 * out, Force Jump flown from a standstill, the jump memory, Force Speed kept
 * up, resupply after a Force Pull, running everywhere safe, pulling items
 * on the move, and dropped packs. Controlled fixtures only: synthetic ground
 * and hand-built graphs, not a level or a live match. */

static void test_fix_respawn(void)
{
    jkBot_Configure("Respawn_Test","ky.3do"); TacticsUse(0);
    memset(bot.previous,0,sizeof(bot.previous));
    bot.now=10; bot.deadAt=10;
    sithTime_g_msecGameTime=10000; sithControl_death_msgtimer=13000;
    assert(!Bot_RespawnPress() && "the stock code ignores the key until its message is due");
    sithTime_g_msecGameTime=12999; assert(!Bot_RespawnPress());
    sithTime_g_msecGameTime=13000; assert(Bot_RespawnPress());
    bot.previous[INPUT_FUNC_ACTIVATE]=1;
    assert(!Bot_RespawnPress() && "the release after a press is what respawns");
    bot.previous[INPUT_FUNC_ACTIVATE]=0; sithControl_death_msgtimer=0;
    assert(Bot_RespawnPress() && "once the message has shown the timer reads zero");
    /* Legacy: nothing for 1.5 s, then a 0.18 s press in every 1.4 s. */
    TacticsUse(1); sithControl_death_msgtimer=13000; sithTime_g_msecGameTime=13000;
    bot.now=11.0f; assert(!Bot_RespawnPress());
    bot.now=13.1f; assert(!Bot_RespawnPress() && "the old cadence misses the first window");
    bot.now=14.25f; assert(Bot_RespawnPress());
    TacticsUse(0); sithControl_death_msgtimer=0; sithTime_g_msecGameTime=0;
    puts("PASS quick respawn presses the moment the stock timer allows and releases on alternate frames; legacy keeps the slow cadence");
}

static void test_fix_swim_thrust(void)
{
    static SithSector pool;
    SithThing self={0}; SithPlayer own={0};
    memset(&pool,0,sizeof(pool)); pool.flags=SITH_SECTOR_UNDERWATER;
    jkBot_Configure("Stroke_Test","ky.3do"); TacticsUse(0);
    self.type=SITH_THING_PLAYER; self.sector=&pool; self.actorParams.pPlayer=&own;
    PlainFace(&self,0);
    /* Straight to the body's right while looking ahead: strafe alone, full key. */
    memset(bot.axes,0,sizeof(bot.axes)); memset(bot.keys,0,sizeof(bot.keys));
    Bot_SwimThrust(&self,(rdVector3){0,-1,0});
    assert(bot.axes[INPUT_FUNC_FORWARD]==0 && bot.axes[INPUT_FUNC_SLIDE]==1 &&
           !bot.keys[INPUT_FUNC_JUMP] && !bot.keys[INPUT_FUNC_DUCK]);
    /* Ahead and to the right: forward and strafe in the stock 1 : 0.7 ratio,
       so the thrust they make points exactly along the wanted line. */
    Bot_SwimThrust(&self,(rdVector3){0.8660254f,-0.5f,0});
    flex_t f=bot.axes[INPUT_FUNC_FORWARD], s=bot.axes[INPUT_FUNC_SLIDE];
    assert(fabsf(f-0.8660254f)<1e-4f && fabsf(s*0.7f-0.5f)<1e-4f);
    /* Down: crouch. Up: jump, but never on the surface, where a fresh jump
       press is the leap out of the water. */
    Bot_SwimThrust(&self,(rdVector3){0,0,-1});
    assert(bot.keys[INPUT_FUNC_DUCK] && !bot.keys[INPUT_FUNC_JUMP]);
    Bot_SwimThrust(&self,(rdVector3){0,0,1});
    assert(bot.keys[INPUT_FUNC_JUMP] && !bot.keys[INPUT_FUNC_DUCK]);
    self.physicsParams.flags=SITH_PF_ONWATERSURFACE;
    Bot_SwimThrust(&self,(rdVector3){0,0,1});
    assert(!bot.keys[INPUT_FUNC_JUMP] && !bot.keys[INPUT_FUNC_DUCK] && "no stray leap at the surface");
    self.physicsParams.flags=0;
    /* Looking up 30 degrees tilts the forward stroke upward; a level leg
       crouches against it. On the surface the head tilts nothing. */
    self.actorParams.headPYR.x=30;
    Bot_SwimThrust(&self,(rdVector3){1,0,0});
    assert(bot.axes[INPUT_FUNC_FORWARD]==1 && bot.keys[INPUT_FUNC_DUCK] && !bot.keys[INPUT_FUNC_JUMP]);
    self.physicsParams.flags=SITH_PF_ONWATERSURFACE;
    Bot_SwimThrust(&self,(rdVector3){1,0,0});
    assert(bot.axes[INPUT_FUNC_FORWARD]==1 && !bot.keys[INPUT_FUNC_DUCK]);
    self.physicsParams.flags=0;
    /* Looking steeply up or down: the route's own keys stand. */
    self.actorParams.headPYR.x=75; bot.axes[INPUT_FUNC_FORWARD]=0.3f; bot.axes[INPUT_FUNC_SLIDE]=0;
    Bot_SwimThrust(&self,(rdVector3){0,-1,0});
    assert(bot.axes[INPUT_FUNC_FORWARD]==0.3f && bot.axes[INPUT_FUNC_SLIDE]==0);
    self.actorParams.headPYR.x=0;
    /* Nothing left to swim: stop the stroke. */
    Bot_SwimThrust(&self,(rdVector3){0.01f,0,0});
    assert(bot.axes[INPUT_FUNC_FORWARD]==0 && bot.axes[INPUT_FUNC_SLIDE]==0);
    puts("PASS swim stroke solved for the view: forward, strafe at 0.7, jump and crouch; no surface leap, pitched view countered, steep view left to the route");
}

static flex_t ExitTurn(SithThing *self,rdVector3 bank,rdVector3 line)
{
    bot.rawTurn=bot.rawPitch=0; memset(bot.axes,0,sizeof(bot.axes));
    Bot_ExitAim(self,bank,line);
    return bot.rawTurn;
}

static rdVector3 ExitAt(flex_t degrees)
{
    return (rdVector3){5.0f*cosf(degrees/BOT_DEG),5.0f*sinf(degrees/BOT_DEG),0};
}

static void test_fix_water_exit(void)
{
    static SithSector pool,bank;
    static rdModel3 rifleModel;
    SithThing self={0},peer={0}; SithPlayer own={0},theirs={0}; jkPlayerInfo remote={0};
    memset(&pool,0,sizeof(pool)); memset(&bank,0,sizeof(bank)); pool.flags=SITH_SECTOR_UNDERWATER;
    strcpy(rifleModel.filename,"strg.3do");
    jkBot_Configure("Exit_Test","ky.3do"); TacticsUse(0); bot.now=5; bot.frameDt=1.0f; bot.elite=1;
    jkPlayer_maxPlayers=0; memset(jkPlayer_playerInfos,0,sizeof(jkPlayer_playerInfos));
    self.type=SITH_THING_PLAYER; self.sector=&pool; self.actorParams.pPlayer=&own; self.actorParams.health=100;
    self.moveSize=self.collideSize=0.065f; self.idx=1; self.actorParams.maxRotVelocity=200;
    sithPlayer_g_pLocalPlayerThing=&self;
    rdVector3 line={1,0,0}, bankAim={2,0,0};

    /* Headed for the climb: within 43 degrees of the line to the bank, facing
       either way along it, since forward and strafe together still push at
       full thrust. Legacy insisted on facing the bank, level. */
    PlainFace(&self,40/BOT_DEG); assert(Bot_ExitHeaded(&self,line));
    PlainFace(&self,50/BOT_DEG); assert(!Bot_ExitHeaded(&self,line));
    PlainFace(&self,3.14159265f); assert(Bot_ExitHeaded(&self,line) && "backing out pushes as hard");
    TacticsUse(1); PlainFace(&self,40/BOT_DEG); assert(!Bot_ExitHeaded(&self,line));
    PlainFace(&self,0); assert(Bot_ExitHeaded(&self,line)); TacticsUse(0);

    /* The look while climbing: as near the shot as that cone allows. */
    self.physicsParams.flags=SITH_PF_ONWATERSURFACE; PlainFace(&self,0);
    nav.exitLookValid=1;
    nav.exitLook=ExitAt(30);  assert(fabsf(ExitTurn(&self,bankAim,line)-30.0f)<0.05f && "inside the cone: on the shot");
    nav.exitLook=ExitAt(90);  assert(fabsf(ExitTurn(&self,bankAim,line)-0.75f*BOT_DEG)<0.05f && "clamped to the cone's edge");
    nav.exitLook=ExitAt(-90); assert(fabsf(ExitTurn(&self,bankAim,line)+0.75f*BOT_DEG)<0.05f);
    nav.exitLook=ExitAt(120);
    assert(fabsf(ExitTurn(&self,bankAim,line)-(180.0f-0.75f*BOT_DEG))<0.05f && "the backward cone serves too");
    nav.exitLook=ExitAt(180); assert(fabsf(fabsf(ExitTurn(&self,bankAim,line))-180.0f)<0.05f && "a shot behind: back out");
    /* Under the surface the head tilts the stroke: face the bank, level. */
    self.physicsParams.flags=0; nav.exitLook=ExitAt(90);
    assert(fabsf(ExitTurn(&self,bankAim,line))<0.05f);
    self.physicsParams.flags=SITH_PF_ONWATERSURFACE; nav.exitLookValid=0;
    assert(fabsf(ExitTurn(&self,bankAim,line))<0.05f && "no fight: face the bank");

    /* One launch spot, one swimmer: the nearer one keeps it. */
    BotNode *wet=&bot.nodes[0], *dry=&bot.nodes[1];
    bot.nNodes=2; memset(wet,0,sizeof(*wet)); memset(dry,0,sizeof(*dry));
    wet->pos=(rdVector3){0,0,0}; wet->sector=&pool; dry->pos=(rdVector3){0.6f,0,0.3f}; dry->sector=&bank;
    nav.waterExitStart=wet->pos; self.position=(rdVector3){0.10f,0,0};
    jkPlayer_maxPlayers=2; jkPlayer_playerInfos[1].flags=1; jkPlayer_playerInfos[1].playerNetId=77;
    jkPlayer_playerInfos[1].pLocalPlayer=&peer;
    peer.type=SITH_THING_PLAYER; peer.moveSize=peer.collideSize=0.065f; peer.idx=2; peer.sector=&pool;
    peer.actorParams.pPlayer=&theirs; peer.actorParams.health=100; peer.playerInfo=&remote;
    remote.rd_thing.model3=&rifleModel;
    peer.position=(rdVector3){0.05f,0,0}; assert(Bot_ExitTaken(&self,dry) && "nearer the spot");
    peer.position=(rdVector3){-0.20f,0,0}; assert(!Bot_ExitTaken(&self,dry) && "farther from it");
    peer.position=(rdVector3){-0.10f,0,0}; assert(!Bot_ExitTaken(&self,dry));
    peer.idx=0; assert(Bot_ExitTaken(&self,dry) && "a tie goes to the lower slot"); peer.idx=2;
    peer.position=(rdVector3){0.05f,0,0.5f}; assert(!Bot_ExitTaken(&self,dry) && "not on this level");
    peer.position=dry->pos; assert(Bot_ExitTaken(&self,dry) && "standing on the landing");
    peer.flags=SITH_TF_DEAD; assert(!Bot_ExitTaken(&self,dry)); peer.flags=0;

    /* Taken: the climb gives way, the spot is set aside, the plan moves on. */
    nav.jumpVelocity=self.actorParams.jumpSpeed=1.5f;
    self.physicsParams.flags=SITH_PF_USETHRUST|SITH_PF_USEGRAVITY|SITH_PF_ONWATERSURFACE;
    self.physicsParams.mass=1; self.actorParams.maxThrust=2;
    nav.waterExitFrom=0; nav.waterExitTo=1; nav.waterExitPhase=0; nav.waterExitUntil=bot.now+4;
    peer.position=(rdVector3){0.05f,0,0}; bot.goal=1; bot.routeCount=1; bot.tele.exitYields=0;
    Bot_ExitWaterMove(&self);
    assert(bot.tele.exitYields==1 && nav.waterExitUntil==0 && bot.goal==-1 && dry->avoidUntil>bot.now+3.9f);
    TacticsUse(1); dry->avoidUntil=0; nav.waterExitUntil=bot.now+4; bot.goal=1;
    Bot_ExitWaterMove(&self);
    assert(bot.tele.exitYields==1 && nav.waterExitUntil>0 && bot.goal==1 && "legacy shoves on");
    TacticsUse(0); nav.waterExitUntil=0;

    /* A heavy gun waits out the run-up, the jump and the settle on the spot. */
    nav.waterExitUntil=bot.now+4; self.position=(rdVector3){0.02f,0,0};
    nav.waterExitPhase=1;
    assert(Bot_ExitHoldsFire(&self,SITHBIN_CONCUSSION_RIFLE) && Bot_ExitHoldsFire(&self,SITHBIN_RAIL_DETONATOR));
    assert(!Bot_ExitHoldsFire(&self,SITHBIN_STORMTROOPER_RIFLE) && !Bot_ExitHoldsFire(&self,SITHBIN_REPEATER));
    nav.waterExitPhase=2; assert(Bot_ExitHoldsFire(&self,SITHBIN_CONCUSSION_RIFLE));
    nav.waterExitPhase=0; assert(Bot_ExitHoldsFire(&self,SITHBIN_CONCUSSION_RIFLE) && "settled on the spot");
    self.position=(rdVector3){0.30f,0,0}; assert(!Bot_ExitHoldsFire(&self,SITHBIN_CONCUSSION_RIFLE) && "still swimming in");
    nav.waterExitUntil=0; assert(!Bot_ExitHoldsFire(&self,SITHBIN_CONCUSSION_RIFLE));

    /* The whole climb: a rifle fires at a visible opponent while the climb
       goes on and turns into the cone. Legacy climbs blind. */
    /* The opponent stands 70 degrees off the line to the bank; the bot faces
       it, so the climb must turn it back to the cone's edge at 43. */
    self.position=(rdVector3){0.30f,0,0};
    peer.position=(rdVector3){0.30f+2.5f*cosf(70/BOT_DEG),2.5f*sinf(70/BOT_DEG),0};
    own.curWeaponID=SITHBIN_STORMTROOPER_RIFLE;
    own.aItems[SITHBIN_STORMTROOPER_RIFLE].amount=1; own.aItems[SITHBIN_STORMTROOPER_RIFLE].state=SITHINVENTORY_ITEM_AVAILABLE;
    own.aItems[SITHBIN_ENERGY].amount=100;
    PlainFace(&self,70/BOT_DEG);
    nav.waterExitPhase=0; nav.waterExitUntil=bot.now+4; bot.reactionUntil=0; bot.nextForce=0; bot.forceBin=-1;
    testLOS=1; memset(bot.keys,0,sizeof(bot.keys)); bot.rawTurn=0;
    Bot_ContinueWaterExit(&self,&peer);
    assert(bot.keys[INPUT_FUNC_FIRE1] && nav.waterExitUntil>0 && "shooting on the way out");
    assert(fabsf(bot.rawTurn-(0.75f*BOT_DEG-70.0f))<0.5f && "turning back into the climbing cone");
    TacticsUse(1); memset(bot.keys,0,sizeof(bot.keys)); bot.reactionUntil=0; nav.waterExitUntil=bot.now+4;
    Bot_ContinueWaterExit(&self,&peer);
    assert(!bot.keys[INPUT_FUNC_FIRE1] && !bot.keys[INPUT_FUNC_FIRE2]);
    TacticsUse(0);

    /* A Grip is answered even mid-climb; nothing else is cast until dry. */
    own.aItems[SITHBIN_F_ABSORB].amount=4; own.aItems[SITHBIN_F_ABSORB].state=SITHINVENTORY_ITEM_AVAILABLE;
    own.aItems[SITHBIN_FORCEMANA].amount=250; bot.forceEnabled=1;
    nav.waterExitUntil=bot.now+4; bot.forceBin=-1; bot.nextForce=0; bot.grippedUntil=0;
    memset(bot.keys,0,sizeof(bot.keys)); Bot_ForceTick(&self,&peer,0);
    assert(bot.forceBin<0 && "not gripped: the climb comes first");
    bot.grippedUntil=bot.now+0.8f; Bot_ForceTick(&self,&peer,0);
    assert(bot.forceBin==SITHBIN_F_ABSORB && bot.keys[Bot_PowerKey(SITHBIN_F_ABSORB)]);
    bot.forceBin=-1; bot.nextForce=0; bot.grippedUntil=0; nav.waterExitUntil=0;
    /* Held by Grip with Absorb up: no Pull, so the mana is there to raise
       Absorb again when it runs out. Without the Grip the Pull goes out. */
    own.aItems[SITHBIN_F_ABSORB].state|=SITHINVENTORY_ITEM_ACTIVATED; own.aItems[SITHBIN_FORCEMANA].amount=300;
    own.aItems[SITHBIN_F_PULL].amount=4; own.aItems[SITHBIN_F_PULL].state=SITHINVENTORY_ITEM_AVAILABLE;
    static SithCogSymbol pullMarker; static SithCogSymbolTable pullTable; static sithCog pullCog;
    memset(&pullMarker,0,sizeof(pullMarker)); memset(&pullTable,0,sizeof(pullTable)); memset(&pullCog,0,sizeof(pullCog));
    pullMarker.pName="victim"; pullMarker.val.type=COG_TYPE_INT; pullMarker.val.data[0]=-1;
    pullTable.aSymbols=&pullMarker; pullTable.tableSize=pullTable.numUsedSymbols=1; pullCog.pSymbolTable=&pullTable;
    testInventoryTypes[SITHBIN_F_PULL].cog=&pullCog;
    peer.position=(rdVector3){self.position.x+1.0f,self.position.y,self.position.z};
    PlainFace(&self,0); bot.competitiveForce=1; bot.reactionUntil=0;
    bot.grippedUntil=bot.now+0.8f; memset(bot.keys,0,sizeof(bot.keys)); Bot_ForceTick(&self,&peer,0);
    assert(bot.forceBin<0 && "held by Grip: no Pull");
    bot.grippedUntil=0; bot.nextForce=0; Bot_ForceTick(&self,&peer,0);
    assert(bot.forceBin==SITHBIN_F_PULL && "free again: the Pull goes out");
    testInventoryTypes[SITHBIN_F_PULL].cog=NULL; bot.competitiveForce=0;
    bot.forceBin=-1; bot.nextForce=0; bot.grippedUntil=0; nav.waterExitUntil=0;
    memset(own.aItems,0,sizeof(own.aItems));
    self.physicsParams.flags=0; jkPlayer_maxPlayers=0; memset(jkPlayer_playerInfos,0,sizeof(jkPlayer_playerInfos));
    sithPlayer_g_pLocalPlayerThing=NULL; bot.nNodes=0; bot.frameDt=0.02f;
    puts("PASS climb out: full-thrust cone, look clamped toward the shot, one swimmer per spot, heavy guns held, rifle fire on the way out, Grip still answered");
}

static void test_fix_force_jump(void)
{
    static SithWorld world;
    SithThing self; SithPlayer own;
    testPlainActive=1; plainEdge=plainWall=1e9f; plainGround.flags=0; plainLand.flags=0;
    PlainSelf(&self,&own); self.physicsParams.airDrag=0.5f;
    jkBot_Configure("Leap_Test","ky.3do"); TacticsUse(0);
    bot.world=sithWorld_g_pCurrentWorld=&world; world.gravity=4.0f;
    bot.physicsStep=1.0f/150.0f; bot.frameDt=1.0f/30.0f; nav.maxRunSpeed=1.33f;
    sithPlayer_g_pLocalPlayerThing=&self;
    flex_t seconds,hold,legacyHold;
    /* Level and slightly lower landings are flown through the standstill model
       too; before, only higher ones were. */
    BotNode a={.pos={0,0,BOT_FOOT_HEIGHT},.sector=&plainLand}, level={.pos={0.35f,0,BOT_FOOT_HEIGHT},.sector=&plainLand};
    assert(Bot_FullForceJump(&a,&level,0.25f,&seconds) && seconds>1.0f);
    TacticsUse(1); assert(!Bot_FullForceJump(&a,&level,0.25f,&seconds)); TacticsUse(0);
    /* A shelf 0.45 up behind a sheer face 0.12 away, landing 0.3 out. The
       old low arc assumed running speed through the air and took it with the
       lightest hold at any rank. From a standstill only air thrust carries the
       jumper over the lip, and only a long flight gives it time to: the light
       hold rises along the face and drops back beside it. */
    plainShelf=0.12f; plainShelfZ=0.45f;
    BotNode shelf={.pos={0.30f,0,0.45f+BOT_FOOT_HEIGHT},.sector=&plainLand};
    TacticsUse(1);
    assert(Bot_ForceJumpProfile(&a,&shelf,4,&seconds,&legacyHold) && legacyHold==0.25f);
    assert(Bot_ForceJumpProfile(&a,&shelf,1,&seconds,&legacyHold) && legacyHold==0.25f && "legacy promises it at rank one");
    TacticsUse(0);
    assert(!Bot_FullForceJump(&a,&shelf,0.25f,&seconds) && "the light hold falls back beside the face");
    assert(Bot_ForceJumpProfile(&a,&shelf,4,&seconds,&hold) && fabsf(hold-1.40f)<0.001f && seconds>1.5f);
    assert(Bot_ForceJumpProfile(&a,&shelf,3,&seconds,&hold) && fabsf(hold-1.05f)<0.001f);
    assert(!Bot_ForceJumpProfile(&a,&shelf,2,&seconds,&hold) && !Bot_ForceJumpProfile(&a,&shelf,1,&seconds,&hold));
    /* The same shelf half a unit off is out of reach from a standstill at any
       rank; a running jump is the only way, and that is a different leg. */
    plainShelf=0.5f; shelf.pos.x=0.75f;
    TacticsUse(1); assert(Bot_ForceJumpProfile(&a,&shelf,4,&seconds,&legacyHold)); TacticsUse(0);
    assert(!Bot_ForceJumpProfile(&a,&shelf,4,&seconds,&hold));
    /* jump_memory: up on the target's level, a walk from the mark, is made;
       still on the ground below is a miss. */
    bot.nNodes=2; memset(bot.nodes,0,2*sizeof(bot.nodes[0]));
    bot.nodes[0].pos=a.pos; bot.nodes[0].sector=&plainLand;
    bot.nodes[1].pos=(rdVector3){1.2f,0,0.45f+BOT_FOOT_HEIGHT}; bot.nodes[1].sector=&plainLand;
    memset(nav.failedJumps,0,sizeof(nav.failedJumps)); bot.tele.jumpMisses=0; bot.now=10;
    self.sector=&plainLand; self.position=(rdVector3){0.65f,0,0.45f+BOT_FOOT_HEIGHT};
    nav.jumpFrom=1; nav.jumpTo=2; nav.jumpTarget=bot.nodes[1].pos; Bot_JumpLanded(&self);
    assert(bot.tele.jumpMisses==0 && !Bot_JumpFailed(0,1) && "on the ledge, 0.55 from the mark");
    self.position=(rdVector3){0.40f,0,BOT_FOOT_HEIGHT};
    nav.jumpFrom=1; nav.jumpTo=2; nav.jumpTarget=bot.nodes[1].pos; Bot_JumpLanded(&self);
    assert(bot.tele.jumpMisses==1 && Bot_JumpFailed(0,1) && "below it");
    memset(nav.failedJumps,0,sizeof(nav.failedJumps)); bot.tele.jumpMisses=0; bot.nNodes=0;
    for (int i=0;i<BOT_NODES && i<4;i++) bot.nodes[i].avoidUntil=0;
    /* Following such a leg: the route moves on to the landing node once the
       bot is within 0.11 of the launch node, and from there the standstill
       flight may not make it. The bot steps onto the launch spot, facing the
       landing, and jumps from there. Before, it walked on into the face. */
    plainShelf=0.12f; shelf.pos.x=0.30f;
    bot.nNodes=2; memset(bot.nodes,0,2*sizeof(bot.nodes[0]));
    bot.nodes[0].pos=a.pos; bot.nodes[0].sector=&plainLand; bot.nodes[0].item=-1;
    bot.nodes[1]=shelf; bot.nodes[1].item=-1;
    bot.nodes[0].nEdges=1; bot.nodes[0].edges[0]=(BotEdge){1,1.0f,BOT_ROUTE_FORCEJUMP};
    bot.graphDone=1; bot.forceEnabled=1; bot.now=20; bot.nextJump=0; sithTime_g_secGameTime=20;
    own.aItems[SITHBIN_F_JUMP].amount=4; own.aItems[SITHBIN_F_JUMP].state=SITHINVENTORY_ITEM_AVAILABLE;
    own.aItems[SITHBIN_FORCEMANA].amount=400;
    #define LEAP_ROUTE() (bot.goal=1, bot.route[0]=0, bot.route[1]=1, bot.routePos=1, bot.routeCount=2, \
        bot.nextPlan=bot.now+100, bot.forceBin=-1, bot.nextForce=0, nav.forceJumpPending=0, nav.jumpUntil=0, \
        memset(bot.axes,0,sizeof(bot.axes)), memset(bot.keys,0,sizeof(bot.keys)))
    LEAP_ROUTE(); self.position=(rdVector3){-0.10f,0,BOT_FOOT_HEIGHT};
    assert(!Bot_ForceJumpProfile(&(BotNode){.pos=self.position,.sector=&plainLand},&shelf,4,&seconds,&hold));
    Bot_Navigate(&self);
    assert(bot.forceBin<0 && !nav.forceJumpPending && bot.axes[INPUT_FUNC_FORWARD]>0.1f && bot.goal==1 && "step onto the spot");
    LEAP_ROUTE(); self.position=a.pos; Bot_Navigate(&self);
    assert(nav.forceJumpPending && bot.forceBin==SITHBIN_F_JUMP && fabsf(bot.forceUntil-bot.now-1.40f)<0.001f && "jump from it");
    /* Legacy walks on toward the landing without a jump. */
    TacticsUse(1); LEAP_ROUTE(); self.position=(rdVector3){-0.10f,0,BOT_FOOT_HEIGHT}; bot.nextJump=0;
    Bot_Navigate(&self); assert(bot.forceBin==SITHBIN_F_JUMP || bot.axes[INPUT_FUNC_FORWARD]>0.1f); TacticsUse(0);
    /* A leg that cannot be made even from the spot is struck off at once. */
    plainShelf=0.5f; bot.nodes[1].pos.x=0.75f; memset(nav.failedJumps,0,sizeof(nav.failedJumps));
    LEAP_ROUTE(); self.position=a.pos; bot.nextJump=0; Bot_Navigate(&self);
    assert(bot.forceBin<0 && bot.goal==-1 && Bot_JumpFailed(0,1) && "struck, not walked into the wall");
    /* And so is one the bot cannot get back onto the spot for. */
    plainShelf=0.12f; bot.nodes[1].pos.x=0.30f; memset(nav.failedJumps,0,sizeof(nav.failedJumps));
    LEAP_ROUTE(); self.position=(rdVector3){-0.10f,0,BOT_FOOT_HEIGHT}; Bot_Navigate(&self); assert(bot.goal==1);
    bot.now+=3.1f; LEAP_ROUTE(); Bot_Navigate(&self); assert(bot.goal==-1 && Bot_JumpFailed(0,1));
    #undef LEAP_ROUTE
    memset(nav.failedJumps,0,sizeof(nav.failedJumps)); bot.nNodes=0; bot.goal=-1; bot.routeCount=bot.routePos=0;
    nav.forceJumpPending=0; bot.forceBin=-1; memset(own.aItems,0,sizeof(own.aItems));
    plainShelf=1e9f; plainShelfZ=0; testPlainActive=0;
    bot.world=sithWorld_g_pCurrentWorld=NULL; sithPlayer_g_pLocalPlayerThing=NULL;
    puts("PASS Force Jump legs flown from a standstill: level landings checked, a shelf the old arc took lightly needs a long hold and rank three, a far shelf is refused; the bot steps onto the launch spot or strikes the leg");
}

static void test_fix_jump_memory(void)
{
    static SithSector land; static SithWorld world;
    static flex_t distance[BOT_NODES]; static int parent[BOT_NODES];
    SithThing self={0}; SithPlayer own={0};
    memset(&land,0,sizeof(land));
    jkBot_Configure("JumpMemory_Test","ky.3do"); TacticsUse(0); bot.now=5; jkPlayer_maxPlayers=0;
    self.type=SITH_THING_PLAYER; self.sector=&land; self.actorParams.pPlayer=&own; self.actorParams.health=100;
    bot.world=sithWorld_g_pCurrentWorld=&world; world.numThings=0; world.numThingsLoaded=0;
    bot.graphDone=1; bot.nNodes=4;
    WaterNode(0,0,&land,-1); WaterNode(1,1.0f,&land,-1); WaterNode(2,1.5f,&land,-1); WaterNode(3,5,&land,-1);
    bot.nodes[1].pos.z=bot.nodes[2].pos.z=0.5f; /* the ledge */
    bot.nodes[0].nEdges=2;
    bot.nodes[0].edges[0]=(BotEdge){1,1.2f,BOT_ROUTE_JUMP};
    bot.nodes[0].edges[1]=(BotEdge){3,5.0f,BOT_ROUTE_WALK};
    memset(nav.failedJumps,0,sizeof(nav.failedJumps));
    /* Landed under the ledge, not on it. */
    self.position=(rdVector3){0.9f,0,0};
    nav.jumpFrom=1; nav.jumpTo=2; nav.jumpTarget=bot.nodes[1].pos; bot.goal=1; bot.routeCount=1; bot.tele.jumpMisses=0;
    Bot_JumpLanded(&self);
    assert(bot.tele.jumpMisses==1 && bot.goal==-1 && bot.routeCount==0 && !nav.jumpFrom && !nav.jumpTo);
    assert(Bot_JumpFailed(0,1) && !Bot_JumpFailed(1,0));
    assert(bot.nodes[1].avoidUntil>bot.now+29 && bot.nodes[2].avoidUntil>bot.now+29 && "the whole ledge is set aside");
    assert(bot.nodes[0].avoidUntil<=bot.now && bot.nodes[3].avoidUntil<=bot.now);
    Bot_PathDistances(&self,0,distance,parent);
    assert(distance[1]>1e19f && fabsf(distance[3]-5.0f)<0.0005f && "the failed leg is off the map");
    bot.now+=31; assert(Bot_JumpFailed(0,1) && "the leg itself stays struck for twice as long");
    bot.now+=30; assert(!Bot_JumpFailed(0,1));
    Bot_PathDistances(&self,0,distance,parent); assert(fabsf(distance[1]-1.2f)<0.0005f);
    /* A landing on the mark is not a miss. */
    self.position=(rdVector3){1.1f,0,0.5f}; nav.jumpFrom=1; nav.jumpTo=2; nav.jumpTarget=bot.nodes[1].pos;
    Bot_JumpLanded(&self); assert(bot.tele.jumpMisses==1 && !Bot_JumpFailed(0,1));
    /* The legacy table keeps no memory. */
    TacticsUse(1); self.position=(rdVector3){0.9f,0,0}; nav.jumpFrom=1; nav.jumpTo=2;
    Bot_JumpLanded(&self); assert(bot.tele.jumpMisses==1 && !Bot_JumpFailed(0,1));
    TacticsUse(0); bot.nNodes=0; bot.world=sithWorld_g_pCurrentWorld=NULL;
    puts("PASS jump memory: a miss strikes the leg and its ledge, the planner routes around it until the memory lapses, a clean landing and legacy record nothing");
}

static void test_fix_speed(void)
{
    static SithWorld world;
    SithThing self; SithPlayer own;
    testPlainActive=1; plainEdge=plainWall=plainShelf=1e9f; plainGround.flags=0; plainLand.flags=0;
    PlainSelf(&self,&own);
    jkBot_Configure("Speed_Test","ky.3do"); TacticsUse(0);
    bot.world=sithWorld_g_pCurrentWorld=&world; sithPlayer_g_pLocalPlayerThing=&self;
    bot.competitiveForce=bot.forceEnabled=1; bot.now=5; sithTime_g_secGameTime=10;
    own.aItems[SITHBIN_F_SPEED].amount=2; own.aItems[SITHBIN_F_SPEED].state=SITHINVENTORY_ITEM_AVAILABLE;
    own.aItems[SITHBIN_F_ABSORB].amount=4; own.aItems[SITHBIN_F_ABSORB].state=SITHINVENTORY_ITEM_AVAILABLE;
    own.aItems[SITHBIN_FORCEMANA].amount=100;
    #define SPEED_TRY() (bot.forceBin=-1, bot.nextForce=bot.nextSpeedProbe=0, memset(bot.keys,0,sizeof(bot.keys)), \
        memset(bot.axes,0,sizeof(bot.axes)), bot.axes[INPUT_FUNC_FORWARD]=1, Bot_TryMovementSpeed(&self), bot.forceBin==SITHBIN_F_SPEED)
    /* In a fight, with mana for Speed and two utility casts but not for
       Absorb on top: Speed goes up. The Absorb reserve used to forbid it. */
    bot.followingRoute=0;
    assert(SPEED_TRY());
    BT(SPEED_UPKEEP)=0; assert(!SPEED_TRY() && "the reserve held 260 mana back");
    own.aItems[SITHBIN_FORCEMANA].amount=300; assert(SPEED_TRY());
    /* On a walking leg whose next node is close: upkeep does not wait for a
       long straight; the old rule did. */
    bot.nNodes=1; bot.nodes[0].pos=(rdVector3){0.3f,0,BOT_FOOT_HEIGHT}; bot.nodes[0].sector=&plainLand;
    bot.route[0]=0; bot.routePos=0; bot.routeCount=1; bot.followingRoute=1; bot.routeMode=BOT_ROUTE_WALK;
    assert(!SPEED_TRY() && "old rule: the next node is too close");
    BT(SPEED_UPKEEP)=1; own.aItems[SITHBIN_FORCEMANA].amount=100; assert(SPEED_TRY());
    /* Jumps keep their own pace: a jump leg, or a running jump under way. */
    bot.routeMode=BOT_ROUTE_FORCEJUMP; assert(!SPEED_TRY());
    bot.routeMode=BOT_ROUTE_WALK; nav.runPhase=1; nav.runSeen=bot.now; assert(!SPEED_TRY());
    nav.runPhase=0; assert(SPEED_TRY());
    /* Still no cast once mana is short of the two utility casts. */
    own.aItems[SITHBIN_FORCEMANA].amount=59; assert(!SPEED_TRY());
    /* Near an opponent, where Grip takes hold, the Absorb reserve applies. */
    static SithThing near; static SithPlayer nearOwn;
    memset(&near,0,sizeof(near)); near.type=SITH_THING_PLAYER; near.sector=&plainLand;
    near.actorParams.pPlayer=&nearOwn; near.actorParams.health=100; near.position=(rdVector3){1.2f,0,BOT_FOOT_HEIGHT};
    jkPlayer_maxPlayers=2; memset(jkPlayer_playerInfos,0,sizeof(jkPlayer_playerInfos));
    jkPlayer_playerInfos[1].flags=1; jkPlayer_playerInfos[1].playerNetId=31; jkPlayer_playerInfos[1].pLocalPlayer=&near;
    bot.routeMode=BOT_ROUTE_WALK; own.aItems[SITHBIN_FORCEMANA].amount=100;
    assert(!SPEED_TRY() && "an opponent at 1.2: keep 200 for Absorb");
    near.position.x=3.0f; assert(SPEED_TRY() && "at 3.0: Speed");
    near.position.x=1.2f; own.aItems[SITHBIN_FORCEMANA].amount=260; assert(SPEED_TRY());
    jkPlayer_maxPlayers=0; memset(jkPlayer_playerInfos,0,sizeof(jkPlayer_playerInfos));
    #undef SPEED_TRY
    bot.followingRoute=0; bot.routeCount=bot.routePos=0; bot.nNodes=0; bot.forceBin=-1;
    bot.competitiveForce=0; testPlainActive=0;
    bot.world=sithWorld_g_pCurrentWorld=NULL; sithPlayer_g_pLocalPlayerThing=NULL;
    puts("PASS Speed kept up in fights and on short walking legs past the Absorb reserve, never on jumps, never below two utility casts");
}

static void test_fix_resupply(void)
{
    static SithSector land; static SithWorld world; static SithThing things[4];
    static rdModel3 concModel,pistolModel,fistsModel,rifleModel;
    SithThing self={0},armed={0},bare={0}; SithPlayer own={0},p1={0},p2={0};
    jkPlayerInfo armedInfo={0},bareInfo={0};
    memset(&land,0,sizeof(land)); memset(things,0,sizeof(things));
    strcpy(concModel.filename,"conp.3do"); strcpy(pistolModel.filename,"bryp.3do");
    strcpy(fistsModel.filename,"fistg.3do"); strcpy(rifleModel.filename,"strg.3do");
    jkBot_Configure("Resupply_Test","ky.3do"); TacticsUse(0); bot.elite=1; bot.now=5;
    self.type=SITH_THING_PLAYER; self.sector=&land; self.actorParams.pPlayer=&own; self.actorParams.health=100;
    PlainFace(&self,0);
    bot.world=sithWorld_g_pCurrentWorld=&world; world.aThings=things; world.numThings=3; world.numThingsLoaded=4;
    memset(nav.itemGuid,0,sizeof(nav.itemGuid));
    /* The stock pull makes a fresh +fpconcrifle where the victim stood. */
    SithThing *gun=&things[3];
    gun->type=SITH_THING_ITEM; gun->idx=3; gun->guid=900; gun->sector=&land;
    gun->collide=SITH_COLLIDE_SPHERE; gun->collideSize=0.04f; gun->renderData.model3=&concModel;
    strcpy(gun->aName,"+fpconcrifle"); gun->position=(rdVector3){1,0,0};
    assert(Bot_LooseWeapon(gun));
    gun->physicsParams.vel=(rdVector3){2,0,0}; assert(!Bot_LooseWeapon(gun) && "still flying to whoever pulled it");
    gun->physicsParams.vel=(rdVector3){0.1f,0,0}; assert(Bot_LooseWeapon(gun) && "sliding to a stop: fair game");
    gun->physicsParams.vel=(rdVector3){0,0,0};
    gun->collide=0; assert(!Bot_LooseWeapon(gun) && "not takeable for its first 0.2 s"); gun->collide=SITH_COLLIDE_SPHERE;
    nav.itemGuid[3]=900; assert(!Bot_LooseWeapon(gun) && "a level pickup is never loose"); nav.itemGuid[3]=0;
    gun->itemParams.flags=SITH_ITEM_BACKPACK; assert(!Bot_LooseWeapon(gun)); gun->itemParams.flags=0;
    gun->renderData.model3=&pistolModel; assert(!Bot_LooseWeapon(gun) && "the starting pistol"); gun->renderData.model3=&concModel;
    TacticsUse(1); assert(!Bot_LooseWeapon(gun) && !Bot_Transient(gun) && "legacy never looks for it"); TacticsUse(0);
    /* Worth what a missing concussion rifle is worth to an armed bot, and
       more to one out of shots. */
    own.aItems[SITHBIN_TUSKEN_PROD].amount=1; own.aItems[SITHBIN_TUSKEN_PROD].state=SITHINVENTORY_ITEM_AVAILABLE;
    own.aItems[SITHBIN_POWER].amount=40;
    assert(Bot_EquipmentValue(&self,3)==BT(VALUE_CONC));
    own.aItems[SITHBIN_TUSKEN_PROD].amount=0; own.aItems[SITHBIN_POWER].amount=0;
    assert(Bot_EquipmentValue(&self,3)==BT(VALUE_CONC)+4.0f);
    /* Out of shots: any real gun or its ammunition jumps the queue. */
    own.aItems[SITHBIN_REPEATER].amount=1; own.aItems[SITHBIN_REPEATER].state=SITHINVENTORY_ITEM_AVAILABLE;
    own.aItems[SITHBIN_POWER].amount=5;
    assert(Bot_Starved(&self));
    BotPickupKind rifle={BOT_ITEM_WEAPON,SITHBIN_STORMTROOPER_RIFLE,SITHBIN_ENERGY,500};
    assert(Bot_GunPickupValue(&self,rifle,1.0f)==12.0f && BT(VALUE_WEAPON)<12.0f);
    BotPickupKind conc={BOT_ITEM_WEAPON,SITHBIN_CONCUSSION_RIFLE,SITHBIN_POWER,500};
    assert(Bot_GunPickupValue(&self,conc,1.0f)==BT(VALUE_CONC)+4.0f && "raised alike, so the guns keep their order");
    /* A fresh choice is held for a moment, so ties at a waterline do not flip. */
    bot.armAt=bot.now-1.0f; assert(Bot_ArmHold()==1.5f);
    bot.armAt=bot.now-3.0f; assert(Bot_ArmHold()==1.15f);
    TacticsUse(1); bot.armAt=bot.now-1.0f; assert(Bot_ArmHold()==1.15f); TacticsUse(0);
    own.aItems[SITHBIN_POWER].amount=50; assert(!Bot_Starved(&self));
    assert(Bot_GunPickupValue(&self,rifle,1.0f)==BT(VALUE_WEAPON));
    /* An opponent left with fists is the easier kill: preferred over a nearer
       armed one, in targeting and in the hunt. */
    jkPlayer_maxPlayers=3; memset(jkPlayer_playerInfos,0,sizeof(jkPlayer_playerInfos));
    jkPlayer_playerInfos[1]=(SithPlayer){0}; jkPlayer_playerInfos[1].flags=1; jkPlayer_playerInfos[1].playerNetId=51;
    jkPlayer_playerInfos[1].pLocalPlayer=&armed;
    jkPlayer_playerInfos[2].flags=1; jkPlayer_playerInfos[2].playerNetId=52; jkPlayer_playerInfos[2].pLocalPlayer=&bare;
    armed.type=bare.type=SITH_THING_PLAYER; armed.sector=bare.sector=&land;
    armed.actorParams.health=bare.actorParams.health=100;
    armed.actorParams.pPlayer=&p1; bare.actorParams.pPlayer=&p2;
    armed.playerInfo=&armedInfo; bare.playerInfo=&bareInfo;
    armedInfo.rd_thing.model3=&rifleModel; bareInfo.rd_thing.model3=&fistsModel;
    armed.guid=61; bare.guid=62; armed.idx=6; bare.idx=7;
    armed.position=(rdVector3){2.0f,0,0}; bare.position=(rdVector3){3.0f,0,0};
    testLOS=1; bot.targetSlot=-1; bot.nextScan=0;
    assert(Bot_UpdateTarget(&self)==&bare && bot.targetSlot==2);
    TacticsUse(1); bot.targetSlot=-1; bot.nextScan=0;
    assert(Bot_UpdateTarget(&self)==&armed && bot.targetSlot==1 && "legacy takes the nearer");
    TacticsUse(0);
    /* No hunt while out of shots: resupply first. */
    bot.nNodes=2; WaterNode(0,0,&land,-1); WaterNode(1,2.5f,&land,-1);
    static flex_t distance[BOT_NODES]; distance[0]=0; distance[1]=2.5f;
    int slot=-1;
    assert(Bot_ElitePursuit(&self,0,distance,&slot)==1);
    own.aItems[SITHBIN_POWER].amount=5; assert(Bot_ElitePursuit(&self,0,distance,&slot)==-1);
    own.aItems[SITHBIN_POWER].amount=50;
    jkPlayer_maxPlayers=0; memset(jkPlayer_playerInfos,0,sizeof(jkPlayer_playerInfos));
    bot.nNodes=0; bot.targetSlot=-1; bot.world=sithWorld_g_pCurrentWorld=NULL;
    puts("PASS resupply: a pulled gun at rest is a pickup worth its kind, empty guns put ammunition first, disarmed opponents are preferred, no hunt without shots");
}

static void test_fix_always_run(void)
{
    static SithWorld world; static SithThing things[1];
    SithThing self; SithPlayer own;
    testPlainActive=1; plainEdge=plainWall=plainShelf=1e9f; plainShelfZ=0; plainGround.flags=0; plainLand.flags=0;
    PlainSelf(&self,&own);
    jkBot_Configure("AlwaysRun_Test","ky.3do"); TacticsUse(0); bot.now=5;
    rdVector3 east={1,0,0}, west={-1,0,0};
    /* One running stop (0.69 units) ahead: a pit refuses the run, a wall
       does not; the old runway wanted the whole body clear for that far. */
    assert(Bot_RunSafe(&self,east,0));
    plainEdge=0.5f; assert(!Bot_RunSafe(&self,east,0)); plainEdge=1e9f;
    plainWall=0.3f; assert(Bot_RunSafe(&self,east,0) && !Bot_RunClear(&self,east,1,0)); plainWall=1e9f;
    /* A step up behind a sheer face ends the look. Off a shelf: a small step
       down is run, a drop the bot could not climb back is walked. */
    plainShelf=0.3f; plainShelfZ=0.45f; assert(Bot_RunSafe(&self,east,0));
    self.position=(rdVector3){0.6f,0,0.45f+BOT_FOOT_HEIGHT}; assert(!Bot_RunSafe(&self,west,0));
    plainShelfZ=0.2f; self.position.z=0.2f+BOT_FOOT_HEIGHT; assert(Bot_RunSafe(&self,west,0));
    assert(!Bot_RunClear(&self,west,1,0) && "the old runway walked any step down");
    plainShelf=1e9f; plainShelfZ=0; self.position=(rdVector3){0,0,BOT_FOOT_HEIGHT};
    /* Off ordinary dry footing there is no run at all. */
    self.attach_flags=0; assert(!Bot_RunSafe(&self,east,0)); self.attach_flags=SITH_ATTACH_SURFACE;
    plainGround.flags=SITH_SURFACE_ICY; assert(!Bot_RunSafe(&self,east,0)); plainGround.flags=0;
    /* The last span onto a pickup is run too, unless the coast past it is unsafe. */
    bot.world=sithWorld_g_pCurrentWorld=&world; world.aThings=things; world.numThings=world.numThingsLoaded=1;
    bot.elite=1; sithPlayer_g_pLocalPlayerThing=&self;
    SithThing *gun=&things[0]; memset(gun,0,sizeof(*gun));
    gun->type=SITH_THING_ITEM; gun->idx=0; gun->guid=40; gun->signature=41; gun->sector=&plainLand;
    gun->collide=SITH_COLLIDE_SPHERE; gun->collideSize=0.1f; strcpy(gun->aName,"concrifle");
    #define APPROACH(x) (gun->position=(rdVector3){(x)+0.1f,0,0.05f}, \
        bot.armItem=1, bot.armGuid=40, bot.armSignature=41, bot.armPosition=gun->position, \
        bot.armDirect=1, bot.armNext=bot.now+10, \
        bot.armContact=(BotNode){.pos={(x),0,BOT_FOOT_HEIGHT},.sector=&plainLand,.item=0}, \
        memset(bot.axes,0,sizeof(bot.axes)), memset(bot.keys,0,sizeof(bot.keys)), Bot_ArmingMove(&self,1e20f))
    assert(APPROACH(1.1f) && bot.keys[INPUT_FUNC_FAST] && bot.axes[INPUT_FUNC_FORWARD]>0.9f);
    plainEdge=0.6f; assert(APPROACH(0.3f) && !bot.keys[INPUT_FUNC_FAST] && "a pit just past the pickup");
    plainEdge=1e9f; TacticsUse(1); assert(APPROACH(1.1f) && !bot.keys[INPUT_FUNC_FAST]); TacticsUse(0);
    #undef APPROACH
    bot.armItem=bot.armDirect=0; bot.world=sithWorld_g_pCurrentWorld=NULL; sithPlayer_g_pLocalPlayerThing=NULL;
    testPlainActive=0;
    puts("PASS always run: only a pit, a big drop or poor footing ahead stops the run; walls, steps up and small steps down do not; pickups are run onto");
}

static void test_fix_pull_on_move(void)
{
    static SithWorld world; static SithThing items[1];
    static SithCogSymbol marker; static SithCogSymbolTable table; static sithCog cog;
    SithThing self, enemy; SithPlayer own;
    int pull=SITHBIN_F_PULL;
    testPlainActive=1; plainEdge=plainWall=plainShelf=1e9f; plainShelfZ=0; plainGround.flags=0; plainLand.flags=0;
    PlainSelf(&self,&own); memset(&enemy,0,sizeof(enemy));
    assert(setenv("JK_BOT_FORCE_STYLE","competitive",1)==0);
    jkBot_Configure("PullMove_Test","ky.3do");
    assert(unsetenv("JK_BOT_FORCE_STYLE")==0);
    TacticsUse(0); bot.joined=1; bot.now=50; bot.elite=1; bot.frameDt=0.02f; jkPlayer_maxPlayers=0; testLOS=1;
    sithPlayer_g_pLocalPlayerThing=&self;
    own.aItems[pull].amount=4; own.aItems[pull].state=SITHINVENTORY_ITEM_AVAILABLE;
    own.aItems[SITHBIN_F_JUMP].amount=4; own.aItems[SITHBIN_F_JUMP].state=SITHINVENTORY_ITEM_AVAILABLE;
    own.aItems[SITHBIN_FORCEMANA].amount=400; own.curPower=SITHBIN_F_JUMP;
    memset(&marker,0,sizeof(marker)); memset(&table,0,sizeof(table)); memset(&cog,0,sizeof(cog));
    table.aSymbols=&marker; table.tableSize=table.numUsedSymbols=1; cog.pSymbolTable=&table;
    marker.pName="victim"; marker.val.type=COG_TYPE_INT; marker.val.data[0]=-1;
    testInventoryTypes[pull].cog=&cog;
    bot.world=sithWorld_g_pCurrentWorld=&world; world.aThings=items; world.numThings=world.numThingsLoaded=1;
    memset(items,0,sizeof(items));
    items[0].type=SITH_THING_ITEM; items[0].idx=0; items[0].guid=700; items[0].sector=&plainLand;
    strcpy(items[0].aName,"concrifle");
    int key=Bot_PowerKey(pull); assert(key>=0);
    #define PULL_TICK(target) (test_force_frame(), memset(bot.axes,0,sizeof(bot.axes)), Bot_ForceTick(&self,(target),180))
    #define PULL_START() (items[0].flags=0, items[0].position=(rdVector3){1.5f,0,0.05f}, \
        items[0].physicsParams.vel=(rdVector3){0,0,0}, own.curPower=SITHBIN_F_JUMP, marker.val.data[0]=-1, \
        bot.nextItemPull=0, bot.pullItemLast=0, bot.nextForce=0, bot.forceBin=-1, PULL_TICK(NULL))
    /* Aimed and cast while running at the item: it stays in reach and in
       view and comes in sooner. Legacy stood still for the whole pull. */
    PULL_START(); assert(bot.pullItem==1 && bot.pullPhase==1);
    PULL_TICK(NULL);
    assert(bot.pullPhase==2 && bot.keys[key] && bot.axes[INPUT_FUNC_FORWARD]>0.9f && bot.keys[INPUT_FUNC_FAST]);
    own.curPower=pull; bot.now+=0.3f; PULL_TICK(NULL);
    assert(bot.keys[key] && bot.axes[INPUT_FUNC_FORWARD]>0.9f && "held for the marker on the run");
    marker.val.data[0]=0; bot.now+=0.3f; PULL_TICK(NULL);
    assert(!bot.keys[key] && bot.pullPhase==3);
    /* Thrown: run onto it as it flies in. */
    items[0].position=(rdVector3){0.9f,0,0.1f}; items[0].physicsParams.vel=(rdVector3){-3,0,0};
    bot.now+=0.05f; PULL_TICK(NULL); assert(bot.pullPhase==3 && bot.axes[INPUT_FUNC_FORWARD]>0.9f);
    /* Where the way to it is unsafe, wait: it is coming to the release spot. */
    plainEdge=0.12f; bot.now+=0.05f; PULL_TICK(NULL);
    assert(bot.pullPhase==3 && bot.axes[INPUT_FUNC_FORWARD]==0 && bot.axes[INPUT_FUNC_SLIDE]==0);
    plainEdge=1e9f;
    /* A fight starting now keeps the view and the Force; the legs still chase. */
    bot.now+=0.05f; PULL_TICK(&enemy); assert(bot.pullPhase==3 && bot.axes[INPUT_FUNC_FORWARD]>0.9f);
    items[0].flags|=SITH_TF_DISABLED; bot.now+=0.05f; PULL_TICK(NULL);
    assert(!bot.pullItem && bot.tele.itemCaught==1);
    /* Marked when a fight starts: let go at once instead of cancelling. */
    bot.now+=2; PULL_START(); assert(bot.pullPhase==1); PULL_TICK(NULL); assert(bot.pullPhase==2);
    own.curPower=pull; marker.val.data[0]=0; bot.now+=0.1f; PULL_TICK(&enemy);
    assert(bot.pullPhase==3 && !bot.keys[key] && bot.forceBin<0 && bot.tele.itemPulls==2);
    items[0].flags|=SITH_TF_DISABLED; bot.now+=0.05f; PULL_TICK(NULL); assert(!bot.pullItem);
    /* Under way, closing inside 0.45 or bouncing off the ground on the run
       does not end it; the bot runs on until it has the item. */
    bot.now+=2; PULL_START(); assert(bot.pullPhase==1);
    items[0].position=(rdVector3){0.3f,0,0.05f}; PULL_TICK(NULL);
    assert(bot.pullItem==1 && bot.axes[INPUT_FUNC_FORWARD]>0.9f);
    self.attach_flags=0; PULL_TICK(NULL); assert(bot.pullItem==1 && bot.axes[INPUT_FUNC_FORWARD]>0.9f);
    self.attach_flags=SITH_ATTACH_SURFACE;
    items[0].flags|=SITH_TF_DISABLED; PULL_TICK(NULL); assert(!bot.pullItem && "taken by touch");
    /* Legacy: still throughout; a fight ends the catch. */
    TacticsUse(1); BT(ITEM_PULL)=2.0f; bot.now+=2; PULL_START(); PULL_TICK(NULL);
    assert(bot.pullPhase==2 && bot.axes[INPUT_FUNC_FORWARD]==0 && !bot.keys[INPUT_FUNC_FAST]);
    own.curPower=pull; marker.val.data[0]=0; bot.now+=0.6f; PULL_TICK(NULL); assert(bot.pullPhase==3);
    bot.now+=0.05f; PULL_TICK(&enemy); assert(!bot.pullItem);
    bot.now+=2; PULL_START(); assert(bot.pullPhase==1);
    items[0].position=(rdVector3){0.3f,0,0.05f}; PULL_TICK(NULL); assert(!bot.pullItem && "too close: given up");
    TacticsUse(0);
    #undef PULL_START
    #undef PULL_TICK
    testInventoryTypes[pull].cog=NULL; own.curPower=SITHBIN_F_JUMP; bot.forceBin=-1;
    bot.world=sithWorld_g_pCurrentWorld=NULL; sithPlayer_g_pLocalPlayerThing=NULL; testPlainActive=0;
    puts("PASS Force Pull on the move: runs at the item through the cast and onto it as it flies in, waits where the way is unsafe, lets go when a fight starts; legacy stands");
}

static void test_fix_pack_hunt(void)
{
    static SithWorld world; static SithThing things[1];
    SithThing self; SithPlayer own;
    testPlainActive=1; plainEdge=plainWall=plainShelf=1e9f; plainShelfZ=0; plainGround.flags=0; plainLand.flags=0;
    plainPool.flags=SITH_SECTOR_UNDERWATER;
    PlainSelf(&self,&own);
    jkBot_Configure("PackHunt_Test","ky.3do"); TacticsUse(0); bot.now=5; bot.elite=1;
    bot.world=sithWorld_g_pCurrentWorld=&world; world.aThings=things; world.numThings=world.numThingsLoaded=1;
    sithPlayer_g_pLocalPlayerThing=&self;
    SithThing *pack=&things[0]; memset(pack,0,sizeof(*pack));
    pack->type=SITH_THING_ITEM; pack->idx=0; pack->guid=900; pack->sector=&plainLand;
    pack->collide=SITH_COLLIDE_SPHERE; pack->collideSize=0.1f; pack->itemParams.flags=SITH_ITEM_BACKPACK;
    pack->itemParams.numBins=2;
    pack->itemParams.contents[0].binIdx=SITHBIN_CONCUSSION_RIFLE; pack->itemParams.contents[0].value=1;
    pack->itemParams.contents[1].binIdx=SITHBIN_POWER; pack->itemParams.contents[1].value=50;
    /* pack_deny: a concussion rifle in a pack is worth the walk even to a
       bot holding one with plenty of shots; before, only its ammunition. */
    own.aItems[SITHBIN_CONCUSSION_RIFLE].amount=1; own.aItems[SITHBIN_CONCUSSION_RIFLE].state=SITHINVENTORY_ITEM_AVAILABLE;
    own.aItems[SITHBIN_POWER].amount=200;
    assert(Bot_PackValue(&self,pack)==BT(PACK_DENY) && BT(PACK_DENY)==3.0f);
    TacticsUse(1); assert(Bot_PackValue(&self,pack)==1.0f); TacticsUse(0);
    own.aItems[SITHBIN_CONCUSSION_RIFLE].amount=0; own.aItems[SITHBIN_POWER].amount=0;
    assert(Bot_PackValue(&self,pack)==18.0f && "a missing rifle is still worth what it was");
    /* A pack on a shelf 0.45 up behind a sheer face. The nodes below the face
       are the nearest; only the shelf node walks onto the pack. Kept while
       the pack lies still; a shove starts over. */
    plainShelf=1.0f; plainShelfZ=0.45f;
    pack->position=(rdVector3){1.3f,0,0.45f+0.036f};
    bot.nNodes=4; bot.graphDone=1;
    RouteNode(0,0.95f,0); RouteNode(1,0.9f,0.2f); RouteNode(2,0.9f,-0.2f);
    RouteNode(3,1.9f,0); bot.nodes[3].pos.z=0.45f+BOT_FOOT_HEIGHT;
    memset(nav.packRoutes,0,sizeof(nav.packRoutes));
    BotPackRoute *kept=Bot_PackRoute(&self,pack);
    assert(kept && fabsf(kept->end.pos.x-1.3f)<0.01f && fabsf(kept->end.pos.z-(0.45f+BOT_FOOT_HEIGHT))<0.01f);
    Bot_GrowPackRoute(&self,kept);
    assert(kept->count==1 && kept->approach[0]==3 && kept->tested==4 && kept->exhausted);
    assert(Bot_PackRoute(&self,pack)==kept && kept->count==1);
    pack->position.x+=0.1f; kept=Bot_PackRoute(&self,pack); assert(kept && kept->count==0 && !kept->tested);
    /* On a pool floor the contact sphere sat on the floor and did not fit;
       lifted within reach, it does. */
    plainShelf=1e9f; plainShelfZ=0; plainPoolActive=1; plainPoolFloor=0;
    pack->sector=&plainPool; pack->position=(rdVector3){0.5f,0,-0.002f};
    BotNode end;
    assert(Bot_PackContact(&self,pack,&end) && end.sector==&plainPool && end.pos.z-self.moveSize>=0.0005f);
    TacticsUse(1); assert(!Bot_PackContact(&self,pack,&end)); TacticsUse(0);
    /* Floating 0.057 under the surface the probe above it is in the air;
       the contact is taken from the water, under the pack. */
    plainPoolSurface=0.3f; pack->position=(rdVector3){0.5f,0,0.243f};
    assert(Bot_PackContact(&self,pack,&end) && end.sector==&plainPool && end.pos.z<pack->position.z &&
           end.pos.z+self.moveSize<=plainPoolSurface);
    TacticsUse(1); assert(!Bot_PackContact(&self,pack,&end) && "the probe met the water surface"); TacticsUse(0);
    plainPoolActive=0; plainPoolSurface=1e9f; plainPool.flags=0; bot.nNodes=0;
    memset(nav.packRoutes,0,sizeof(nav.packRoutes));
    bot.world=sithWorld_g_pCurrentWorld=NULL; sithPlayer_g_pLocalPlayerThing=NULL; testPlainActive=0;
    puts("PASS dropped packs: a heavy gun is worth fetching to deny it, the way in is found from the nodes nearest the pack and kept, and a pack on a pool floor can be reached");
}

static void test_fix_lip_escape(void)
{
    SithThing self; SithPlayer own;
    testPlainActive=1; plainEdge=plainWall=plainShelf=1e9f; plainShelfZ=0; plainGround.flags=0; plainLand.flags=0;
    plainPool.flags=0;
    PlainSelf(&self,&own);
    jkBot_Configure("LipEscape_Test","ky.3do"); TacticsUse(0); bot.now=5;
    /* Feet on the lip, centre 0.057 past the edge of the floor (x<0), as Red
       stood on the Canyon Oasis walkway over the lightning ramp. Only
       headings within about 30 degrees of straight back are safe. */
    plainEdge=0; self.position=(rdVector3){0.057f,0,BOT_FOOT_HEIGHT};
    PlainFace(&self,(flex_t)(M_PI/2));
    rdVector3 along={0,1,0};
    memset(bot.axes,0,sizeof(bot.axes)); memset(bot.keys,0,sizeof(bot.keys)); bot.nextJump=0;
    Bot_Move(&self,along,0);
    rdVector3 thrust=PlainThrust(&self);
    assert(thrust.x<-0.05f && !bot.keys[INPUT_FUNC_JUMP] && bot.tele.lipSteps==1 && "stepped back onto the floor");
    TacticsUse(1);
    memset(bot.axes,0,sizeof(bot.axes)); memset(bot.keys,0,sizeof(bot.keys)); bot.nextJump=0;
    Bot_Move(&self,along,0);
    assert(bot.axes[INPUT_FUNC_FORWARD]==0 && bot.axes[INPUT_FUNC_SLIDE]==0 && !bot.keys[INPUT_FUNC_JUMP] &&
           "legacy: frozen on the lip");
    TacticsUse(0);
    /* A blocked bot with floor under it still hops as before. */
    self.position=(rdVector3){-0.5f,0,BOT_FOOT_HEIGHT}; plainWall=-0.4f;
    memset(bot.axes,0,sizeof(bot.axes)); memset(bot.keys,0,sizeof(bot.keys)); bot.nextJump=0;
    Bot_Move(&self,(rdVector3){1,0,0},0);
    assert(bot.keys[INPUT_FUNC_JUMP] && bot.axes[INPUT_FUNC_FORWARD]==0 && bot.axes[INPUT_FUNC_SLIDE]==0 &&
           "facing a wall with floor underfoot: the hop, not a turn away");
    plainWall=1e9f;
    /* Routes start from the floor underfoot: the centre is in another sector
       (plainPool here) whose node lies a metre away below the lip. */
    self.position=(rdVector3){0.057f,0,BOT_FOOT_HEIGHT}; self.sector=&plainPool;
    bot.nNodes=2;
    RouteNode(0,-0.08f,0); RouteNode(1,1.0f,0.3f); bot.nodes[1].sector=&plainPool;
    assert(Bot_Nearest(&self)==0);
    TacticsUse(1); assert(Bot_Nearest(&self)==1 && "legacy: the centre's sector only"); TacticsUse(0);
    self.sector=&plainLand; bot.nNodes=0; plainEdge=1e9f; bot.tele.lipSteps=0; testPlainActive=0;
    puts("PASS lip escape: a bot on a lip with its centre over a drop steps back onto the floor and routes from the floor underfoot; legacy froze");
}

/* Canyon Oasis in miniature: a 0.1 switch on the wall at x=1, its centre
   0.17 up, facing -x (the lightning switch stands 0.175 over its floor);
   00_lightning.cog as the level gives it, with the switch, the ramp and no
   ghosts. Nodes 0..2 lead along dry ground to the switch; 3..5 lie on the
   ramp, sector 1. */
static SithWorld trapWorld; static SithSector trapSectors[2]; static SithSurface trapSurfaces[1];
static rdVector3 trapVertices[4]; static int32_t trapCorners[4]={0,1,2,3};
static SithCogSymbol trapSymbols[5]; static SithCogSymbolTable trapTable; static sithCog trapCogs[1];
static SithSurface *LightningWorld(SithThing *self,SithPlayer *own,const char *name)
{
    testPlainActive=1; plainEdge=plainShelf=1e9f; plainWall=1.0f; plainShelfZ=0; plainGround.flags=0; plainLand.flags=0;
    PlainSelf(self,own);
    jkBot_Configure(name,"ky.3do"); TacticsUse(0); bot.now=10; bot.forceBin=-1;
    BT(TRAP_CHANCE)=1;
    self->actorParams.eyeOffset=(rdVector3){0,0,0.037f};
    memset(&trapWorld,0,sizeof(trapWorld)); memset(trapSectors,0,sizeof(trapSectors)); memset(trapSurfaces,0,sizeof(trapSurfaces));
    memset(&traps,0,sizeof(traps)); memset(&nav,0,sizeof(nav));
    bot.world=sithWorld_g_pCurrentWorld=&trapWorld; sithPlayer_g_pLocalPlayerThing=self;
    trapWorld.aSectors=trapSectors; trapWorld.numSectors=2; trapSectors[0].id=0; trapSectors[1].id=1; trapWorld.gravity=4;
    trapVertices[0]=(rdVector3){1,-0.05f,0.12f}; trapVertices[1]=(rdVector3){1,0.05f,0.12f};
    trapVertices[2]=(rdVector3){1,0.05f,0.22f}; trapVertices[3]=(rdVector3){1,-0.05f,0.22f};
    trapWorld.aVertices=trapVertices; trapWorld.numVertices=4; trapWorld.surfaces=trapSurfaces; trapWorld.numSurfaces=1;
    SithSurface *button=&trapSurfaces[0];
    button->flags=SITH_SURFACE_COG_LINKED|SITH_SURFACE_HAS_COLLISION; button->pSector=&plainLand;
    button->surfaceInfo.face.numVertices=4; button->surfaceInfo.face.vertexPosIdx=trapCorners;
    button->surfaceInfo.face.normal=(rdVector3){-1,0,0};
    plainWallSurface=button;
    static const char *names[]={"switch0","zapsector","ghost0","ghost1","ghost2"};
    static const int values[]={0,1,-1,-1,-1};
    for (int i=0;i<5;i++) {
        memset(&trapSymbols[i],0,sizeof(trapSymbols[i])); trapSymbols[i].pName=(char*)names[i];
        trapSymbols[i].val.type=SITHCOG_VALUE_INT; trapSymbols[i].val.data[0]=values[i];
    }
    memset(&trapTable,0,sizeof(trapTable)); trapTable.aSymbols=trapSymbols; trapTable.tableSize=trapTable.numUsedSymbols=5;
    memset(trapCogs,0,sizeof(trapCogs)); trapCogs[0].pSymbolTable=&trapTable; trapWorld.aCogs=trapCogs; trapWorld.numCogs=1;
    bot.nNodes=6; bot.graphDone=1;
    RouteNode(0,0,0); RouteNode(1,0.45f,0); RouteNode(2,0.85f,0);
    RouteNode(3,0,1.0f); RouteNode(4,0.4f,1.0f); RouteNode(5,0.8f,1.0f);
    for (int i=3;i<6;i++) bot.nodes[i].sector=&trapSectors[1];
    static const int links[][2]={{0,1},{1,2},{0,3},{3,4},{4,5}};
    for (int i=0;i<5;i++) { RouteEdge(links[i][0],links[i][1],BOT_ROUTE_WALK); RouteEdge(links[i][1],links[i][0],BOT_ROUTE_WALK); }
    return button;
}

/* The bot faces the switch from its spot, looking up at the switch's centre. */
static void TrapPressPose(SithThing *self,const BotTrap *trap,flex_t yaw)
{
    self->position=trap->stand.pos; PlainFace(self,yaw);
    self->actorParams.headPYR.x=atan2f(0.17f-(BOT_FOOT_HEIGHT+0.037f),0.085f)*BOT_DEG;
    memset(bot.keys,0,sizeof(bot.keys)); memset(bot.previous,0,sizeof(bot.previous));
}

static void TrapOpponent(SithThing *enemy,SithSector *sector,rdVector3 position)
{
    memset(enemy,0,sizeof(*enemy));
    enemy->type=SITH_THING_PLAYER; enemy->sector=sector; enemy->position=position; enemy->actorParams.health=100;
    jkPlayer_maxPlayers=2; memset(jkPlayer_playerInfos,0,sizeof(jkPlayer_playerInfos));
    jkPlayer_playerInfos[1].flags=1; jkPlayer_playerInfos[1].playerNetId=33; jkPlayer_playerInfos[1].pLocalPlayer=enemy;
}

static void test_fix_traps(void)
{
    static SithThing things[1];
    SithThing self, enemy; SithPlayer own;
    SithSurface *button=LightningWorld(&self,&own,"Traps_Test");
    SithSector *sectors=trapSectors;
    Bot_TrapScan(&self);
    BotTrap *trap=&traps.list[0];
    assert(traps.count==1 && trap->kind==BOT_TRAP_LIGHTNING && trap->usable && trap->standNode==2);
    assert(fabsf(trap->stand.pos.x-0.915f)<0.011f && fabsf(trap->stand.pos.z-BOT_FOOT_HEIGHT)<0.001f &&
           "close enough for the 0.165 use ray from the eye");
    assert(trap->zoneNodes==3 && traps.zone[4]==1 && !traps.zone[1]);
    assert(Bot_TrapButton(button) && !Bot_TrapButton(&plainGround));
    /* Armed: the ramp's nodes are avoided; a bot on it walks off. */
    button->surfaceInfo.face.wallCel=1; bot.now+=0.3f; Bot_TrapScan(&self);
    assert(trap->live && bot.nodes[4].avoidUntil>bot.now && bot.nodes[1].avoidUntil<=bot.now);
    self.position=bot.nodes[4].pos; self.sector=&sectors[1]; bot.nextPlan=0;
    Bot_TrapEscape(&self);
    assert(traps.exitNode==0 && bot.goal==0 && bot.tele.trapEscapes==1);
    /* Disarmed, with an opponent on the ramp and the switch 0.9 away: go. */
    button->surfaceInfo.face.wallCel=0; bot.now+=0.6f; Bot_TrapScan(&self); assert(!trap->live);
    self.position=bot.nodes[0].pos; self.sector=&plainLand; bot.goal=-1; bot.routeCount=bot.routePos=0;
    TrapOpponent(&enemy,&sectors[1],bot.nodes[5].pos);
    traps.nextConsider=0;
    assert(Bot_TrapTick(&self)==1 && traps.use==1 && !traps.phase && bot.goal==2 && traps.purpose==BOT_TRAP_SPRING);
    /* At the spot, looking at the switch: one press of the use key. */
    TrapPressPose(&self,trap,0);
    assert(Bot_TrapTick(&self)==2 && traps.phase==2 && traps.presses==1 && bot.keys[INPUT_FUNC_ACTIVATE]);
    /* The server sets the frame: sprung, and left alone for a while. */
    button->surfaceInfo.face.wallCel=1; bot.now+=0.1f;
    assert(Bot_TrapTick(&self)==0 && !traps.use && bot.tele.trapsSprung==1 && trap->nextTry>bot.now+20);
    /* Already armed: nothing to spring, whoever is on the ramp. */
    traps.nextConsider=0; trap->nextTry=0; bot.now+=0.3f;
    assert(Bot_TrapTick(&self)==0 && !traps.use);
    /* A Nar Shaddaa detonator thrown from 0.5 up, facing +x, lands ahead. */
    plainSolidFloor=1; plainWall=1e9f;
    SithThing *spot=&things[0]; memset(spot,0,sizeof(*spot));
    spot->position=(rdVector3){0,0,0.5f}; spot->sector=&plainLand;
    spot->orient.lvec=(rdVector3){1,0,0}; spot->orient.rvec=(rdVector3){0,-1,0}; spot->orient.uvec=(rdVector3){0,0,1};
    rdVector3 landing; SithSector *where=NULL;
    assert(Bot_TrapThrow(&self,spot,NULL,&landing,&where) && where==&plainLand);
    assert(landing.x>0.9f && landing.x<2.0f && fabsf(landing.y)<0.001f && landing.z<0.05f);
    plainSolidFloor=0;
    /* Legacy: bound, but neither kept clear of nor sprung. */
    TacticsUse(1); memset(&traps,0,sizeof(traps)); button->surfaceInfo.face.wallCel=0;
    for (int i=0;i<6;i++) bot.nodes[i].avoidUntil=0;
    self.position=bot.nodes[0].pos; bot.goal=-1; bot.routeCount=0; bot.now+=1;
    assert(Bot_TrapTick(&self)==0 && traps.count==1 && !traps.use);
    button->surfaceInfo.face.wallCel=1; bot.now+=0.3f; Bot_TrapScan(&self);
    assert(traps.list[0].live && bot.nodes[4].avoidUntil<=bot.now);
    TacticsUse(0);
    plainWallSurface=NULL; plainWall=1e9f; jkPlayer_maxPlayers=0; memset(jkPlayer_playerInfos,0,sizeof(jkPlayer_playerInfos));
    memset(&traps,0,sizeof(traps)); bot.nNodes=0; bot.goal=-1; bot.routeCount=0; bot.tele.trapsSprung=bot.tele.trapEscapes=0;
    bot.world=sithWorld_g_pCurrentWorld=NULL; sithPlayer_g_pLocalPlayerThing=NULL; testPlainActive=0;
    puts("PASS level traps: a lightning switch is found by its COG, its armed ramp is kept clear of and walked off, it is sprung on an opponent from a spot the use ray reaches, a detonator throw lands ahead; legacy leaves traps alone");
}

/* trap_disarm: an armed ramp is not avoided all match. */
static void test_fix_trap_disarm(void)
{
    SithThing self, enemy; SithPlayer own;
    SithSurface *button=LightningWorld(&self,&own,"Disarm_Test");
    Bot_TrapScan(&self);
    BotTrap *trap=&traps.list[0];
    assert(traps.count==1 && trap->usable && trap->standNode==2);
    /* Armed in an ambush: the ramp is kept clear of, and the ambush gets
       its time before anyone takes it down. */
    button->surfaceInfo.face.wallCel=1; bot.now+=0.3f; Bot_TrapScan(&self);
    assert(trap->live && bot.nodes[4].avoidUntil>bot.now);
    self.position=bot.nodes[0].pos; self.sector=&plainLand;
    traps.nextConsider=0; bot.now+=3.0f;
    assert(Bot_TrapTick(&self)==0 && !traps.use && "a fresh ambush is left alone");
    /* An opponent near the ramp keeps it armed however long it stands. */
    TrapOpponent(&enemy,&plainLand,(rdVector3){0.2f,0.6f,BOT_FOOT_HEIGHT});
    traps.nextConsider=0; bot.now+=60.0f;
    assert(Bot_TrapTick(&self)==0 && !traps.use && bot.nodes[4].avoidUntil>bot.now);
    /* A minute on with nobody near it: the bot walks back and switches it off. */
    jkPlayer_maxPlayers=0; traps.nextConsider=0; bot.now+=0.6f;
    assert(Bot_TrapTick(&self)==1 && traps.use==1 && traps.purpose==BOT_TRAP_DISARM && traps.startCel==1 && bot.goal==2);
    TrapPressPose(&self,trap,0);
    assert(Bot_TrapTick(&self)==2 && traps.phase==2 && bot.keys[INPUT_FUNC_ACTIVATE]);
    /* The server clears the frame: disarmed, and within half a second the
       ramp is part of the routes again. */
    button->surfaceInfo.face.wallCel=0; bot.now+=0.25f;
    assert(Bot_TrapTick(&self)==0 && !traps.use && bot.tele.trapsDisarmed==1 && !bot.tele.trapsSprung && !trap->live);
    assert(trap->nextTry>bot.now+20 && "and it is not armed again straight away");
    bot.now+=0.5f; Bot_TrapScan(&self);
    assert(bot.nodes[4].avoidUntil<=bot.now);
    /* Armed 20 s, a switch almost 4 away is past the 3.5 reach; at 50 s it is not. */
    button->surfaceInfo.face.wallCel=1; bot.now+=0.3f; Bot_TrapScan(&self); trap->nextTry=0;
    self.position=(rdVector3){-3.2f,0,BOT_FOOT_HEIGHT}; RouteNode(6,-3.0f,0);
    RouteEdge(6,0,BOT_ROUTE_WALK); RouteEdge(0,6,BOT_ROUTE_WALK); bot.nNodes=7;
    traps.nextConsider=0; bot.now+=20.0f;
    assert(Bot_TrapTick(&self)==0 && !traps.use);
    traps.nextConsider=0; bot.now+=30.0f;
    assert(Bot_TrapTick(&self)==1 && traps.purpose==BOT_TRAP_DISARM && "farther, the longer it stands");
    Bot_TrapEnd(NULL,0);
    /* Legacy: an armed ramp stays armed. */
    BT(TRAP_DISARM)=0; traps.nextConsider=0; bot.now+=0.6f; bot.goal=-1;
    assert(Bot_TrapTick(&self)==0 && !traps.use);
    TacticsUse(0);
    plainWallSurface=NULL; plainWall=1e9f; jkPlayer_maxPlayers=0; memset(jkPlayer_playerInfos,0,sizeof(jkPlayer_playerInfos));
    memset(&traps,0,sizeof(traps)); bot.nNodes=0; bot.goal=-1; bot.routeCount=0; bot.tele.trapsDisarmed=0;
    bot.world=sithWorld_g_pCurrentWorld=NULL; sithPlayer_g_pLocalPlayerThing=NULL; testPlainActive=0;
    puts("PASS trap disarm: an armed ramp is left a while and kept armed while an opponent is near it, then switched off from farther the longer it stands, and walked again within half a second; legacy leaves it armed");
}

/* Nar Shaddaa's force field in miniature: its face on the plane x=1 (y -1
   to 1, z 0 to 1.2), on at the start; a switch on the near side at
   x=-0.5 facing +x and one on the far side on the wall at x=2 facing -x,
   as m2_ffieldswitch.cog gives them. Nodes 0..2 lie on the near side,
   3..5 on the far side; node 6 stands against the field. */
static void test_fix_field(void)
{
    static SithWorld world; static SithSurface surfaces[4]; static SithSurfaceAdjoin adjoins[2];
    static rdVector3 vertices[12];
    static int32_t faceA[4]={0,1,2,3}, faceB[4]={3,2,1,0}, farButton[4]={4,5,6,7}, nearButton[4]={8,9,10,11};
    static SithCogSymbol symbols[4]; static SithCogSymbolTable table; static sithCog cogs[1];
    SithThing self; SithPlayer own;
    testPlainActive=1; plainEdge=plainShelf=1e9f; plainWall=2.0f; plainField=1.0f; plainFieldOn=1;
    plainShelfZ=0; plainGround.flags=0; plainLand.flags=0;
    PlainSelf(&self,&own);
    jkBot_Configure("Field_Test","ky.3do"); TacticsUse(0); bot.now=10; bot.forceBin=-1;
    self.actorParams.eyeOffset=(rdVector3){0,0,0.037f};
    memset(&world,0,sizeof(world)); memset(surfaces,0,sizeof(surfaces)); memset(adjoins,0,sizeof(adjoins));
    memset(&traps,0,sizeof(traps)); memset(&nav,0,sizeof(nav));
    bot.world=sithWorld_g_pCurrentWorld=&world; sithPlayer_g_pLocalPlayerThing=&self;
    world.aSectors=&plainLand; world.numSectors=1; world.gravity=4;
    vertices[0]=(rdVector3){1,-1,0}; vertices[1]=(rdVector3){1,1,0}; vertices[2]=(rdVector3){1,1,1.2f}; vertices[3]=(rdVector3){1,-1,1.2f};
    vertices[4]=(rdVector3){2,-0.05f,0.12f}; vertices[5]=(rdVector3){2,0.05f,0.12f};
    vertices[6]=(rdVector3){2,0.05f,0.22f}; vertices[7]=(rdVector3){2,-0.05f,0.22f};
    vertices[8]=(rdVector3){-0.5f,0.05f,0.12f}; vertices[9]=(rdVector3){-0.5f,-0.05f,0.12f};
    vertices[10]=(rdVector3){-0.5f,-0.05f,0.22f}; vertices[11]=(rdVector3){-0.5f,0.05f,0.22f};
    world.aVertices=vertices; world.numVertices=12; world.surfaces=surfaces; world.numSurfaces=4;
    int32_t *corners[4]={faceA,faceB,farButton,nearButton};
    static const rdVector3 normals[4]={{-1,0,0},{1,0,0},{-1,0,0},{1,0,0}};
    for (int i=0;i<4;i++) {
        surfaces[i].pSector=&plainLand; surfaces[i].surfaceInfo.face.numVertices=4;
        surfaces[i].surfaceInfo.face.vertexPosIdx=corners[i]; surfaces[i].surfaceInfo.face.normal=normals[i];
        if (i>=2) surfaces[i].flags=SITH_SURFACE_COG_LINKED|SITH_SURFACE_HAS_COLLISION;
    }
    /* On: seen but not passable, as the COG's startup leaves it. */
    surfaces[0].pAdjoin=&adjoins[0]; surfaces[1].pAdjoin=&adjoins[1];
    adjoins[0].flags=adjoins[1].flags=SITHSURF_ADJOIN_VISIBLE;
    plainWallSurface=&surfaces[2];
    static const char *names[]={"switch","switch1","damsurf","damsurf2"};
    static const int values[]={3,2,0,1};
    for (int i=0;i<4;i++) {
        memset(&symbols[i],0,sizeof(symbols[i])); symbols[i].pName=(char*)names[i];
        symbols[i].val.type=SITHCOG_VALUE_INT; symbols[i].val.data[0]=values[i];
    }
    memset(&table,0,sizeof(table)); table.aSymbols=symbols; table.tableSize=table.numUsedSymbols=4;
    memset(cogs,0,sizeof(cogs)); cogs[0].pSymbolTable=&table; world.aCogs=cogs; world.numCogs=1;
    bot.nNodes=7; bot.graphDone=1;
    RouteNode(0,-0.4f,0); RouteNode(1,0.2f,0); RouteNode(2,0.8f,0);
    RouteNode(3,1.25f,0); RouteNode(4,1.6f,0); RouteNode(5,1.9f,0); RouteNode(6,0.97f,0.5f);
    /* 2-3 is a leg built while the field was off: it goes through the face. */
    static const int links[][2]={{0,1},{1,2},{3,4},{4,5},{2,3}};
    for (int i=0;i<5;i++) { RouteEdge(links[i][0],links[i][1],BOT_ROUTE_WALK); RouteEdge(links[i][1],links[i][0],BOT_ROUTE_WALK); }
    RouteEdge(2,6,BOT_ROUTE_WALK); RouteEdge(6,1,BOT_ROUTE_WALK);
    Bot_TrapScan(&self);
    BotTrap *nearSwitch=&traps.list[0], *farSwitch=&traps.list[1];
    assert(traps.nFields==1 && traps.count==2 && nearSwitch->kind==BOT_TRAP_FIELD && farSwitch->kind==BOT_TRAP_FIELD);
    assert(nearSwitch->usable && nearSwitch->standNode==0 && nearSwitch->side==1 && nearSwitch->cel==0);
    assert(farSwitch->usable && farSwitch->standNode==5 && farSwitch->side==-1);
    assert(Bot_TrapButton(&surfaces[2]) && Bot_TrapButton(&surfaces[3]) && !Bot_TrapButton(&surfaces[0]));
    /* No ordinary leg goes through the face or ends against it; one gate
       leg each way crosses it. */
    for (int i=0;i<bot.nNodes;i++) for (int k=0;k<bot.nodes[i].nEdges;k++) {
        const BotEdge *e=&bot.nodes[i].edges[k];
        assert(e->to!=6 && "nothing ends against the field");
        if ((bot.nodes[i].pos.x<1)!=(bot.nodes[e->to].pos.x<1)) assert(e->drop==BOT_ROUTE_GATE);
    }
    assert(traps.nGates==2 && traps.fields[0].gates==2 && traps.fields[0].hugging==1);
    assert(Bot_GateCost(2,3)>3.3f && Bot_GateCost(2,3)<3.6f && "there and back to the near switch, and the press");
    assert(Bot_GateCost(3,2)>2.2f && Bot_GateCost(3,2)<2.5f && Bot_GateCost(1,2)<0);
    assert(Bot_FieldBlocks(1,4) && !Bot_FieldBlocks(0,1));
    int before=bot.nodes[1].nEdges; Bot_AddEdge(1,4,BOT_ROUTE_WALK); assert(bot.nodes[1].nEdges==before);
    /* On: from the far side the way to node 1 goes by the far switch. */
    static flex_t distance[BOT_NODES]; static int parent[BOT_NODES];
    self.position=bot.nodes[4].pos;
    Bot_PathDistances(&self,4,distance,parent);
    assert(distance[1]>3.6f && distance[1]<3.9f && parent[2]==3);
    assert(Bot_SetRoute(4,1,parent) && bot.routeCount==3 && bot.route[0]==3);
    /* Waiting at the field on the gate leg, not walking into it. */
    bot.routePos=1; bot.nextPlan=1e9f; self.position=bot.nodes[3].pos; bot.frameDt=0.02f; bot.tele.gateWait=0;
    memset(bot.axes,0,sizeof(bot.axes));
    Bot_Navigate(&self);
    assert(bot.goal==1 && bot.routePos==1 && bot.axes[INPUT_FUNC_FORWARD]==0 && bot.tele.gateWait>0);
    /* The route meets the field while it is on: go to the far switch first. */
    bot.routePos=0; self.position=bot.nodes[4].pos;
    assert(Bot_TrapTick(&self)==2 && traps.use==2 && traps.purpose==BOT_TRAP_OPEN && traps.startCel==0 && bot.goal==5);
    assert(Bot_GateCost(3,2)<0 && "no gate plans while a run is under way");
    TrapPressPose(&self,farSwitch,0);
    assert(Bot_TrapTick(&self)==2 && traps.phase==2 && bot.keys[INPUT_FUNC_ACTIVATE]);
    /* The server lets the field go: open, the run ends and the bot plans again. */
    adjoins[0].flags|=SITHSURF_ADJOIN_ALLOW_MOVEMENT; adjoins[1].flags|=SITHSURF_ADJOIN_ALLOW_MOVEMENT; plainFieldOn=0;
    bot.now+=0.25f;
    assert(Bot_TrapTick(&self)==0 && !traps.use && bot.tele.fieldsOpened==1 && farSwitch->cel==1);
    assert(bot.goal==1 && !bot.routeCount && "on to where it was headed");
    assert(Bot_GateCost(3,2)==0 && Bot_GateCost(2,3)==0);
    Bot_PathDistances(&self,4,distance,parent);
    assert(fabsf(distance[1]-1.4f)<0.01f && "straight through");
    /* Open, the gate leg is an ordinary walk. */
    assert(Bot_SetRoute(4,1,parent));
    bot.routePos=1; bot.nextPlan=1e9f; self.position=bot.nodes[3].pos; bot.tele.gateWait=0;
    Bot_Navigate(&self);
    assert(bot.goal==1 && bot.routeMode==BOT_ROUTE_WALK && bot.tele.gateWait==0);
    /* No switch that side can be worked: the field is a wall from there a while. */
    adjoins[0].flags=adjoins[1].flags=SITHSURF_ADJOIN_VISIBLE; plainFieldOn=1; bot.now+=0.3f; Bot_TrapScan(&self);
    farSwitch->nextTry=bot.now+30; Bot_PathDistances(&self,4,distance,parent);
    self.position=bot.nodes[4].pos; assert(Bot_SetRoute(4,1,parent)); bot.routePos=0; traps.nextGateCheck=0;
    assert(Bot_TrapTick(&self)==0 && !traps.use && bot.goal==-1 && Bot_GateCost(3,2)<0 && Bot_GateCost(2,3)>0);
    Bot_PathDistances(&self,4,distance,parent);
    assert(distance[1]>=1e19f);
    /* 15 seconds the first time; each time in a row after that twice as
       long, up to two minutes. */
    BotField *field=&traps.fields[0];
    assert(field->fails[1]==1 && fabsf(field->failedUntil[1]-bot.now-15.0f)<0.01f);
    static const flex_t rests[]={30,60,120,120};
    for (int i=0;i<4;i++) {
        bot.now=field->failedUntil[1]+0.1f; farSwitch->nextTry=bot.now+30;
        Bot_PathDistances(&self,4,distance,parent); assert(Bot_SetRoute(4,1,parent));
        bot.routePos=0; traps.nextGateCheck=0;
        assert(Bot_TrapTick(&self)==0 && !traps.use && bot.goal==-1);
        assert(fabsf(field->failedUntil[1]-bot.now-rests[i])<0.01f);
    }
    /* A switch past a 25-unit walk is not worth it: the way from the gate to
       the far switch made 26 long, no detour is priced through the field, and
       a route already through it gives up on it. */
    field->fails[1]=0; field->failedUntil[1]=0; farSwitch->nextTry=0;
    BotEdge *far45=NULL, *far54=NULL;
    for (int k=0;k<bot.nodes[4].nEdges;k++) if (bot.nodes[4].edges[k].to==5) far45=&bot.nodes[4].edges[k];
    for (int k=0;k<bot.nodes[5].nEdges;k++) if (bot.nodes[5].edges[k].to==4) far54=&bot.nodes[5].edges[k];
    assert(far45 && far54); far45->cost=far54->cost=26.0f;
    traps.nextDetours=traps.nextScan=0; Bot_TrapScan(&self);
    assert(Bot_GateCost(3,2)<0 && Bot_GateCost(2,3)>0 && "the near switch is still close");
    bot.goal=1; bot.route[0]=4; bot.route[1]=3; bot.route[2]=2; bot.route[3]=1; bot.routeCount=4; bot.routePos=0;
    traps.nextGateCheck=0;
    assert(Bot_TrapTick(&self)==0 && !traps.use && bot.goal==-1 && field->fails[1]==1);
    far45->cost=far54->cost=0.3f; field->fails[1]=0; field->failedUntil[1]=0;
    traps.nextDetours=traps.nextScan=0; Bot_TrapScan(&self);
    assert(Bot_GateCost(3,2)>2.2f && Bot_GateCost(3,2)<2.5f);
    /* Legacy: a field that is on is a wall, and no switch is pressed. */
    TacticsUse(1); traps.fields[0].failedUntil[1]=0; farSwitch->nextTry=0;
    Bot_PathDistances(&self,4,distance,parent);
    assert(distance[1]>=1e19f && Bot_GateCost(3,2)<0);
    TacticsUse(0); Bot_PathDistances(&self,4,distance,parent); assert(Bot_SetRoute(4,1,parent));
    TacticsUse(1); bot.routePos=0; traps.nextGateCheck=0; self.position=bot.nodes[4].pos;
    assert(Bot_TrapTick(&self)==0 && !traps.use);
    bot.routePos=1; bot.nextPlan=1e9f; self.position=bot.nodes[3].pos;
    Bot_Navigate(&self);
    assert(bot.goal==-1 && "legacy drops a route through a field that is on");
    TacticsUse(0);
    plainWallSurface=NULL; plainWall=plainField=1e9f; plainFieldOn=0;
    memset(&traps,0,sizeof(traps)); bot.nNodes=0; bot.goal=-1; bot.routeCount=0; bot.tele.fieldsOpened=0; bot.tele.gateWait=0;
    bot.world=sithWorld_g_pCurrentWorld=NULL; sithPlayer_g_pLocalPlayerThing=NULL; testPlainActive=0;
    puts("PASS force field: its COG gives two switches and the field's faces, no ordinary leg goes through it or ends against it, a gate leg crosses it, a route through it while it is on goes by the switch on that side and waits short of the field, the press opens it and the gate is walked; with no switch to work it is a wall for 15 seconds, then 30, 60 and at most 120; a switch past a 25-unit walk is not gone for; legacy treats it as a wall");
}

static void test_fix_jump_margin(void)
{
    static SithWorld world; static SithThing items[1];
    SithThing self; SithPlayer own;
    testPlainActive=1; plainEdge=plainWall=plainShelf=1e9f; plainShelfZ=0; plainGround.flags=0; plainLand.flags=0;
    PlainSelf(&self,&own);
    jkBot_Configure("JumpMargin_Test","ky.3do"); TacticsUse(0); bot.now=5; bot.elite=1;
    self.actorParams.jumpSpeed=1.5f; self.physicsParams.airDrag=0.5f;
    bot.world=sithWorld_g_pCurrentWorld=&world; world.gravity=4.0f; world.aThings=items; world.numThings=0; world.numThingsLoaded=1;
    bot.physicsStep=1.0f/30.0f; bot.frameDt=1.0f/30.0f; bot.forceEnabled=1;
    /* A ledge 1.0 up across a gap, as on Canyon Oasis: floor ends at 0.4,
       the ledge starts at 2.3. Landing 0.1 past its lip, a launch 15
       percent slow meets the face: refused. 0.4 past it, kept. */
    plainEdge=0.4f; plainShelf=2.3f; plainShelfZ=1.0f;
    BotNode a={.pos={0,0,BOT_FOOT_HEIGHT},.sector=&plainLand,.item=-1};
    BotNode close={.pos={2.4f,0,1.0f+BOT_FOOT_HEIGHT},.sector=&plainLand,.item=-1}, deep=close;
    deep.pos.x=2.7f;
    BotRunJump plan={0};
    assert(!Bot_RunJumpSolve(&self,&a,&close,4,4,&plan));
    assert(Bot_RunJumpSolve(&self,&a,&deep,4,4,&plan) && plan.force);
    TacticsUse(1); BT(RUN_JUMP)=1;
    assert(Bot_RunJumpSolve(&self,&a,&close,4,4,&plan) && "legacy took the lip landing");
    TacticsUse(0);
    plainEdge=plainShelf=1e9f; plainShelfZ=0;
    /* Gripped through the run-up, the held Force Jump still went off with
       no speed: come back down at the take-off, not toward the far side,
       and leave the leg alone a short while. */
    bot.nNodes=2; RouteNode(0,0,0); RouteNode(1,2.4f,0);
    memset(nav.runEdges,0,sizeof(nav.runEdges)); nav.runCount=1;
    nav.runEdges[0]=(BotRunJump){.from=0,.to=1,.speedRank=4,.jumpRank=4,.speed=2.3f,.hold=1.2f,.runway=0.45f,.sprint=0.33f,.force=1};
    nav.runFrom=1; nav.runTo=2; nav.runPhase=2; nav.runActive=1; nav.runSeen=bot.now; nav.runUntil=bot.now+5;
    nav.runLogged=0; nav.runSalvage=0; nav.runRelease=bot.now-0.05f;
    PlainFace(&self,0); self.attach_flags=0; self.position=(rdVector3){0.15f,0,0.45f};
    self.physicsParams.vel=(rdVector3){0.3f,0,2.8f};
    memset(bot.axes,0,sizeof(bot.axes));
    assert(Bot_RunJumpMove(&self,0,1) && nav.runSalvage && PlainThrust(&self).x<-0.1f);
    self.attach_flags=SITH_ATTACH_SURFACE; self.physicsParams.vel=(rdVector3){0,0,0};
    assert(Bot_RunJumpMove(&self,0,1) && !nav.runSalvage && !nav.runPhase &&
           fabsf(nav.runEdges[0].failedUntil-(bot.now+15))<0.01f);
    /* At speed, the flight still pushes on toward the ledge. */
    nav.runFrom=1; nav.runTo=2; nav.runPhase=2; nav.runActive=1; nav.runSeen=bot.now; nav.runLogged=0;
    nav.runEdges[0].failedUntil=0; self.attach_flags=0; self.physicsParams.vel=(rdVector3){2.2f,0,2.8f};
    memset(bot.axes,0,sizeof(bot.axes));
    assert(Bot_RunJumpMove(&self,0,1) && !nav.runSalvage && PlainThrust(&self).x>0.1f);
    TacticsUse(1); nav.runLogged=0; self.physicsParams.vel=(rdVector3){0.3f,0,2.8f}; memset(bot.axes,0,sizeof(bot.axes));
    assert(Bot_RunJumpMove(&self,0,1) && !nav.runSalvage && PlainThrust(&self).x>0.1f && "legacy pushes on regardless");
    TacticsUse(0);
    nav.runPhase=nav.runFrom=nav.runTo=nav.runActive=0; nav.runCount=0; bot.nNodes=0;
    self.attach_flags=SITH_ATTACH_SURFACE; bot.forceEnabled=0;
    bot.world=sithWorld_g_pCurrentWorld=NULL; testPlainActive=0;
    puts("PASS jump margin: a ledge landing just past its lip is refused unless a launch 15 percent slow still lands; a launch far too slow comes back down at the take-off; legacy pushes on");
}

/* fjump_margin: a shelf 1.07 up behind a face 0.10 away is made from a
   standstill at 60 and 40 frames a second and missed at 30, as leg 144-83
   on Nar Shaddaa was. Air thrust comes once a frame. */
static void test_fix_fjump_margin(void)
{
    static SithWorld world;
    SithThing self; SithPlayer own;
    testPlainActive=1; plainEdge=plainWall=1e9f; plainGround.flags=0; plainLand.flags=0;
    PlainSelf(&self,&own); self.physicsParams.airDrag=0.5f;
    jkBot_Configure("FJMargin_Test","ky.3do"); TacticsUse(0);
    bot.world=sithWorld_g_pCurrentWorld=&world; world.gravity=4.0f; nav.maxRunSpeed=1.33f;
    sithPlayer_g_pLocalPlayerThing=&self;
    plainShelf=0.10f; plainShelfZ=1.07f;
    BotNode a={.pos={0,0,BOT_FOOT_HEIGHT},.sector=&plainLand};
    BotNode shelf={.pos={0.25f,0,1.07f+BOT_FOOT_HEIGHT},.sector=&plainLand};
    flex_t seconds,hold;
    /* Running at 60: made on the full hold. */
    bot.physicsStep=bot.frameDt=bot.frameSmooth=1.0f/60.0f; nav.fjBuild=0;
    assert(Bot_ForceJumpProfile(&a,&shelf,4,&seconds,&hold) && fabsf(hold-1.40f)<0.001f);
    /* Built into the graph on those same frames: refused, as it would be
       missed at 25. Before, the graph kept it and the bot, running at 30,
       refused it at the launch spot. */
    nav.fjBuild=1;
    assert(!Bot_ForceJumpProfile(&a,&shelf,4,&seconds,&hold));
    /* One fast frame in a bot that averages 30 does not pass it. */
    nav.fjBuild=0; bot.frameSmooth=1.0f/30.0f;
    assert(!Bot_ForceJumpProfile(&a,&shelf,4,&seconds,&hold));
    /* With a fixed physics step the thrust still comes once a frame. */
    bot.physicsStep=1.0f/150.0f; bot.frameSmooth=1.0f/60.0f; nav.fjBuild=1;
    assert(!Bot_ForceJumpProfile(&a,&shelf,4,&seconds,&hold));
    nav.fjBuild=0; assert(Bot_ForceJumpProfile(&a,&shelf,4,&seconds,&hold));
    /* Legacy builds it on the frame in hand. */
    TacticsUse(1); BT(FJUMP_STANDSTILL)=1; bot.physicsStep=bot.frameDt=1.0f/60.0f; nav.fjBuild=1;
    assert(Bot_ForceJumpProfile(&a,&shelf,4,&seconds,&hold));
    TacticsUse(0);
    nav.fjBuild=0; bot.frameSmooth=0; plainShelf=1e9f; plainShelfZ=0; testPlainActive=0;
    bot.world=sithWorld_g_pCurrentWorld=NULL; sithPlayer_g_pLocalPlayerThing=NULL;
    puts("PASS fjump margin: a standstill Force Jump is flown at the averaged frame time, and one built into the graph must still be made at 25 frames a second; legacy builds on the frame in hand");
}

/* lift_call: a lift standing still away from the stop wanted. The lift's
   stops are 2 apart; its deck here is node 0 at the origin, up there node 1.
   A call button beside the deck on the wall at x=0.3, its centre 0.17 up,
   facing -x; a threshold adjoin at x=-0.4 facing -x onto the landing,
   node 2 at x=-0.7. 00_elev_switch2.cog names the elevator, the button as
   call0 and the threshold as lower_adjoin0. */
static void test_fix_lift_call(void)
{
    static SithWorld world; static SithThing things[1]; static SithPathFrame frames[2];
    static SithSurface surfaces[3]; static SithSurfaceAdjoin adjoin;
    static rdVector3 vertices[12];
    static int32_t buttonFace[4]={0,1,2,3}, thresholdFace[4]={4,5,6,7}, solidFace[4]={8,9,10,11};
    static SithCogSymbol symbols[5]; static SithCogSymbolTable table; static sithCog cogs[1];
    SithThing self; SithPlayer own;
    testPlainActive=1; plainEdge=plainShelf=plainField=1e9f; plainFieldOn=0; plainWall=0.30f; plainShelfZ=0;
    plainGround.flags=0; plainLand.flags=0;
    PlainSelf(&self,&own);
    jkBot_Configure("Lift_Test","ky.3do"); TacticsUse(0); bot.now=10; bot.nextUse=0;
    self.actorParams.eyeOffset=(rdVector3){0,0,0.037f};
    memset(&world,0,sizeof(world)); memset(surfaces,0,sizeof(surfaces)); memset(&adjoin,0,sizeof(adjoin));
    memset(&traps,0,sizeof(traps)); memset(&nav,0,sizeof(nav));
    bot.world=sithWorld_g_pCurrentWorld=&world; sithPlayer_g_pLocalPlayerThing=&self;
    world.aSectors=&plainLand; world.numSectors=1; world.gravity=4;
    /* The lift: a path thing with two frames, standing at the stop here. */
    memset(things,0,sizeof(things)); frames[0].pos=(rdVector3){0,0,0}; frames[1].pos=(rdVector3){0,0,2};
    things[0].type=SITH_THING_COG; things[0].moveType=SITH_MT_PATH; things[0].sector=&plainLand;
    things[0].trackParams.aFrames=frames; things[0].trackParams.loadedFrames=2; things[0].position=frames[0].pos;
    world.aThings=things; world.numThings=0; world.numThingsLoaded=1;
    vertices[0]=(rdVector3){0.30f,0.05f,0.12f}; vertices[1]=(rdVector3){0.30f,-0.05f,0.12f};
    vertices[2]=(rdVector3){0.30f,-0.05f,0.22f}; vertices[3]=(rdVector3){0.30f,0.05f,0.22f};
    vertices[4]=(rdVector3){-0.4f,-0.3f,0}; vertices[5]=(rdVector3){-0.4f,0.3f,0};
    vertices[6]=(rdVector3){-0.4f,0.3f,0.3f}; vertices[7]=(rdVector3){-0.4f,-0.3f,0.3f};
    vertices[8]=(rdVector3){-0.4f,0.4f,0}; vertices[9]=(rdVector3){-0.4f,0.5f,0};
    vertices[10]=(rdVector3){-0.4f,0.5f,0.3f}; vertices[11]=(rdVector3){-0.4f,0.4f,0.3f};
    world.aVertices=vertices; world.numVertices=12; world.surfaces=surfaces; world.numSurfaces=3;
    int32_t *corners[3]={buttonFace,thresholdFace,solidFace};
    for (int i=0;i<3;i++) {
        surfaces[i].pSector=&plainLand; surfaces[i].surfaceInfo.face.numVertices=4;
        surfaces[i].surfaceInfo.face.vertexPosIdx=corners[i];
        surfaces[i].surfaceInfo.face.normal=(rdVector3){-1,0,0};
    }
    surfaces[0].flags=SITH_SURFACE_COG_LINKED|SITH_SURFACE_HAS_COLLISION;
    surfaces[1].pAdjoin=&adjoin; adjoin.flags=SITHSURF_ADJOIN_VISIBLE|SITHSURF_ADJOIN_ALLOW_MOVEMENT;
    surfaces[1].flags=SITH_SURFACE_COG_LINKED;
    plainWallSurface=&surfaces[0];
    static const char *names[]={"elevator","call0","call1","lower_adjoin0","lower_adjoin1"};
    static const int values[]={0,0,7,1,2};
    for (int i=0;i<5;i++) {
        memset(&symbols[i],0,sizeof(symbols[i])); symbols[i].pName=(char*)names[i];
        symbols[i].val.type=SITHCOG_VALUE_INT; symbols[i].val.data[0]=values[i];
    }
    memset(&table,0,sizeof(table)); table.aSymbols=symbols; table.tableSize=table.numUsedSymbols=5;
    memset(cogs,0,sizeof(cogs)); cogs[0].pSymbolTable=&table; world.aCogs=cogs; world.numCogs=1;
    bot.nNodes=4; bot.graphDone=1;
    RouteNode(0,0,0); RouteNode(1,0,0); bot.nodes[1].pos.z+=2; RouteNode(2,-0.7f,0); RouteNode(3,0.9f,0);
    nav.liftCount=1; nav.lifts[0].thing=0; nav.lifts[0].node[0]=0; nav.lifts[0].node[1]=1;
    nav.liftForNode[0]=nav.liftForNode[1]=1;
    BotLift *lift=&nav.lifts[0];
    /* Bound from the COG: one button in range, one threshold with an
       adjoin; call1 names no surface and lower_adjoin1 is solid. */
    Bot_BindLifts();
    assert(lift->buttons==1 && lift->button[0]==0 && lift->thresholds==1 && lift->threshold[0]==1);
    #define LIFT_STILL(seconds) (nav.liftTrack=1, nav.liftSeen=things[0].position, nav.liftMovedAt=bot.now-(seconds), \
        nav.liftWaitAt=0, nav.liftStep=0, bot.nextUse=0, bot.goal=1, bot.routeCount=2, \
        memset(bot.axes,0,sizeof(bot.axes)), memset(bot.keys,0,sizeof(bot.keys)), memset(bot.previous,0,sizeof(bot.previous)))
    /* Riding it up, beside the button: a lift that has only just stopped is
       waited out. */
    self.attach_flags=SITH_ATTACH_THINGFACE; self.attachedThing=&things[0];
    self.position=(rdVector3){0.12f,0,BOT_FOOT_HEIGHT}; PlainFace(&self,0);
    LIFT_STILL(0.3f); bot.tele.liftCalls=bot.tele.liftSteps=0;
    assert(Bot_LiftMove(&self,0,1) && !bot.keys[INPUT_FUNC_ACTIVATE] && bot.axes[INPUT_FUNC_FORWARD]==0);
    /* Still 0.8 seconds away from the stop wanted: press its button. */
    LIFT_STILL(1.0f);
    assert(Bot_LiftMove(&self,0,1) && bot.keys[INPUT_FUNC_ACTIVATE] && bot.tele.liftCalls==1 && !nav.liftStep);
    /* In the middle of the deck the button is past a rider's reach: step
       off across the threshold onto the landing, and plan again from there. */
    self.position=(rdVector3){0,0,BOT_FOOT_HEIGHT}; PlainFace(&self,180/BOT_DEG);
    LIFT_STILL(1.0f);
    assert(Bot_LiftMove(&self,0,1) && !bot.keys[INPUT_FUNC_ACTIVATE] && nav.liftStep==3 && bot.tele.liftSteps==1);
    self.position.x=-0.2f; memset(bot.axes,0,sizeof(bot.axes));
    assert(Bot_LiftMove(&self,0,1) && nav.liftStep==3 && PlainThrust(&self).x<-0.1f && bot.goal==1);
    self.position.x=-0.52f; self.attach_flags=SITH_ATTACH_SURFACE; self.attachedThing=NULL;
    assert(Bot_LiftMove(&self,0,1) && !nav.liftStep && bot.goal==-1 && !bot.routeCount);
    /* A button that has not brought the lift in four seconds: step off. */
    self.attach_flags=SITH_ATTACH_THINGFACE; self.attachedThing=&things[0];
    self.position=(rdVector3){0.12f,0,BOT_FOOT_HEIGHT}; PlainFace(&self,0);
    LIFT_STILL(4.5f);
    assert(Bot_LiftMove(&self,0,1) && !bot.keys[INPUT_FUNC_ACTIVATE] && nav.liftStep==3 && bot.tele.liftSteps==2);
    /* On a landing, the lift standing still at the other stop: walk up to the
       call button on the landing's wall and press it. */
    self.attach_flags=SITH_ATTACH_SURFACE; self.attachedThing=NULL; things[0].position=frames[1].pos;
    plainWall=1.30f;
    for (int i=0;i<4;i++) vertices[i].x=1.30f;
    self.position=bot.nodes[3].pos; PlainFace(&self,0);
    LIFT_STILL(1.0f);
    assert(Bot_LiftMove(&self,3,0) && !bot.keys[INPUT_FUNC_ACTIVATE] && bot.axes[INPUT_FUNC_FORWARD]>0.3f);
    self.position.x=1.15f; LIFT_STILL(1.0f);
    assert(Bot_LiftMove(&self,3,0) && bot.keys[INPUT_FUNC_ACTIVATE] && bot.tele.liftCalls==2);
    /* A lift on its way is waited for. */
    LIFT_STILL(0.2f);
    assert(Bot_LiftMove(&self,3,0) && !bot.keys[INPUT_FUNC_ACTIVATE] && bot.axes[INPUT_FUNC_FORWARD]==0 && nav.waitUntil>bot.now);
    /* Come to its stop, it is boarded only once it has stood still a moment:
       a stock lift ignores a crossing onto it while it moves. */
    things[0].position=frames[0].pos; PlainFace(&self,180/BOT_DEG); LIFT_STILL(0.1f);
    assert(Bot_LiftMove(&self,3,0) && bot.axes[INPUT_FUNC_FORWARD]==0 && nav.waitUntil>bot.now);
    LIFT_STILL(0.5f);
    assert(Bot_LiftMove(&self,3,0) && bot.axes[INPUT_FUNC_FORWARD]>0.3f && nav.waitUntil==0);
    TacticsUse(1); LIFT_STILL(0.1f);
    assert(Bot_LiftMove(&self,3,0) && bot.axes[INPUT_FUNC_FORWARD]>0.3f && "legacy boards at once");
    TacticsUse(0); things[0].position=frames[1].pos;
    /* leg_axis: the threshold is an opening 0.2 wide. Off its axis on the
       deck, the straight way off clips the jamb: get onto the axis first,
       whether walking off at the stop or stepping off a lift that will not
       move. */
    plainSlotX=-0.4f; plainSlotLo=-0.1f; plainSlotHi=0.1f;
    self.attach_flags=SITH_ATTACH_THINGFACE; self.attachedThing=&things[0]; things[0].position=frames[0].pos;
    self.position=(rdVector3){-0.25f,0.09f,BOT_FOOT_HEIGHT}; PlainFace(&self,180/BOT_DEG);
    LIFT_STILL(1.0f); bot.tele.legAxis=0; bot.frameDt=0.03f;
    assert(Bot_LiftMove(&self,0,2) && bot.tele.legAxis>0 && PlainThrust(&self).y<-0.2f);
    things[0].position=frames[1].pos; LIFT_STILL(1.0f); nav.liftStep=3; nav.liftStepAt=(rdVector3){-0.4f,0,0.15f};
    nav.liftStepNormal=(rdVector3){-1,0,0}; nav.liftStepUntil=bot.now+3; bot.tele.legAxis=0;
    assert(Bot_LiftMove(&self,0,1) && nav.liftStep==3 && bot.tele.legAxis>0 && PlainThrust(&self).y<-0.2f);
    self.position.y=0.005f; memset(bot.axes,0,sizeof(bot.axes)); bot.tele.legAxis=0;
    assert(Bot_LiftMove(&self,0,1) && bot.tele.legAxis==0 && PlainThrust(&self).x<-0.5f && "on the axis: straight out");
    TacticsUse(1); self.position.y=0.09f; nav.liftStep=0; things[0].position=frames[0].pos; LIFT_STILL(1.0f); bot.tele.legAxis=0;
    assert(Bot_LiftMove(&self,0,2) && bot.tele.legAxis==0 && "legacy: no step onto the axis"); TacticsUse(0);
    plainSlotX=1e9f; nav.liftStep=0; self.position=bot.nodes[3].pos;
    self.attach_flags=SITH_ATTACH_SURFACE; self.attachedThing=NULL; things[0].position=frames[1].pos;
    /* Legacy: the use key, every 1.2 seconds, wherever the bot looks. */
    TacticsUse(1); PlainFace(&self,180/BOT_DEG); LIFT_STILL(5.0f);
    assert(Bot_LiftMove(&self,3,0) && bot.keys[INPUT_FUNC_ACTIVATE] && bot.tele.liftCalls==2 && bot.axes[INPUT_FUNC_FORWARD]==0);
    self.attach_flags=SITH_ATTACH_THINGFACE; self.attachedThing=&things[0]; self.position=(rdVector3){0,0,BOT_FOOT_HEIGHT};
    things[0].position=frames[0].pos; LIFT_STILL(5.0f);
    assert(Bot_LiftMove(&self,0,1) && !nav.liftStep && bot.tele.liftSteps==2);
    TacticsUse(0);
    #undef LIFT_STILL
    plainWallSurface=NULL; plainWall=1e9f; memset(&nav,0,sizeof(nav)); bot.nNodes=0; bot.goal=-1; bot.routeCount=0;
    bot.tele.liftCalls=bot.tele.liftSteps=0;
    bot.world=sithWorld_g_pCurrentWorld=NULL; sithPlayer_g_pLocalPlayerThing=NULL; testPlainActive=0;
    puts("PASS lift call: a lift's COG gives its call buttons and thresholds; a lift standing still away from the stop wanted is sent with a button in a rider's reach, or else stepped off across the threshold and planned from the landing; one not answering its button in four seconds is stepped off too; from a landing the bot walks up to the call button; a moving lift is waited for and boarded once it has stood still a moment; off the axis of a narrow threshold the bot gets onto it before walking or stepping off; legacy presses blindly and boards at once");
}

/* dead_end: Bespin's pit in miniature. The bot stands on a floor door
   (a captured path thing) by node 0, which has no leg anywhere; nodes 1 to
   9 hang together a little way off. */
static void test_fix_dead_end(void)
{
    static SithWorld world; static SithThing things[1];
    SithThing self; SithPlayer own;
    testPlainActive=1; plainEdge=plainShelf=plainWall=plainField=1e9f; plainFieldOn=0; plainShelfZ=0;
    plainGround.flags=0; plainLand.flags=0;
    PlainSelf(&self,&own);
    jkBot_Configure("DeadEnd_Test","ky.3do"); TacticsUse(0); bot.now=10; bot.nextUse=0; bot.forceBin=-1;
    self.actorParams.eyeOffset=(rdVector3){0,0,0.037f};
    memset(&world,0,sizeof(world)); memset(&traps,0,sizeof(traps)); memset(&nav,0,sizeof(nav));
    bot.world=sithWorld_g_pCurrentWorld=&world; sithPlayer_g_pLocalPlayerThing=&self;
    world.aSectors=&plainLand; world.numSectors=1; world.gravity=4;
    memset(things,0,sizeof(things)); things[0].type=SITH_THING_COG; things[0].moveType=SITH_MT_PATH;
    things[0].flags=SITH_TF_CAPTURED|SITH_TF_STANDABLE; things[0].sector=&plainLand;
    world.aThings=things; world.numThings=0; world.numThingsLoaded=1;
    plainFloorThing=&things[0];
    bot.nNodes=10; bot.graphDone=1;
    RouteNode(0,0.05f,0);
    for (int i=1;i<10;i++) RouteNode(i,3.0f+0.4f*i,0);
    for (int i=1;i<9;i++) { RouteEdge(i,i+1,BOT_ROUTE_WALK); RouteEdge(i+1,i,BOT_ROUTE_WALK); }
    self.attach_flags=SITH_ATTACH_THING; self.attachedThing=&things[0]; self.position=(rdVector3){0,0,BOT_FOOT_HEIGHT};
    bot.goal=-1; bot.targetSlot=-1; bot.tele.deadEndUses=0;
    #define DEAD_TICK() (memset(bot.keys,0,sizeof(bot.keys)), memset(bot.previous,0,sizeof(bot.previous)), \
        memset(bot.axes,0,sizeof(bot.axes)), bot.rawPitch=0, Bot_DeadEnd(&self))
    /* Two seconds with nothing to do first. */
    assert(!DEAD_TICK()); bot.now+=1.0f; assert(!DEAD_TICK());
    /* Then: node 0 reaches nothing. Looking ahead, the use ray finds no door:
       turn the view down. */
    bot.now+=1.1f;
    assert(DEAD_TICK() && nav.deadReach==1 && bot.rawPitch<0 && !bot.keys[INPUT_FUNC_ACTIVATE]);
    /* Looking down 80 degrees, as far as a player's head goes: press use on it. */
    self.actorParams.headPYR.x=-80;
    assert(DEAD_TICK() && bot.keys[INPUT_FUNC_ACTIVATE] && bot.tele.deadEndUses==1);
    /* Not again until the use key is free. */
    bot.now+=0.5f; assert(DEAD_TICK() && !bot.keys[INPUT_FUNC_ACTIVATE]);
    /* A recovery jump or a shot at someone above waits, without starting
       the count again. */
    self.attach_flags=0; bot.now+=1.5f; assert(!DEAD_TICK() && nav.deadSince>0);
    self.attach_flags=SITH_ATTACH_THING; bot.targetSlot=2; assert(!DEAD_TICK() && nav.deadSince>0);
    bot.targetSlot=-1; assert(DEAD_TICK() && bot.keys[INPUT_FUNC_ACTIVATE] && bot.tele.deadEndUses==2);
    /* Off the door, the escape leaves the bot to recovery. */
    self.attach_flags=SITH_ATTACH_SURFACE; self.attachedThing=NULL; bot.now+=1.0f;
    assert(!DEAD_TICK());
    /* Among nodes that lead somewhere it is no dead end. */
    self.attach_flags=SITH_ATTACH_THING; self.attachedThing=&things[0]; self.position=bot.nodes[5].pos;
    nav.deadCheckAt=0; bot.now+=1.0f;
    assert(!DEAD_TICK() && nav.deadReach==9);
    /* A goal ends it. */
    self.position=(rdVector3){0,0,BOT_FOOT_HEIGHT}; bot.goal=4; assert(!DEAD_TICK() && !nav.deadSince);
    /* Legacy leaves it to recovery. */
    bot.goal=-1; TacticsUse(1); bot.now+=5.0f; assert(!DEAD_TICK()); bot.now+=3.0f; assert(!DEAD_TICK());
    TacticsUse(0);
    /* A door in two pieces, as Bespin's hatch, moved by one 00_door.cog:
       over the seam where they part first, then the press. */
    static SithThing pair[2]; static SithCogSymbol doors[2]; static SithCogSymbolTable doorTable; static sithCog doorCog[1];
    memset(pair,0,sizeof(pair));
    for (int i=0;i<2;i++) {
        pair[i].type=SITH_THING_COG; pair[i].moveType=SITH_MT_PATH; pair[i].flags=SITH_TF_CAPTURED|SITH_TF_STANDABLE;
        pair[i].sector=&plainLand; pair[i].position=(rdVector3){i ? 0.15f : -0.15f,0,0};
    }
    world.aThings=pair; world.numThings=1; world.numThingsLoaded=2; plainFloorThing=&pair[0];
    static const char *doorNames[]={"door0","door1"};
    for (int i=0;i<2;i++) {
        memset(&doors[i],0,sizeof(doors[i])); doors[i].pName=(char*)doorNames[i];
        doors[i].val.type=SITHCOG_VALUE_INT; doors[i].val.data[0]=i;
    }
    memset(&doorTable,0,sizeof(doorTable)); doorTable.aSymbols=doors; doorTable.tableSize=doorTable.numUsedSymbols=2;
    memset(doorCog,0,sizeof(doorCog)); doorCog[0].pSymbolTable=&doorTable; world.aCogs=doorCog; world.numCogs=1;
    self.attach_flags=SITH_ATTACH_THING; self.attachedThing=&pair[0]; self.position=(rdVector3){-0.12f,0,BOT_FOOT_HEIGHT};
    PlainFace(&self,0); self.actorParams.headPYR.x=-80; bot.goal=-1; nav.deadSince=0; nav.deadCheckAt=0;
    assert(!DEAD_TICK()); bot.now+=2.1f; bot.tele.deadEndUses=0;
    assert(DEAD_TICK() && !bot.keys[INPUT_FUNC_ACTIVATE] && PlainThrust(&self).x>0.1f && "to the seam");
    self.position.x=-0.04f; bot.now+=0.5f;
    assert(DEAD_TICK() && bot.keys[INPUT_FUNC_ACTIVATE] && bot.tele.deadEndUses==1 && "near enough over it: press");
    /* Over the seam the ray may meet the other piece: pressed all the same. */
    plainFloorThing=&pair[1]; bot.now+=1.3f;
    assert(DEAD_TICK() && bot.keys[INPUT_FUNC_ACTIVATE] && bot.tele.deadEndUses==2);
    /* Away from the seam it never presses: pressed there, the door pinned
       the bot to the wall. After two seconds it hops toward the seam. */
    plainFloorThing=&pair[0]; self.position.x=-0.12f; nav.deadSeamUntil=0; bot.now+=1.3f; bot.nextJump=0;
    assert(DEAD_TICK() && !bot.keys[INPUT_FUNC_ACTIVATE] && !bot.keys[INPUT_FUNC_JUMP] && PlainThrust(&self).x>0.1f);
    bot.now+=2.1f;
    assert(DEAD_TICK() && !bot.keys[INPUT_FUNC_ACTIVATE] && bot.keys[INPUT_FUNC_JUMP] && bot.tele.deadEndUses==2);
    world.aCogs=NULL; world.numCogs=0;
    #undef DEAD_TICK
    plainFloorThing=NULL; self.actorParams.headPYR.x=0; memset(&nav,0,sizeof(nav)); bot.nNodes=0; bot.goal=-1;
    bot.tele.deadEndUses=0;
    bot.world=sithWorld_g_pCurrentWorld=NULL; sithPlayer_g_pLocalPlayerThing=NULL; testPlainActive=0;
    puts("PASS dead end: with no goal for two seconds where the nearest node reaches nothing, a bot on a floor door looks down and presses use once the ray meets it, from over the seam where a two-piece door parts; a jump or a fight waits without restarting the count; off a door, among nodes that lead on, with a goal or in legacy it is left to recovery");
}

/* leg_axis: a door alcove's mouth 0.2 wide in a wall at x=1; node 0 on its
   axis in front, node 1 through it. */
static void test_fix_leg_axis(void)
{
    static SithWorld world;
    SithThing self; SithPlayer own;
    testPlainActive=1; plainEdge=plainShelf=plainWall=plainField=1e9f; plainFieldOn=0; plainShelfZ=0;
    plainGround.flags=0; plainLand.flags=0;
    plainSlotX=1.0f; plainSlotLo=-0.1f; plainSlotHi=0.1f;
    PlainSelf(&self,&own);
    jkBot_Configure("LegAxis_Test","ky.3do"); TacticsUse(0); bot.now=10; bot.forceBin=-1;
    memset(&world,0,sizeof(world)); memset(&traps,0,sizeof(traps)); memset(&nav,0,sizeof(nav));
    bot.world=sithWorld_g_pCurrentWorld=&world; sithPlayer_g_pLocalPlayerThing=&self;
    world.aSectors=&plainLand; world.numSectors=1; world.gravity=4;
    bot.nNodes=2; bot.graphDone=1;
    RouteNode(0,0.7f,0); RouteNode(1,1.2f,0);
    RouteEdge(0,1,BOT_ROUTE_WALK); RouteEdge(1,0,BOT_ROUTE_WALK);
    #define AXIS_STEP(x,y) (self.position=(rdVector3){x,y,BOT_FOOT_HEIGHT}, PlainFace(&self,0), \
        bot.goal=1, bot.route[0]=0, bot.route[1]=1, bot.routeCount=2, bot.routePos=1, bot.nextPlan=1e9f, \
        memset(bot.axes,0,sizeof(bot.axes)), memset(bot.keys,0,sizeof(bot.keys)), bot.tele.legAxis=0, bot.frameDt=0.03f, \
        Bot_Navigate(&self))
    /* 0.08 off the axis and 0.12 short of the wall, the straight way to
       node 1 clips the jamb: step back onto the axis, a little forward. */
    AXIS_STEP(0.88f,0.08f);
    rdVector3 thrust=PlainThrust(&self);
    assert(bot.tele.legAxis>0 && thrust.y<-0.3f && thrust.x>0 && bot.goal==1);
    /* On the axis: straight through. */
    AXIS_STEP(0.88f,0.005f);
    thrust=PlainThrust(&self);
    assert(bot.tele.legAxis==0 && thrust.x>0.5f && fabsf(thrust.y)<0.2f);
    /* Off the axis with a clear way: straight on, no detour. */
    plainSlotLo=-0.5f; plainSlotHi=0.5f;
    AXIS_STEP(0.88f,0.08f);
    assert(bot.tele.legAxis==0);
    plainSlotLo=-0.1f; plainSlotHi=0.1f;
    /* Legacy: no step back onto the axis. */
    TacticsUse(1); AXIS_STEP(0.88f,0.08f); assert(bot.tele.legAxis==0); TacticsUse(0);
    #undef AXIS_STEP
    plainSlotX=1e9f; memset(&nav,0,sizeof(nav)); bot.nNodes=0; bot.goal=-1; bot.routeCount=bot.routePos=0;
    bot.world=sithWorld_g_pCurrentWorld=NULL; sithPlayer_g_pLocalPlayerThing=NULL; testPlainActive=0;
    puts("PASS leg axis: off a walking leg's line where the straight way to its node clips the jamb of a narrow opening, the bot steps back onto the line first; on the line, or with the way clear, it goes straight; legacy does not");
}

/* lift_hop: a ledge (node 0, on the ground at the origin) beside a lift
   shaft centred 0.3 along +y, whose deck stops 1.5 below the ledge (node 1)
   and 1.2 above it (node 2), as Bespin's railgun alcove sits. */
static void test_fix_lift_hop(void)
{
    static SithWorld world; static SithThing things[1]; static SithPathFrame frames[2];
    SithThing self; SithPlayer own;
    testPlainActive=1; plainEdge=plainShelf=plainWall=plainField=1e9f; plainFieldOn=0; plainShelfZ=0; plainSlotX=1e9f;
    plainGround.flags=0; plainLand.flags=0;
    PlainSelf(&self,&own);
    jkBot_Configure("LiftHop_Test","ky.3do"); TacticsUse(0); bot.now=10; bot.nextUse=0; bot.frameDt=0.03f;
    self.actorParams.eyeOffset=(rdVector3){0,0,0.037f};
    memset(&world,0,sizeof(world)); memset(&traps,0,sizeof(traps)); memset(&nav,0,sizeof(nav));
    bot.world=sithWorld_g_pCurrentWorld=&world; sithPlayer_g_pLocalPlayerThing=&self;
    world.aSectors=&plainLand; world.numSectors=1; world.gravity=4;
    memset(things,0,sizeof(things)); frames[0].pos=(rdVector3){0,0.3f,-1.5f}; frames[1].pos=(rdVector3){0,0.3f,1.2f};
    things[0].type=SITH_THING_COG; things[0].moveType=SITH_MT_PATH; things[0].sector=&plainLand;
    things[0].trackParams.aFrames=frames; things[0].trackParams.loadedFrames=2; things[0].position=frames[0].pos;
    world.aThings=things; world.numThings=0; world.numThingsLoaded=1;
    bot.nNodes=3; bot.graphDone=1;
    RouteNode(0,0,0); RouteNode(1,0,0.3f); RouteNode(2,0,0.3f);
    bot.nodes[1].pos.z=-1.5f+BOT_FOOT_HEIGHT; bot.nodes[2].pos.z=1.2f+BOT_FOOT_HEIGHT;
    nav.liftCount=1; nav.lifts[0].thing=0; nav.lifts[0].node[0]=1; nav.lifts[0].node[1]=2; nav.lifts[0].top=0;
    nav.liftForNode[1]=nav.liftForNode[2]=1;
    /* The graph: a leg off the ledge to either stop, none back. */
    assert(Bot_EdgeMode(0,1)==BOT_ROUTE_LIFT && Bot_EdgeMode(0,2)==BOT_ROUTE_LIFT && Bot_EdgeMode(1,0)<0);
    TacticsUse(1); assert(Bot_EdgeMode(0,1)<0 && "legacy: no way off"); TacticsUse(0);
    #define HOP_AT(z,rate,stillFor) (things[0].position=(rdVector3){0,0.3f,z}, nav.liftTrack=1, \
        nav.liftSeen=(stillFor)>0 ? things[0].position : (rdVector3){0,0.3f,(z)-0.01f}, nav.liftMovedAt=bot.now-(stillFor), \
        nav.liftLastZ=(z)-(rate)*0.03f, nav.liftLastAt=bot.now-0.03f, nav.liftWaitAt=0, nav.hopUntil=0, \
        bot.goal=1, bot.routeCount=2, memset(bot.axes,0,sizeof(bot.axes)), memset(bot.keys,0,sizeof(bot.keys)), \
        memset(bot.previous,0,sizeof(bot.previous)))
    self.position=(rdVector3){0,0,BOT_FOOT_HEIGHT}; PlainFace(&self,90/BOT_DEG); bot.tele.liftHops=0;
    /* Standing 1.5 below: drop onto it. */
    HOP_AT(-1.5f,0,1.0f);
    assert(Bot_LiftMove(&self,0,1) && nav.hopUntil>bot.now && bot.tele.liftHops==1 && PlainThrust(&self).y>0.3f);
    /* Hurt, a drop over a unit is not taken: wait at the lip instead. */
    self.actorParams.health=40; HOP_AT(-1.5f,0,1.0f);
    assert(Bot_LiftMove(&self,0,1) && !nav.hopUntil && bot.tele.liftHops==1);
    self.actorParams.health=100;
    /* Standing above the ledge: walk up to the lip and wait there. */
    HOP_AT(1.2f,0,1.0f);
    assert(Bot_LiftMove(&self,0,1) && !nav.hopUntil && PlainThrust(&self).y>0.05f && nav.waitUntil>bot.now);
    self.position.y=0.077f; HOP_AT(1.2f,0,1.0f);
    assert(Bot_LiftMove(&self,0,1) && !nav.hopUntil && fabsf(PlainThrust(&self).y)<0.05f && nav.waitUntil>bot.now);
    self.position.y=0;
    /* Rising at a unit a second, 0.45 under the ledge: it will be 0.3 under
       by the time the bot is over it. Go. 0.8 under: not yet. */
    HOP_AT(-0.45f,1.0f,0);
    assert(Bot_LiftMove(&self,0,1) && nav.hopUntil>bot.now && bot.tele.liftHops==2);
    HOP_AT(-0.8f,1.0f,0);
    assert(Bot_LiftMove(&self,0,1) && !nav.hopUntil && bot.tele.liftHops==2);
    /* Coming down, just above the ledge: go, it will be under it. */
    HOP_AT(0.05f,-1.0f,0);
    assert(Bot_LiftMove(&self,0,2) && nav.hopUntil>bot.now && bot.tele.liftHops==3);
    /* Committed while it rises past the ledge: stop short of the shaft. */
    HOP_AT(0.05f,1.0f,0); nav.hopUntil=bot.now+0.5f;
    assert(Bot_LiftMove(&self,0,1) && !nav.hopUntil && fabsf(PlainThrust(&self).y)<0.05f);
    /* Legacy: no hop; a lift away from the stop is waited for. */
    TacticsUse(1); HOP_AT(-1.5f,0,1.0f);
    assert(Bot_LiftMove(&self,0,2) && !nav.hopUntil && bot.tele.liftHops==3); TacticsUse(0);
    #undef HOP_AT
    memset(&nav,0,sizeof(nav)); bot.nNodes=0; bot.goal=-1; bot.routeCount=0; bot.tele.liftHops=0;
    bot.world=sithWorld_g_pCurrentWorld=NULL; sithPlayer_g_pLocalPlayerThing=NULL; testPlainActive=0;
    puts("PASS lift hop: a ledge partway up a lift shaft gets legs onto both stops; the deck is dropped onto where it stands below within reach of the bot's health, or stepped onto as it passes just under the ledge, and the step is called off if it rises past; legacy has no way off");
}

/* leg_square: Bespin's lift 2 at the top in miniature. The deck's way off
   is an opening 0.2 wide in a wall at x=-0.4, to a landing (node 2); the
   rider stands against that wall 0.01 past the opening's edge and 0.11 off
   its line, as Boba Fett stood for 25 seconds. */
static void test_fix_leg_square(void)
{
    static SithWorld world; static SithThing things[1]; static SithPathFrame frames[2];
    SithThing self; SithPlayer own;
    testPlainActive=1; plainEdge=plainShelf=plainWall=plainField=1e9f; plainFieldOn=0; plainShelfZ=0;
    plainGround.flags=0; plainLand.flags=0;
    plainSlotX=-0.4f; plainSlotLo=-0.1f; plainSlotHi=0.1f;
    PlainSelf(&self,&own);
    jkBot_Configure("LegSquare_Test","ky.3do"); TacticsUse(0); bot.now=10; bot.nextUse=0; bot.forceBin=-1; bot.frameDt=0.03f;
    self.actorParams.eyeOffset=(rdVector3){0,0,0.037f};
    memset(&world,0,sizeof(world)); memset(&traps,0,sizeof(traps)); memset(&nav,0,sizeof(nav));
    bot.world=sithWorld_g_pCurrentWorld=&world; sithPlayer_g_pLocalPlayerThing=&self;
    world.aSectors=&plainLand; world.numSectors=1; world.gravity=4;
    memset(things,0,sizeof(things)); frames[0].pos=(rdVector3){0,0,0}; frames[1].pos=(rdVector3){0,0,2};
    things[0].type=SITH_THING_COG; things[0].moveType=SITH_MT_PATH; things[0].sector=&plainLand;
    things[0].trackParams.aFrames=frames; things[0].trackParams.loadedFrames=2; things[0].position=frames[0].pos;
    world.aThings=things; world.numThings=0; world.numThingsLoaded=1;
    bot.nNodes=3; bot.graphDone=1;
    RouteNode(0,0,0); RouteNode(1,0,0); bot.nodes[1].pos.z+=2; RouteNode(2,-0.7f,0);
    nav.liftCount=1; nav.lifts[0].thing=0; nav.lifts[0].node[0]=0; nav.lifts[0].node[1]=1;
    nav.liftForNode[0]=nav.liftForNode[1]=1;
    self.attach_flags=SITH_ATTACH_THINGFACE; self.attachedThing=&things[0];
    #define SQUARE_RIDE(stepping,y) (self.position=(rdVector3){-0.335f,y,BOT_FOOT_HEIGHT}, PlainFace(&self,180/BOT_DEG), \
        nav.liftTrack=1, nav.liftSeen=things[0].position, nav.liftMovedAt=bot.now-1.0f, nav.liftWaitAt=0, \
        nav.liftStep=(stepping) ? 3 : 0, nav.liftStepAt=(rdVector3){-0.4f,0,0.15f}, nav.liftStepNormal=(rdVector3){-1,0,0}, \
        nav.liftStepUntil=bot.now+3, bot.goal=2, bot.routeCount=2, bot.tele.legAxis=bot.tele.legSquare=0, \
        memset(bot.axes,0,sizeof(bot.axes)), memset(bot.keys,0,sizeof(bot.keys)), memset(bot.previous,0,sizeof(bot.previous)))
    /* Walking off at the stop: the straight way and the slant onto the
       line both meet the jamb's corner. Square along the wall instead. */
    SQUARE_RIDE(0,0.11f);
    assert(Bot_LiftMove(&self,0,2));
    rdVector3 thrust=PlainThrust(&self);
    assert(bot.tele.legSquare>0 && bot.tele.legAxis>0 && thrust.y<-0.2f && fabsf(thrust.x)<0.05f);
    /* Stepping off a lift that will not move: the same. */
    SQUARE_RIDE(1,0.11f);
    assert(Bot_LiftMove(&self,0,1) && nav.liftStep==3);
    thrust=PlainThrust(&self);
    assert(bot.tele.legSquare>0 && thrust.y<-0.2f && fabsf(thrust.x)<0.05f);
    /* 0.04 off the line, still against the wall: the slimmer steering probe
       would pass the straight way, but the body meets the corner. Keep
       squaring. 0.03 off, the body is clear of the jamb: straight off. */
    SQUARE_RIDE(1,0.04f);
    assert(Bot_LiftMove(&self,0,1) && bot.tele.legSquare>0 && PlainThrust(&self).y<-0.2f);
    SQUARE_RIDE(1,0.03f);
    assert(Bot_LiftMove(&self,0,1) && bot.tele.legSquare==0 && PlainThrust(&self).x<-0.5f);
    SQUARE_RIDE(0,0.005f);
    assert(Bot_LiftMove(&self,0,2) && bot.tele.legSquare==0 && PlainThrust(&self).x<-0.5f && "on the line: straight off");
    /* Only 0.02 off the line of an opening that leaves a body 0.008 either
       side: the square step is still long enough to register as a move. */
    plainSlotLo=-0.06f; plainSlotHi=0.06f;
    SQUARE_RIDE(1,0.02f);
    assert(Bot_LiftMove(&self,0,1) && bot.tele.legSquare>0 && PlainThrust(&self).y<-0.2f);
    plainSlotLo=-0.1f; plainSlotHi=0.1f;
    /* leg_square off: no square step. From the corner, walking off at the
       stop, the rider does not move at all, as on Bespin; from 0.04 off it
       walks straight into the corner. */
    BT(LEG_SQUARE)=0; SQUARE_RIDE(1,0.11f);
    assert(Bot_LiftMove(&self,0,1) && bot.tele.legSquare==0);
    SQUARE_RIDE(0,0.11f); thrust=Bot_LiftMove(&self,0,2) ? PlainThrust(&self) : (rdVector3){1,1,0};
    assert(bot.tele.legSquare==0 && fabsf(thrust.x)<0.01f && fabsf(thrust.y)<0.01f);
    SQUARE_RIDE(1,0.04f);
    assert(Bot_LiftMove(&self,0,1) && bot.tele.legSquare==0 && PlainThrust(&self).x<-0.5f);
    TacticsUse(0);
    #undef SQUARE_RIDE
    /* Walking a leg into a door alcove 0.2 wide in a wall at x=1, pressed
       against the wall beside its mouth: the same, and once squaring it
       keeps on until the body is clear of the jamb. */
    memset(&nav,0,sizeof(nav)); plainSlotX=1.0f;
    bot.nNodes=2; RouteNode(0,0.7f,0); RouteNode(1,1.2f,0);
    RouteEdge(0,1,BOT_ROUTE_WALK); RouteEdge(1,0,BOT_ROUTE_WALK);
    self.attach_flags=SITH_ATTACH_SURFACE; self.attachedThing=NULL; self.attachedSurface=&plainGround;
    #define SQUARE_WALK(x,y) (self.position=(rdVector3){x,y,BOT_FOOT_HEIGHT}, PlainFace(&self,0), \
        bot.goal=1, bot.route[0]=0, bot.route[1]=1, bot.routeCount=2, bot.routePos=1, bot.nextPlan=1e9f, \
        memset(bot.axes,0,sizeof(bot.axes)), memset(bot.keys,0,sizeof(bot.keys)), bot.tele.legAxis=bot.tele.legSquare=0, \
        Bot_Navigate(&self))
    SQUARE_WALK(0.935f,0.11f);
    thrust=PlainThrust(&self);
    assert(bot.tele.legSquare>0 && bot.tele.legAxis>0 && thrust.y<-0.3f && fabsf(thrust.x)<0.05f && bot.goal==1);
    assert(nav.squareNode==2 && nav.squareUntil>bot.now);
    bot.now+=0.1f; SQUARE_WALK(0.935f,0.04f);
    assert(bot.tele.legSquare>0 && PlainThrust(&self).y<-0.3f);
    bot.now+=0.1f; SQUARE_WALK(0.935f,0.03f);
    assert(bot.tele.legSquare==0 && PlainThrust(&self).x>0.3f);
    /* A little way out from the wall the slant clears the corner, as before. */
    memset(&nav,0,sizeof(nav)); SQUARE_WALK(0.88f,0.08f);
    assert(bot.tele.legAxis>0 && bot.tele.legSquare==0 && PlainThrust(&self).x>0);
    /* leg_square off: no square step. */
    BT(LEG_SQUARE)=0; SQUARE_WALK(0.935f,0.11f); assert(bot.tele.legSquare==0 && !nav.squareNode); TacticsUse(0);
    #undef SQUARE_WALK
    plainSlotX=1e9f; memset(&nav,0,sizeof(nav)); bot.nNodes=0; bot.goal=-1; bot.routeCount=bot.routePos=0;
    bot.tele.legAxis=bot.tele.legSquare=0;
    bot.world=sithWorld_g_pCurrentWorld=NULL; sithPlayer_g_pLocalPlayerThing=NULL; testPlainActive=0;
    puts("PASS leg square: pressed against the wall beside a narrow opening, where the body meets the jamb's corner on the straight way and on the slant onto the leg's line, the bot steps square onto the line along the wall until the body is clear of the jamb, whether walking off a lift, stepping off one or walking a leg; a little way out the slant still serves; with leg_square off it does not");
}

static void test_bot_tactic_fixes(void)
{
    jkPlayer_maxPlayers=0; memset(jkPlayer_playerInfos,0,sizeof(jkPlayer_playerInfos));
    test_fix_respawn();
    test_fix_swim_thrust();
    test_fix_water_exit();
    test_fix_force_jump();
    test_fix_jump_memory();
    test_fix_speed();
    test_fix_resupply();
    test_fix_always_run();
    test_fix_pull_on_move();
    test_fix_pack_hunt();
    test_fix_lip_escape();
    test_fix_traps();
    test_fix_trap_disarm();
    test_fix_field();
    test_fix_jump_margin();
    test_fix_fjump_margin();
    test_fix_lift_call();
    test_fix_dead_end();
    test_fix_leg_axis();
    test_fix_lift_hop();
    test_fix_leg_square();
}
