/* First-hit controls fixture. Dynamic spheres include both players and a
   movable obstacle. Sector geometry comes from the combat arena fixture. */
static SithThing *testBeamObstacle;
static void TestBeamCollision(SithThing *probe,const rdVector3 *from,const rdVector3 *direction,
                              flex_t length,flex_t radius,SithCollision *hit,int *found)
{
    assert(probe->pParent && probe->parentSignature==probe->pParent->signature);
    flex_t nearest=*found ? hit->distance : length;
    for (int slot=-1;slot<(int)jkPlayer_maxPlayers;slot++) {
        SithThing *thing=slot<0 ? testBeamObstacle : jkPlayer_playerInfos[slot].pLocalPlayer;
        if (!thing || thing==probe->pParent) continue;
        rdVector3 delta=Bot_Sub(thing->position,*from);
        flex_t along=Bot_Dot(delta,*direction), width=radius+thing->collideSize;
        flex_t side2=Bot_Max(0,Bot_Dot(delta,delta)-along*along);
        if (along<0 || side2>width*width) continue;
        flex_t at=Bot_Max(0,along-sqrtf(width*width-side2));
        if (at>nearest) continue;
        *found=1; nearest=at;
        *hit=(SithCollision){.type=SITHCOLLISION_THING,.distance=at,.pThingCollided=thing};
    }
}

/* These stock-barrel fixtures use horizontal body axes and pitch-only head
   rotation. The production call is the same matrix rotation as FireProjectile. */
void rdMatrix_PreRotate34(rdMatrix34 *m,const rdVector3 *pyr)
{
    assert(pyr->y==0 && pyr->z==0);
    flex_t pitch=pyr->x/BOT_DEG, c=cosf(pitch), s=sinf(pitch);
    m->lvec=(rdVector3){c*m->lvec.x+s*m->uvec.x,c*m->lvec.y+s*m->uvec.y,c*m->lvec.z+s*m->uvec.z};
}

static BotGunShot test_fire_input(SithThing *self,SithThing *enemy,int weapon,flex_t error,int expected)
{
    self->actorParams.pPlayer->curWeaponID=weapon;
    memset(bot.keys,0,sizeof(bot.keys));
    BotGunShot shot=Bot_ChooseGunShot(self,enemy,weapon);
    rdVector3 line=Bot_Sub(shot.aim,self->position);
    self->actorParams.headPYR.x=atan2f(line.z,Bot_Horizontal(line))*BOT_DEG;
    Bot_FireGunShot(self,enemy,weapon,&shot,error,Bot_Distance(self->position,enemy->position));
    if (bot.keys[INPUT_FUNC_FIRE1]!=(expected==1) || bot.keys[INPUT_FUNC_FIRE2]!=(expected==2))
        fprintf(stderr,"fire fixture weapon=%d d=%.2f cells=%.1f expected=%d primary=%d secondary=%d\n",
            weapon,(double)Bot_Len(line),(double)sithInventory_GetInventory(self,SITHBIN_POWER),
            expected,bot.keys[INPUT_FUNC_FIRE1],bot.keys[INPUT_FUNC_FIRE2]);
    assert(bot.keys[INPUT_FUNC_FIRE1]==(expected==1) && bot.keys[INPUT_FUNC_FIRE2]==(expected==2));
    assert(queryDepth==0);
    return shot;
}

