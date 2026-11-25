/* Exercise ownership of movement through the normal per-frame dispatcher.
 * The fixed actor pose represents pushing into an obstruction. */
int sithNet_isMulti, g_submodeFlags, playerThingIdx;
SithWorld *sithWorld_g_pCurrentWorld;
SithPlayer *sithPlayer_g_pLocalPlayer;
#ifndef TEST_CUSTOM_CHAT_HANDLER
void sithMulti_SendChat(const char *message,int a,int b)
{ (void)message; (void)a; (void)b; assert(!"Unexpected chat in movement fixture"); }
#endif

static void test_bot_movement_tick(int underwater,int opponent,int sound,int makeProgress)
{
    static SithWorld world;
    static SithSector wet,dry;
    static SithThing self,enemy;
    static SithPlayer own;
    jkBot_Configure("Movement_Test","ky.3do");
    Bot_ResetHearing();
    memset(&nav,0,sizeof(nav));
    memset(&self,0,sizeof(self));
    memset(&enemy,0,sizeof(enemy));
    memset(&own,0,sizeof(own));
    memset(jkPlayer_playerInfos,0,sizeof(jkPlayer_playerInfos));
    wet.flags=SITH_SECTOR_UNDERWATER;
    self.type=enemy.type=SITH_THING_PLAYER;
    self.sector=underwater ? &wet : &dry;
    enemy.sector=&dry;
    self.actorParams.pPlayer=&own;
    self.actorParams.health=enemy.actorParams.health=100;
    self.actorParams.maxRotVelocity=200;
    self.orient.lvec.y=self.orient.rvec.x=1;
    own.curWeaponID=SITHBIN_BRYARPISTOL;
    own.aItems[SITHBIN_BRYARPISTOL].state=SITHINVENTORY_ITEM_AVAILABLE;
    own.aItems[SITHBIN_BRYARPISTOL].amount=1;
    own.aItems[SITHBIN_ENERGY].amount=100;
    sithPlayer_g_pLocalPlayerThing=&self;
    sithPlayer_g_pLocalPlayer=&own;
    bot.world=sithWorld_g_pCurrentWorld=&world;
    bot.enabled=bot.joined=bot.graphDone=sithNet_isMulti=1;
    bot.nextBehavior=bot.nextLog=100;
    bot.forceEnabled=0;
    jkPlayer_maxPlayers=2;
    jkPlayer_playerInfos[1].flags=1;
    jkPlayer_playerInfos[1].playerNetId=42;
    jkPlayer_playerInfos[1].pLocalPlayer=&enemy;
    testLOS=opponent;
    corridorMode=!underwater;
    corridorSector=&dry;
    corridorCeiling=-0.05f;
    if (!underwater) {
        self.position=(rdVector3){-2.2f,-1.85f,-0.25f+BOT_FOOT_HEIGHT};
        bot.nNodes=2;
        bot.nodes[0]=(BotNode){.pos=self.position,.sector=&dry,.item=-1};
        bot.nodes[1]=bot.nodes[0];
        bot.nodes[1].pos.x-=0.5f;
        bot.nodes[0].edges[0]=(BotEdge){1,0.5f,BOT_ROUTE_WALK};
        bot.nodes[0].nEdges=1;
    }
    bot.progressPos=self.position;
    enemy.position=self.position;
    enemy.position.y+=2;
    int ascent=0,visible=0,heard=0,route=0,fire=0;
    for (int tick=0;tick<340;tick++) {
        if (sound) {
            BotHeard *record=&ears.records[0];
            record->cue.kind=BOT_HEARD_PROJECTILE;
            record->cue.strength=1;
            record->slot=-1;
            record->last=bot.now;
        }
        /* A late loss of sight gives navigation a couple of frames before
           detection. Those frames cannot explain the preceding combat stall. */
        if (!underwater && opponent) testLOS=tick<39 || tick>40;
        if (makeProgress && tick==62) self.position.x-=0.15f;
        jkBot_Tick(0.05f);
        if (!underwater && tick==44) assert(bot.nodes[1].avoidUntil<=bot.now);
        if (!underwater && tick==74) {
            if (makeProgress) assert(bot.nodes[1].avoidUntil<=bot.now);
            else assert(bot.nodes[1].avoidUntil>bot.now);
        }
        if (bot.targetSlot==1) visible++;
        if (Bot_Attention()) heard++;
        if (bot.now>2 && bot.now<3.5f && bot.goal==1 && bot.axes[INPUT_FUNC_SLIDE]<-0.1f) route++;
        if (bot.now>15 && bot.keys[INPUT_FUNC_JUMP]) ascent++;
        if (bot.now>15 && bot.keys[INPUT_FUNC_FIRE1]) fire++;
    }
    assert(!opponent || (visible>300 && fire>20));
    assert(!sound || heard>300);
    if (underwater) assert(ascent>20);
    else assert(route>10);
    if (!underwater && opponent) {
        /* Enemy lies left and below, committed flight heads right and up. */
        enemy.position=self.position;
        enemy.position.x-=1; enemy.position.y+=1; enemy.position.z-=0.5f;
        nav.jumpTarget=self.position;
        nav.jumpTarget.x+=1; nav.jumpTarget.y+=1; nav.jumpTarget.z+=0.5f;
        nav.jumpUntil=bot.now+1.0f;
        jkBot_Tick(0.05f);
        assert(bot.targetSlot==1);
        assert(TestTurn()<-0.1f && TestPitch()>0.1f);
        assert(!bot.keys[INPUT_FUNC_FIRE1] && !bot.keys[INPUT_FUNC_FIRE2]);

        /* Heading is already needed before a takeoff has been committed.
           Keep the same off-axis target while approaching each type of edge. */
        nav.jumpUntil=0; self.attach_flags=SITH_ATTACH_SURFACE;
        bot.nodes[1].pos=nav.jumpTarget;
        bot.nodes[0].edges[0].drop=BOT_ROUTE_JUMP;
        bot.goal=1; bot.route[0]=0; bot.route[1]=1;
        bot.routeCount=2; bot.routePos=1; bot.nextPlan=bot.now+2;
        bot.nextRecovery=bot.now+1;
        jkBot_Tick(0.05f);
        assert(TestTurn()<-0.1f && fabsf(TestPitch())<0.01f);
        assert(!bot.keys[INPUT_FUNC_FIRE1]);
        bot.nodes[0].edges[0].drop=BOT_ROUTE_FORCEJUMP;
        bot.forceEnabled=1; own.aItems[SITHBIN_FORCEMANA].amount=100;
        jkBot_Tick(0.05f);
        assert(TestTurn()<-0.1f && !bot.keys[INPUT_FUNC_FIRE1]);

        /* Pending Force Jump must still receive its ordinary hold input. */
        nav.forceJumpPending=1; nav.forceChargeUntil=bot.now+0.5f;
        bot.forceBin=SITHBIN_F_JUMP; bot.forceUntil=nav.forceChargeUntil;
        jkBot_Tick(0.05f);
        assert(bot.keys[Bot_PowerKey(SITHBIN_F_JUMP)] && TestTurn()<-0.1f);
        assert(!bot.keys[INPUT_FUNC_FIRE1]);
        enemy.position=self.position; enemy.position.y+=1;
        jkBot_Tick(0.05f);
        assert(bot.keys[INPUT_FUNC_FIRE1] && bot.keys[Bot_PowerKey(SITHBIN_F_JUMP)]);
    }
    corridorMode=0;
}

