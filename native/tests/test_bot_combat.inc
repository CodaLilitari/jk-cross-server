/* Controlled flat floor, optional cross-wall, and ordinary template inheritance. */
static int testCombatArena, testCombatWall;
static SithThing testConcProjectile, testRailProjectile, testConcBlast, testRailBlast, testConcBeam;

static int TestCombatCollision(SithSector *sector,const rdVector3 *from,const rdVector3 *dir,
                              flex_t length,flex_t radius,SithCollision *hit)
{
    flex_t at=length+1;
    if (dir->z<0) at=(from->z-radius)/-dir->z;
    if (testCombatWall && dir->y>0 && from->y<0.5f) {
        flex_t wallAt=(0.5f-from->y-radius)/dir->y;
        if (testCombatWall==1 || from->z+wallAt*dir->z-radius<0.105f)
            at=Bot_Min(at,wallAt);
    }
    if (at<0 || at>length) return 0;
    *hit=(SithCollision){0}; hit->type=SITHCOLLISION_WORLD; hit->distance=at;
    corridorFloor.pSector=sector;
    corridorFloor.flags=SITH_SURFACE_HAS_COLLISION|SITH_SURFACE_FLOOR;
    hit->surface=&corridorFloor; hit->hitNorm.z=1;
    return 1;
}

/* Inspect the ordinary SELECT key for every slot. The caller's inventory
   stays untouched until the stock engine consumes the request. */
static void test_selection_pulse(SithThing *self,SithThing *target,int expected)
{
    int current=self->actorParams.pPlayer->curWeaponID;
    bot.now+=1; bot.nextSelect=0; bot.targetSlot=target ? 1 : -1;
    memset(bot.keys,0,sizeof(bot.keys));
    assert(Bot_SelectWeapon(self,target ? Bot_Distance(self->position,target->position) : 2)==current);
    for (int w=SITHBIN_FISTS;w<=SITHBIN_LIGHTSABER;w++)
        assert(bot.keys[INPUT_FUNC_SELECT1+w-1]==(w==expected && expected!=current));
    assert(!bot.keys[INPUT_FUNC_FIRE1] && !bot.keys[INPUT_FUNC_FIRE2]);
}