static void test_alternate_fire(SithThing *self,SithThing *enemy,SithThing *ally)
{
    SithPlayer *p=self->actorParams.pPlayer;
    for (int i=SITHBIN_FISTS;i<=SITHBIN_LIGHTSABER;i++) {
        p->aItems[i].amount=1; p->aItems[i].state=SITHINVENTORY_ITEM_AVAILABLE;
    }
    p->aItems[SITHBIN_POWER].amount=40; p->aItems[SITHBIN_ENERGY].amount=20;
    p->aItems[SITHBIN_RAILCHARGES].amount=2;
    self->orient.rvec=(rdVector3){1,0,0}; self->orient.lvec=(rdVector3){0,1,0}; self->orient.uvec.z=1;
    self->attach_flags=SITH_ATTACH_SURFACE; bot.reactionUntil=0; bot.targetSlot=1;
    memset(bot.previous,0,sizeof(bot.previous)); nav.combatJumpUntil=0;
    ally->position.x=10; enemy->position=(rdVector3){0,2,BOT_FOOT_HEIGHT};
    enemy->physicsParams.vel=(rdVector3){0};
    testConcBeam=(SithThing){.type=SITH_THING_WEAPON,.moveSize=.005f};
    testConcBeam.weaponParams.flags=SITH_WF_INSTANT_IMPACT;
    testConcBeam.weaponParams.range=5; testConcBeam.weaponParams.damage=80;
    int conc=SITHBIN_CONCUSSION_RIFLE, rpt=SITHBIN_REPEATER, bow=SITHBIN_TUSKEN_PROD;
    BotGunShot ground=test_fire_input(self,enemy,conc,0,1); assert(ground.floorAim);
    enemy->physicsParams.vel.x=1;
    BotGunShot crossing=test_fire_input(self,enemy,conc,0,2);
    assert(crossing.beam && crossing.aim.x==enemy->position.x && !crossing.flight);
    enemy->physicsParams.vel.x=0; p->aItems[SITHBIN_POWER].amount=8;
    test_fire_input(self,enemy,conc,0,2); p->aItems[SITHBIN_POWER].amount=7;
    test_fire_input(self,enemy,conc,0,0); p->aItems[SITHBIN_POWER].amount=12;
    enemy->position.y=5.1f; assert(!test_fire_input(self,enemy,conc,0,1).beam);
    enemy->position.y=.40f; test_fire_input(self,enemy,conc,0,2);
    test_fire_input(self,enemy,conc,1,0); /* Close primary splash is unsafe. */
    /* A mobile obstruction or a protected first contact vetoes the beam.
       A teammate well behind the target is beyond its first impact. */
    SithThing lift={.type=SITH_THING_COG,.collideSize=.07f,.position={0,.20f,BOT_FOOT_HEIGHT}};
    testBeamObstacle=&lift; test_fire_input(self,enemy,conc,0,0); testBeamObstacle=NULL;
    ally->position=(rdVector3){0,.22f,BOT_FOOT_HEIGHT}; test_fire_input(self,enemy,conc,0,0);
    ally->position.y=1.2f; test_fire_input(self,enemy,conc,0,2); ally->position.x=10;
    self->orient.lvec=(rdVector3){1,0,0}; test_fire_input(self,enemy,conc,0,0);
    self->orient.lvec=(rdVector3){0,1,0};
    testConcBeam.weaponParams.pExplosionTemplate=&testConcBlast; test_fire_input(self,enemy,conc,0,0);
    testConcBeam.weaponParams.pExplosionTemplate=NULL;
    enemy->position.y=.72f; testCombatWall=1; test_fire_input(self,enemy,conc,0,0); testCombatWall=0;
    enemy->position.y=.40f; bot.previous[INPUT_FUNC_FIRE1]=1;
    test_fire_input(self,enemy,conc,0,0); bot.previous[INPUT_FUNC_FIRE1]=0; test_fire_input(self,enemy,conc,0,2);
    enemy->position.y=2; p->aItems[SITHBIN_POWER].amount=40; bot.previous[INPUT_FUNC_FIRE2]=1;
    test_fire_input(self,enemy,conc,0,0); bot.previous[INPUT_FUNC_FIRE2]=0; test_fire_input(self,enemy,conc,0,1);
    puts("PASS concussion mode holds actual buttons for splash or stock-range beam, verifies first target and physical aim, rejects unsafe lines, enforces ammo and neutral handoff");

    enemy->position.y=.45f; test_fire_input(self,enemy,rpt,0,2);
    enemy->position.y=1.1f; test_fire_input(self,enemy,rpt,0,1);
    enemy->position.y=.45f; test_fire_input(self,enemy,rpt,4,1);
    p->aItems[SITHBIN_POWER].amount=2; test_fire_input(self,enemy,rpt,0,1);
    test_fire_input(self,enemy,bow,0,2); ally->position.x=3; test_fire_input(self,enemy,bow,0,0);
    ally->position.x=10; p->aItems[SITHBIN_POWER].amount=1; test_fire_input(self,enemy,bow,0,0);
    enemy->position.y=2; test_fire_input(self,enemy,SITHBIN_RAIL_DETONATOR,0,1);
    test_fire_input(self,enemy,SITHBIN_THERMAL_DETONATOR,0,0); test_fire_input(self,enemy,SITHBIN_SEQUENCER_CHARGE,0,0);
    test_fire_input(self,enemy,SITHBIN_BRYARPISTOL,0,1); test_fire_input(self,enemy,SITHBIN_STORMTROOPER_RIFLE,0,1);
    puts("PASS repeater uses converging short burst and falls back for spread or low charge; bow uses safe immediate release-free mode; rail and blasters use primary");

    enemy->position.y=.20f; test_fire_input(self,enemy,SITHBIN_LIGHTSABER,0,1);
    enemy->actorParams.flags|=SITH_AF_IMMOBILE; test_fire_input(self,enemy,SITHBIN_LIGHTSABER,0,2);
    self->sector->flags|=SITH_SECTOR_UNDERWATER;
    test_fire_input(self,enemy,SITHBIN_LIGHTSABER,0,1); self->sector->flags&=~SITH_SECTOR_UNDERWATER;
    enemy->actorParams.flags&=~SITH_AF_IMMOBILE;
    enemy->position.y=.30f; test_fire_input(self,enemy,SITHBIN_LIGHTSABER,0,0);
    p->aItems[SITHBIN_POWER].amount=40; enemy->position.y=2; nav.combatJumpUntil=bot.now+5;
    test_fire_input(self,enemy,conc,0,0); test_fire_input(self,enemy,SITHBIN_RAIL_DETONATOR,0,0);
    test_fire_input(self,enemy,rpt,0,1); p->curWeaponID=SITHBIN_BRYARPISTOL;
    test_selection_pulse(self,enemy,SITHBIN_STORMTROOPER_RIFLE);
    nav.combatJumpUntil=0; test_selection_pulse(self,enemy,conc);
    puts("PASS saber preserves bolt guard, selects dry heavy only on immobilized contact; tactical jump suppresses recoil guns and allows ordinary fire");

    /* Exercise the full movement/aim/Force dispatch at short range. */
    enemy->position.y=.40f; p->curWeaponID=conc; bot.targetSlot=1;
    bot.forceEnabled=0; bot.routeAim=0; bot.routeMode=0; self->actorParams.headPYR.x=0;
    memset(bot.keys,0,sizeof(bot.keys)); Bot_Combat(self,enemy);
    assert(!bot.keys[INPUT_FUNC_FIRE1] && bot.keys[INPUT_FUNC_FIRE2]);
    bot.traceForce=1; bot.tracedFireMode=-1; bot.nextFireTrace=0;
    Bot_TraceFireInput(self); assert(bot.tracedFireMode==2*conc+1);
    bot.keys[INPUT_FUNC_FIRE1]=1; bot.keys[INPUT_FUNC_FIRE2]=0;
    Bot_TraceFireInput(self); assert(bot.tracedFireMode==2*conc+1);
    bot.now+=.5f; Bot_TraceFireInput(self); assert(bot.tracedFireMode==2*conc);
    bot.traceForce=0; testConcBeam=(SithThing){0}; self->attach_flags=0;
    puts("PASS combat dispatch produces ordinary secondary input; optional final-input log limits mode changes to two per second");
}