/* In a narrow shaft the stock swimmer can travel for several seconds with
 * no horizontal displacement. Only progress toward the commanded depth counts. */
static void test_vertical_swim_progress(int direction,int targetDepth)
{
    static SithWorld world;
    static SithSector wet;
    static SithThing self;
    static SithPlayer own;
    memset(&self,0,sizeof(self)); memset(&nav,0,sizeof(nav));
    jkBot_Configure("Swim_Test","ky.3do");
    Bot_ResetHearing();
    self.type=SITH_THING_PLAYER; self.actorParams.health=100;
    self.actorParams.pPlayer=&own; self.sector=&wet;
    self.orient.lvec.y=self.orient.rvec.x=1;
    wet.flags=SITH_SECTOR_UNDERWATER;
    bot.world=sithWorld_g_pCurrentWorld=&world;
    sithPlayer_g_pLocalPlayer=&own; sithPlayer_g_pLocalPlayerThing=&self;
    bot.enabled=bot.joined=bot.graphDone=sithNet_isMulti=1;
    bot.nNodes=2; bot.goal=1; bot.nextPlan=bot.nextBehavior=bot.nextLog=100;
    bot.nodes[0]=(BotNode){.sector=&wet,.item=-1,.nEdges=1};
    bot.nodes[0].edges[0]=(BotEdge){1,1,BOT_ROUTE_SWIM};
    bot.nodes[1]=(BotNode){.sector=&wet,.item=-1,.pos={0,0,targetDepth}};
    bot.route[0]=0; bot.route[1]=1; bot.routePos=1; bot.routeCount=2;
    jkPlayer_maxPlayers=0; corridorMode=0; corridorSector=&wet;
    for (int tick=0;tick<52;tick++) {
        self.position.z+=direction*0.0055f;
        jkBot_Tick(0.05f);
    }
    if (direction==targetDepth)
        assert(bot.nodes[1].avoidUntil<=bot.now && bot.keys[targetDepth>0 ? INPUT_FUNC_JUMP : INPUT_FUNC_DUCK]);
    else assert(bot.nodes[1].avoidUntil>bot.now);
}