static void test_ranged_choices(SithThing *self,SithThing *enemy,SithThing *ally)
{
    SithPlayer *p=self->actorParams.pPlayer; jkPlayerInfo remote={0}; rdModel3 gun={0};
    SithSector *dry=enemy->sector,wet={.flags=SITH_SECTOR_UNDERWATER};
    memset(p->aItems,0,sizeof(p->aItems));
    int weapons[]={SITHBIN_FISTS,SITHBIN_LIGHTSABER,SITHBIN_BRYARPISTOL};
    for (unsigned i=0;i<sizeof(weapons)/sizeof(weapons[0]);i++) {
        p->aItems[weapons[i]].state=SITHINVENTORY_ITEM_AVAILABLE; p->aItems[weapons[i]].amount=1;
    }
    p->aItems[SITHBIN_ENERGY].amount=12; p->curWeaponID=SITHBIN_LIGHTSABER;
    self->orient.lvec.y=1; enemy->orient.lvec.y=-1;
    enemy->playerInfo=&remote; remote.rd_thing.model3=&gun; strcpy(gun.filename,"rptg.3do");
    enemy->position=(rdVector3){0,0.8f,BOT_FOOT_HEIGHT};
    enemy->physicsParams.vel=(rdVector3){0}; ally->position.x=10;
    test_selection_pulse(self,enemy,SITHBIN_BRYARPISTOL);
    enemy->position.y=0.40f; test_selection_pulse(self,enemy,SITHBIN_BRYARPISTOL);
    p->curWeaponID=SITHBIN_BRYARPISTOL;
    enemy->position.y=0.20f; test_selection_pulse(self,enemy,SITHBIN_LIGHTSABER);
    enemy->physicsParams.vel.y=1; test_selection_pulse(self,enemy,SITHBIN_BRYARPISTOL);
    self->physicsParams.vel.y=1; test_selection_pulse(self,enemy,SITHBIN_LIGHTSABER);
    self->physicsParams.vel.y=enemy->physicsParams.vel.y=0;
    enemy->physicsParams.vel.z=2; test_selection_pulse(self,enemy,SITHBIN_BRYARPISTOL); enemy->physicsParams.vel.z=0;
    enemy->sector=&wet; test_selection_pulse(self,enemy,SITHBIN_BRYARPISTOL); enemy->sector=dry;
    enemy->position.y=0.10f; enemy->position.z+=0.16f;
    test_selection_pulse(self,enemy,SITHBIN_BRYARPISTOL); enemy->position.z=BOT_FOOT_HEIGHT;
    /* A nearby blaster facing the bot gives the blade a defensive use. */
    enemy->position.y=0.32f; strcpy(gun.filename,"bryg.3do"); test_selection_pulse(self,enemy,SITHBIN_LIGHTSABER);
    enemy->orient.lvec.y=1; test_selection_pulse(self,enemy,SITHBIN_BRYARPISTOL);
    enemy->orient.lvec.y=-1; strcpy(gun.filename,"cong.3do"); test_selection_pulse(self,enemy,SITHBIN_BRYARPISTOL);
    enemy->position.y=.19f; test_selection_pulse(self,enemy,SITHBIN_BRYARPISTOL);
    strcpy(gun.filename,"rldg.3do"); test_selection_pulse(self,enemy,SITHBIN_BRYARPISTOL);
    /* Ammo without a weapon (for example after Pull) cannot select its slot. */
    p->aItems[SITHBIN_BRYARPISTOL].amount=0; enemy->position.y=2;
    test_selection_pulse(self,enemy,SITHBIN_LIGHTSABER); p->aItems[SITHBIN_BRYARPISTOL].amount=1;

    testRailProjectile.weaponParams.pExplosionTemplate=&testRailBlast; testRailBlast.explosionParams.range=.5f;
    p->aItems[SITHBIN_RAIL_DETONATOR].state=p->aItems[SITHBIN_CONCUSSION_RIFLE].state=SITHINVENTORY_ITEM_AVAILABLE;
    p->aItems[SITHBIN_RAIL_DETONATOR].amount=p->aItems[SITHBIN_CONCUSSION_RIFLE].amount=1;
    p->aItems[SITHBIN_RAILCHARGES].amount=1; p->aItems[SITHBIN_POWER].amount=7;
    test_selection_pulse(self,NULL,SITHBIN_RAIL_DETONATOR);
    p->aItems[SITHBIN_POWER].amount=8; test_selection_pulse(self,NULL,SITHBIN_CONCUSSION_RIFLE);
    p->curWeaponID=SITHBIN_RAIL_DETONATOR; test_selection_pulse(self,NULL,SITHBIN_RAIL_DETONATOR);
    p->curWeaponID=SITHBIN_BRYARPISTOL; test_selection_pulse(self,enemy,SITHBIN_CONCUSSION_RIFLE);
    ally->position=enemy->position; ally->position.x=.70f; test_selection_pulse(self,enemy,SITHBIN_RAIL_DETONATOR);
    ally->position.x=.30f; test_selection_pulse(self,enemy,SITHBIN_BRYARPISTOL);
    ally->position.x=10; enemy->position.y=.45f; test_selection_pulse(self,enemy,SITHBIN_BRYARPISTOL);
    p->aItems[SITHBIN_POWER].amount=0; p->aItems[SITHBIN_RAILCHARGES].amount=0;
    test_selection_pulse(self,NULL,SITHBIN_BRYARPISTOL);
    /* At long range or between contacts, each loaded upgrade should replace
       the Bryar. A mounted rail can still yield to the faster concussion. */
    p->aItems[SITHBIN_CONCUSSION_RIFLE].amount=p->aItems[SITHBIN_RAIL_DETONATOR].amount=0;
    p->aItems[SITHBIN_POWER].amount=8; p->aItems[SITHBIN_RAILCHARGES].amount=1; enemy->position.y=11;
    int upgrades[]={SITHBIN_STORMTROOPER_RIFLE,SITHBIN_TUSKEN_PROD,SITHBIN_REPEATER,
                    SITHBIN_RAIL_DETONATOR,SITHBIN_CONCUSSION_RIFLE};
    for (unsigned i=0;i<sizeof(upgrades)/sizeof(upgrades[0]);i++) {
        int w=upgrades[i];
        p->aItems[w].state=SITHINVENTORY_ITEM_AVAILABLE; p->aItems[w].amount=1;
        test_selection_pulse(self,enemy,w); test_selection_pulse(self,NULL,w);
        p->aItems[w].amount=0;
    }
    p->aItems[SITHBIN_CONCUSSION_RIFLE].amount=p->aItems[SITHBIN_RAIL_DETONATOR].amount=1;
    p->curWeaponID=SITHBIN_RAIL_DETONATOR; test_selection_pulse(self,enemy,SITHBIN_CONCUSSION_RIFLE);
    bot.sabersOnly=1; test_selection_pulse(self,enemy,SITHBIN_LIGHTSABER); bot.sabersOnly=0;
    enemy->playerInfo=NULL;
    puts("PASS elite gun selection retains blade contact/bolt defense, respects separating targets, elevation, water, blast clearance, reserves and quiet heavy readiness");
}