/* Actual frame arbitration on a controlled, dry floor. Stock inventory and
 * physics effects are observed separately in a live engine run. */
static void test_competitive_speed(void)
{
    SithWorld world={0}; SithSector sector={0}; SithThing self={0},enemy={0};
    SithPlayer own={0};
    jkBot_Configure("Speed_Test","ky.3do"); Bot_ResetHearing();
    bot.world=sithWorld_g_pCurrentWorld=&world;
    sithPlayer_g_pLocalPlayer=&own; sithPlayer_g_pLocalPlayerThing=&self;
    corridorMode=0; testCombatArena=1; testCombatWall=0; testLOS=1;
    bot.forceEnabled=bot.competitiveForce=bot.elite=bot.graphDone=bot.joined=sithNet_isMulti=1;
    bot.fistsPeace=0; bot.nextLog=bot.nextBehavior=100; bot.now=bot.stuckAt=1;
    self.type=enemy.type=SITH_THING_PLAYER; self.sector=enemy.sector=&sector;
    self.actorParams.health=enemy.actorParams.health=100;
    self.actorParams.pPlayer=&own; self.actorParams.maxRotVelocity=200;
    self.moveSize=self.collideSize=0.065f; self.position.z=BOT_FOOT_HEIGHT;
    self.orient.lvec.y=self.orient.rvec.x=1;
    self.attach_flags=SITH_ATTACH_SURFACE; self.attachedSurface=&corridorFloor;
    own.curWeaponID=SITHBIN_BRYARPISTOL;
    own.aItems[SITHBIN_BRYARPISTOL].state=SITHINVENTORY_ITEM_AVAILABLE;
    own.aItems[SITHBIN_BRYARPISTOL].amount=1; own.aItems[SITHBIN_ENERGY].amount=100;
    int speed=SITHBIN_F_SPEED, key=Bot_PowerKey(speed);
    own.aItems[speed].state=SITHINVENTORY_ITEM_AVAILABLE; own.aItems[speed].amount=4;
    own.aItems[SITHBIN_FORCEMANA].amount=60;
    memset(jkPlayer_playerInfos,0,sizeof(jkPlayer_playerInfos));
    jkPlayer_maxPlayers=2;
    jkPlayer_playerInfos[1].flags=1; jkPlayer_playerInfos[1].playerNetId=42;
    jkPlayer_playerInfos[1].pLocalPlayer=&enemy;
    enemy.position=self.position; enemy.position.y+=4;
    bot.targetSlot=1; bot.targetNetId=42;
    jkBot_Tick(0.04f);
    assert(bot.targetSlot==1 && !bot.followingRoute && bot.forceBin==speed);
    assert(jkBot_GetKey(key,NULL) && bot.presses[key] && bot.keys[INPUT_FUNC_FIRE1]);
    assert(own.aItems[SITHBIN_FORCEMANA].amount==60 && self.actorParams.extraSpeed==0);
    jkBot_Tick(0.04f); assert(bot.keys[key] && !bot.presses[key]);
    own.aItems[speed].state|=SITHINVENTORY_ITEM_ACTIVATED;
    for (int i=0;i<13;i++) jkBot_Tick(0.04f);
    assert(bot.forceBin<0 && !bot.keys[key] && bot.keys[INPUT_FUNC_FIRE1]);

    /* Same normal dispatcher, no opponent, item route shorter than the old
       two-unit threshold. Preserve the reserve, including the exact edge. */
    jkPlayer_maxPlayers=0; own.aItems[speed].state=SITHINVENTORY_ITEM_AVAILABLE;
    bot.targetSlot=-1; bot.nNodes=2; bot.goal=1; bot.routeCount=2; bot.routePos=1;
    bot.nodes[0]=(BotNode){.pos=self.position,.sector=&sector,.item=-1,.nEdges=1};
    bot.nodes[0].edges[0]=(BotEdge){1,1,BOT_ROUTE_WALK};
    bot.nodes[1]=(BotNode){.pos={0,1,BOT_FOOT_HEIGHT},.sector=&sector,.item=-1};
    bot.route[0]=0; bot.route[1]=1; bot.nextPlan=bot.now+5;
    own.aItems[SITHBIN_FORCEMANA].amount=59;
    jkBot_Tick(0.05f); assert(bot.routeMode==BOT_ROUTE_WALK && !bot.keys[key]);
    own.aItems[SITHBIN_FORCEMANA].amount=60; testCombatWall=1;
    jkBot_Tick(0.05f); assert(bot.axes[INPUT_FUNC_FORWARD]>0.9f && !bot.keys[key]);
    bot.now+=0.41f; testCombatWall=0; jkBot_Tick(0.05f);
    assert(bot.keys[key] && bot.presses[key]);
    puts("PASS competitive Speed uses ordinary held/released hotkey during gunfire and short walks, checks reserve and extended clearance");

    bot.forceBin=-1; bot.now+=1; bot.nextForce=bot.nextSpeedProbe=0;
    memset(bot.keys,0,sizeof(bot.keys)); nav.forceJumpPending=1;
    Bot_TryMovementSpeed(&self); assert(bot.forceBin<0); nav.forceJumpPending=0;
    nav.waterExitUntil=bot.now+2; Bot_TryMovementSpeed(&self); assert(bot.forceBin<0); nav.waterExitUntil=0;
    /* Both a thing attachment and an unattached swimmer can carry non-surface
       data in the stock attachment union. Inspect only genuine surfaces. */
    self.attach_flags=0; self.attachedSurface=(SithSurface *)(uintptr_t)1;
    sector.flags=SITH_SECTOR_UNDERWATER; Bot_TryMovementSpeed(&self); assert(bot.forceBin<0);
    self.attach_flags=SITH_ATTACH_SURFACE; self.attachedSurface=&corridorFloor; sector.flags=0;
    own.aItems[SITHBIN_F_GRIP].state=SITHINVENTORY_ITEM_ACTIVATED;
    Bot_TryMovementSpeed(&self); assert(bot.forceBin<0); own.aItems[SITHBIN_F_GRIP].state=0;
    own.aItems[SITHBIN_FORCEMANA].amount=19; own.aItems[SITHBIN_S_LIGHT].amount=1;
    Bot_TryMovementSpeed(&self); assert(bot.forceBin<0);
    own.aItems[SITHBIN_FORCEMANA].amount=20; Bot_TryMovementSpeed(&self); assert(bot.forceBin==speed);

    self.attach_flags=0; nav.jumpTarget=(rdVector3){1,1,BOT_FOOT_HEIGHT+0.5f};
    nav.jumpStarted=bot.now; nav.jumpUntil=bot.now+1; self.actorParams.maxThrust=2;
    self.actorParams.extraSpeed=2.5f; Bot_Navigate(&self);
    flex_t boostedForward=bot.axes[INPUT_FUNC_FORWARD], boostedSlide=bot.axes[INPUT_FUNC_SLIDE];
    self.actorParams.extraSpeed=0; Bot_Navigate(&self);
    assert(boostedForward>0 && boostedSlide>0);
    assert(fabsf(4.5f*boostedForward-2*bot.axes[INPUT_FUNC_FORWARD])<0.0001f);
    assert(fabsf(4.5f*boostedSlide-2*bot.axes[INPUT_FUNC_SLIDE])<0.0001f);
    assert(queryDepth==0); testCombatArena=0;
    puts("PASS Speed respects jump/water/Grip commitments and stock surge minimum, dry flight retains planned thrust across expiry");
}

static void test_bot_movement_ownership(void)
{
    test_competitive_speed();
    test_bot_movement_tick(1,1,0,0);
    test_bot_movement_tick(1,0,1,0);
    test_bot_movement_tick(1,0,0,0);
    test_bot_movement_tick(0,1,0,0);
    test_bot_movement_tick(0,0,1,0);
    test_bot_movement_tick(0,1,0,1);
    test_vertical_swim_progress(1,1);
    test_vertical_swim_progress(-1,-1);
    test_vertical_swim_progress(0,1);
    test_vertical_swim_progress(-1,1);
    puts("PASS air and wall recovery retain route movement during combat and hearing");
}