#include "test_bot_altfire.inc"

static void test_bot_gunshots(void)
{
    SithThing self={0}, enemy={0}, ally={0};
    SithSector sector={0};
    jkBot_Configure("Bot_Aim","ky.3do");
    bot.elite=1; bot.fistsPeace=0; bot.now=1; bot.targetSlot=1;
    testCombatArena=1; fixtureMode=corridorMode=testSlopeActive=testBridgeActive=testC1Active=0;
    memset(jkPlayer_playerInfos,0,sizeof(jkPlayer_playerInfos));
    jkPlayer_maxPlayers=3; sithNet_MultiModeFlags=MULTIMODEFLAG_TEAMS;
    SithThing *players[]={&self,&enemy,&ally};
    for (int i=0;i<3;i++) {
        SithPlayer *p=&jkPlayer_playerInfos[i];
        p->pLocalPlayer=players[i]; p->flags=1; p->teamNum=i==1 ? 2 : 1; p->playerNetId=i+1;
        players[i]->type=SITH_THING_PLAYER; players[i]->sector=&sector;
        players[i]->actorParams.pPlayer=p; players[i]->position.z=BOT_FOOT_HEIGHT;
        players[i]->collideSize=players[i]->moveSize=.065f;
    }
    ally.position.x=9; enemy.position.y=2; enemy.physicsParams.vel.x=1;
    testConcBlast.type=testRailBlast.type=SITH_THING_EXPLOSION;
    testConcBlast.explosionParams.range=.8f; testRailBlast.explosionParams.range=.5f;
    testConcProjectile.weaponParams.pExplosionTemplate=testConcProjectile.weaponParams.fleshHitTemplate=&testConcBlast;
    testRailProjectile.weaponParams.pExplosionTemplate=testRailProjectile.weaponParams.fleshHitTemplate=&testRailBlast;
    testConcProjectile.physicsParams.vel.y=7; testRailProjectile.physicsParams.vel.y=2.5f;
    testConcProjectile.moveSize=.005f; testRailProjectile.moveSize=.003f;
    BotGunShot shot=Bot_PlanGunShot(&self,&enemy,SITHBIN_CONCUSSION_RIFLE);
    assert(shot.aim.x>.24f && shot.aim.x<.34f && shot.aim.z>0 && shot.aim.z<.025f);
    assert(Bot_GunSafe(&self,&enemy,&shot,0));
    assert(!Bot_FloorAimAligned(&self,&shot)); /* Horizontal barrel would sail over this floor. */
    rdVector3 line=Bot_Sub(shot.aim,self.position);
    self.actorParams.headPYR.x=atan2f(line.z,Bot_Horizontal(line))*BOT_DEG;
    assert(Bot_FloorAimAligned(&self,&shot));
    self.actorParams.pPlayer->aItems[SITHBIN_CONCUSSION_RIFLE].amount=1;
    self.actorParams.pPlayer->aItems[SITHBIN_CONCUSSION_RIFLE].state=SITHINVENTORY_ITEM_AVAILABLE;
    self.actorParams.pPlayer->aItems[SITHBIN_POWER].amount=8;
    Bot_SelectWeapon(&self,2); assert(bot.keys[INPUT_FUNC_SELECT1+SITHBIN_CONCUSSION_RIFLE-1]);
    ally.position=shot.aim; ally.position.x+=.76f; assert(!Bot_GunSafe(&self,&enemy,&shot,0));
    ally.position=(rdVector3){1.55f,2,BOT_FOOT_HEIGHT};
    ally.physicsParams.vel.x=1;
    assert(Bot_GunSafe(&self,&enemy,&shot,0)); /* Moving away from impact. */
    ally.physicsParams.vel.x=-2;
    assert(!Bot_GunSafe(&self,&enemy,&shot,0)); /* Moving into the splash. */
    ally.physicsParams.vel.x=0; ally.position.x=9; testCombatWall=2;
    BotGunShot overLip=Bot_PlanGunShot(&self,&enemy,SITHBIN_CONCUSSION_RIFLE);
    assert(!overLip.floorAim && overLip.aim.z==enemy.position.z && Bot_GunSafe(&self,&enemy,&overLip,0));
    testCombatWall=1; assert(!Bot_GunSafe(&self,&enemy,&shot,0)); testCombatWall=0;
    enemy.position.z=1.1f;
    shot=Bot_PlanGunShot(&self,&enemy,SITHBIN_CONCUSSION_RIFLE);
    assert(shot.aim.z>.95f);
    enemy.position.z=BOT_FOOT_HEIGHT; enemy.physicsParams.vel.x=0; enemy.position.y=.76f;
    shot=Bot_PlanGunShot(&self,&enemy,SITHBIN_CONCUSSION_RIFLE); assert(!Bot_GunSafe(&self,&enemy,&shot,0));
    shot=Bot_PlanGunShot(&self,&enemy,SITHBIN_RAIL_DETONATOR); assert(Bot_GunSafe(&self,&enemy,&shot,0));
    testRailBlast.explosionParams.range=1.2f;
    shot=Bot_PlanGunShot(&self,&enemy,SITHBIN_RAIL_DETONATOR); assert(!Bot_GunSafe(&self,&enemy,&shot,0));
    testRailProjectile.weaponParams.pExplosionTemplate=NULL;
    shot=Bot_PlanGunShot(&self,&enemy,SITHBIN_RAIL_DETONATOR); assert(!Bot_GunSafe(&self,&enemy,&shot,0));
    test_ranged_choices(&self,&enemy,&ally);
    test_alternate_fire(&self,&enemy,&ally);
    testCombatArena=0; sithNet_MultiModeFlags=0; assert(queryDepth==0);
    puts("PASS predicted concussion floor/direct aim, legal selection, template splash, friendly/self and wall rejection");
}

static void test_bot_arming(void)
{
    SithThing self={0}, enemy={0}, rack={0}; SithSector sector={0}; SithWorld world={0};
    jkBot_Configure("Bot_Arm","ky.3do");
    memset(jkPlayer_playerInfos,0,sizeof(jkPlayer_playerInfos)); jkPlayer_maxPlayers=2;
    sithNet_MultiModeFlags=0; testCombatArena=1; testCombatWall=0;
    SithPlayer *p=&jkPlayer_playerInfos[0];
    self.type=enemy.type=SITH_THING_PLAYER; self.sector=enemy.sector=&sector;
    self.actorParams.pPlayer=p; self.actorParams.health=100; self.attach_flags=SITH_ATTACH_SURFACE;
    self.position.z=enemy.position.z=BOT_FOOT_HEIGHT; self.moveSize=self.collideSize=.065f;
    self.orient.lvec.y=1; self.orient.rvec.x=1; self.actorParams.maxRotVelocity=200;
    enemy.position.y=3; jkPlayer_playerInfos[1].flags=1;
    jkPlayer_playerInfos[1].pLocalPlayer=&enemy; jkPlayer_playerInfos[1].playerNetId=2;
    for (int w=2;w<=10;w++) { p->aItems[w].state=SITHINVENTORY_ITEM_AVAILABLE; p->aItems[w].amount=1; }
    p->aItems[SITHBIN_POWER].amount=8; p->aItems[SITHBIN_ENERGY].amount=10;
    bot.now=1; bot.targetSlot=-1; p->curWeaponID=SITHBIN_CONCUSSION_RIFLE;
    Bot_SelectWeapon(&self,2);
    for (int w=1;w<=10;w++) assert(!bot.keys[INPUT_FUNC_SELECT1+w-1]);
    bot.sabersOnly=1; bot.nextSelect=0; Bot_SelectWeapon(&self,2);
    assert(bot.keys[INPUT_FUNC_SELECT1+SITHBIN_LIGHTSABER-1]); bot.sabersOnly=0;
    p->aItems[SITHBIN_POWER].amount=0; bot.nextSelect=0; memset(bot.keys,0,sizeof(bot.keys));
    Bot_SelectWeapon(&self,2); assert(bot.keys[INPUT_FUNC_SELECT1+SITHBIN_STORMTROOPER_RIFLE-1]);
    memset(p->aItems,0,sizeof(p->aItems));
    p->aItems[SITHBIN_BRYARPISTOL].state=SITHINVENTORY_ITEM_AVAILABLE;
    p->aItems[SITHBIN_BRYARPISTOL].amount=1; p->aItems[SITHBIN_ENERGY].amount=10;
    p->curWeaponID=SITHBIN_BRYARPISTOL;
    bot.elite=1; bot.fistsPeace=0; bot.forceEnabled=0; bot.targetSlot=1; bot.now=5;
    world.aThings=&rack; world.numThings=0; world.numThingsLoaded=1; bot.world=&world;
    rack.type=SITH_THING_ITEM; rack.sector=&sector; strcpy(rack.aName,"railgun");
    rack.position=(rdVector3){0.8f,0,BOT_FOOT_HEIGHT}; bot.nNodes=1;
    bot.nodes[0]=(BotNode){.pos=rack.position,.sector=&sector,.item=0};
    memset(bot.keys,0,sizeof(bot.keys)); Bot_Combat(&self,&enemy);
    assert(bot.keys[INPUT_FUNC_FIRE1] && bot.axes[INPUT_FUNC_SLIDE]>.9f);
    assert(bot.armNode && !p->aItems[SITHBIN_RAIL_DETONATOR].amount);
    /* A near-side anchor can be inside pickup reach while the approaching
       player falls inside the generic navigation stop distance first. */
    rack.collide=SITH_COLLIDE_SPHERE; rack.collideSize=.10f;
    bot.nodes[0].pos.x=.031f; rack.position.x=.17f;
    bot.now+=1; memset(bot.keys,0,sizeof(bot.keys)); memset(bot.axes,0,sizeof(bot.axes)); Bot_Combat(&self,&enemy);
    assert(bot.keys[INPUT_FUNC_FIRE1] && bot.axes[INPUT_FUNC_SLIDE]>.1f && bot.axes[INPUT_FUNC_SLIDE]<=.4f);
    /* Acquire from rest inside the graph's .025 minimum edge as well. */
    Bot_ClearEquipment("fixture"); bot.now+=3; rack.position.x=.168f; bot.nodes[0].pos.x=.012f;
    memset(bot.axes,0,sizeof(bot.axes));
    assert(Bot_ArmingMove(&self,3) && bot.axes[INPUT_FUNC_SLIDE]>.1f && bot.axes[INPUT_FUNC_SLIDE]<=.4f);
    self.position.x=.007f; memset(bot.axes,0,sizeof(bot.axes));
    assert(!Bot_ArmingMove(&self,3) && !bot.axes[INPUT_FUNC_SLIDE]);
    /* A live obstruction still cancels an already-armed final nudge. */
    self.position=(rdVector3){0,.425f,BOT_FOOT_HEIGHT};
    bot.nodes[0].pos=(rdVector3){0,.456f,BOT_FOOT_HEIGHT};
    rack.position=(rdVector3){0,.595f,BOT_FOOT_HEIGHT};
    bot.now+=3; assert(Bot_ArmingMove(&self,3)); testCombatWall=1;
    memset(bot.axes,0,sizeof(bot.axes)); assert(!Bot_ArmingMove(&self,3) && !bot.axes[INPUT_FUNC_FORWARD]);
    testCombatWall=0; self.position=(rdVector3){0,0,BOT_FOOT_HEIGHT};
    bot.nodes[0].pos=rack.position=(rdVector3){.8f,0,BOT_FOOT_HEIGHT};
    nav.forceJumpPending=1; assert(!Bot_ArmingMove(&self,3)); nav.forceJumpPending=0;
    assert(!Bot_ArmingMove(&self,.3f));
    bot.now+=1; bot.hurtUntil=bot.now+1; assert(Bot_ArmingMove(&self,3)); bot.hurtUntil=0;
    bot.now+=4; bot.nodes[0].pos=(rdVector3){0,1,BOT_FOOT_HEIGHT}; testCombatWall=1;
    assert(!Bot_ArmingMove(&self,3)); testCombatWall=0;
    bot.nodes[0].pos=rack.position;
    bot.now+=4; strcpy(rack.aName,"railcharges"); assert(!Bot_ArmingMove(&self,3));
    p->aItems[SITHBIN_RAIL_DETONATOR].amount=1;
    p->aItems[SITHBIN_RAIL_DETONATOR].state=SITHINVENTORY_ITEM_AVAILABLE;
    bot.now+=4; assert(Bot_ArmingMove(&self,3));
    p->aItems[SITHBIN_RAILCHARGES].amount=1; assert(Bot_ArmingMove(&self,3));
    p->aItems[SITHBIN_RAILCHARGES].amount=30; assert(!Bot_ArmingMove(&self,3));
    testCombatArena=0; bot.world=NULL; assert(queryDepth==0);
    puts("PASS quiet weapon retention, saber-only/empty fallback, safe pickup movement + normal fire and interruption");
}
