/* Controlled policy and input tests. Engine effects remain live-test work. */
static void test_bot_behavior(void)
{
    SithSector sector={0}; SithThing self={0},peer={0},shot={0};
    SithPlayer own={0}; jkPlayerInfo remote={0}; rdModel3 fists={0},gun={0},saber={0},bomb={0};
    strcpy(fists.filename,"fistg.3do"); strcpy(gun.filename,"strg.3do");
    strcpy(saber.filename,"sabg.3do"); strcpy(bomb.filename,"detg.3do");
    jkBot_Configure("Bot_Policy","ky.3do"); bot.joined=1; bot.now=10;
    corridorMode=0; testLOS=1; sithNet_MultiModeFlags=0; jkPlayer_maxPlayers=2;
    self.type=peer.type=SITH_THING_PLAYER; self.sector=peer.sector=&sector;
    self.actorParams.pPlayer=&own; self.actorParams.health=100; self.collideSize=0.065f;
    self.orient.lvec=(rdVector3){0,1,0}; self.orient.rvec=(rdVector3){1,0,0};
    self.actorParams.maxRotVelocity=200;
    peer.playerInfo=&remote; remote.rd_thing.model3=&fists;
    peer.position=(rdVector3){0,0.20f,0}; peer.collideSize=0.065f; peer.signature=9; peer.guid=42;
    jkPlayer_playerInfos[1].flags=1; jkPlayer_playerInfos[1].playerNetId=42;
    jkPlayer_playerInfos[1].pLocalPlayer=&peer;
    sithPlayer_g_pLocalPlayerThing=&self;
    assert(Bot_WeaponFromModel(&fists)==SITHBIN_FISTS);
    assert(Bot_WeaponFromModel(&bomb)==SITHBIN_THERMAL_DETONATOR);
    assert(Bot_IsPeaceful(&self,1) && !Bot_EnemyAllowed(&self,1));
    /* Remote curWeaponID is intentionally stale and irrelevant. */
    jkPlayer_playerInfos[1].curWeaponID=SITHBIN_CONCUSSION_RIFLE;
    assert(Bot_IsPeaceful(&self,1));
    remote.rd_thing.model3=&bomb; assert(!Bot_IsPeaceful(&self,1)); remote.rd_thing.model3=&fists;
    jkBot_ObserveDamage(&self,NULL,10); assert(Bot_IsPeaceful(&self,1));
    jkBot_ObserveDamage(&self,&self,10); assert(Bot_IsPeaceful(&self,1));
    shot.type=SITH_THING_WEAPON; shot.pParent=&peer; shot.parentSignature=8;
    jkBot_ObserveDamage(&self,&shot,10); assert(Bot_IsPeaceful(&self,1));
    shot.parentSignature=9; jkBot_ObserveDamage(&self,&shot,10);
    assert(!Bot_IsPeaceful(&self,1) && Bot_EnemyAllowed(&self,1));
    bot.now+=15.1f; assert(Bot_IsPeaceful(&self,1));
    jkBot_ObserveDamage(&self,&peer,10); assert(!Bot_IsPeaceful(&self,1));
    jkPlayer_playerInfos[1].playerNetId=43; assert(Bot_IsPeaceful(&self,1));
    jkBot_ObserveSkill(&self,&peer,SITHBIN_F_HEALING); assert(Bot_IsPeaceful(&self,1));
    jkBot_ObserveSkill(&self,&peer,SITHBIN_F_PULL); assert(!Bot_IsPeaceful(&self,1));
    peer.guid++; assert(Bot_IsPeaceful(&self,1));
    puts("PASS fists mesh identity, explicit damage/Force attribution, expiry and identity reset");
    remote.rd_thing.model3=&gun; peer.jkFlags=JKFLAG_PERSUASION;
    assert(!Bot_EnemyAllowed(&self,1));
    own.aItems[SITHBIN_F_SEEING].state=SITHINVENTORY_ITEM_ACTIVATED;
    assert(Bot_EnemyAllowed(&self,1));
    own.aItems[SITHBIN_F_SEEING].state=0;
    bot.targetSlot=1; bot.targetGuid=(int)peer.guid; bot.nextScan=0;
    assert(Bot_UpdateTarget(&self)==NULL && bot.targetSlot==-1);
    peer.jkFlags=0; self.actorParams.flags=SITH_AF_BLIND;
    own.aItems[SITHBIN_F_SEEING].state=SITHINVENTORY_ITEM_ACTIVATED;
    bot.targetSlot=1; bot.targetGuid=(int)peer.guid;
    assert(!Bot_EnemyAllowed(&self,1) && Bot_UpdateTarget(&self)==NULL && bot.targetSlot==-1);
    assert(!Bot_SafeShot(&self,&peer,peer.position,0,0));
    self.actorParams.flags=0; own.aItems[SITHBIN_F_SEEING].state=0;
    assert(Bot_EnemyAllowed(&self,1)); remote.rd_thing.model3=&fists;
    puts("PASS blinded perception/fire suppression and Persuasion visibility only with active Seeing");
    strcpy(shot.aName,"+punch");
    shot.weaponParams.damage=10; rdVector3 away={0,1,0},atSelf={0,-1,0};
    jkBot_ObserveProjectile(&peer,&shot,&away); assert(Bot_IsPeaceful(&self,1));
    testLOS=0; jkBot_ObserveProjectile(&peer,&shot,&atSelf); assert(Bot_IsPeaceful(&self,1)); testLOS=1;
    jkBot_ObserveProjectile(&peer,&shot,&atSelf); assert(!Bot_IsPeaceful(&self,1));
    peer.guid++; Bot_Peer(1); peer.position.y=2.0f;
    jkBot_ObserveProjectile(&peer,&shot,&atSelf); assert(Bot_IsPeaceful(&self,1));
    strcpy(shot.aName,"+stlaser"); jkBot_ObserveProjectile(&peer,&shot,&atSelf);
    assert(!Bot_IsPeaceful(&self,1)); /* gun fired before shooter switched to fists */
    peer.position.y=0.20f;
    peer.guid++; Bot_Peer(1); jkBot_ObserveWeapon(&peer,&fists);
    for (int i=0;i<3;i++) { bot.now+=0.3f; jkBot_ObserveWeapon(&peer,i%2 ? &fists : &gun); }
    assert(Bot_IsPeaceful(&self,1));
    jkBot_ObserveWeapon(&peer,&fists); assert(!Bot_IsPeaceful(&self,1));
    peer.guid++; Bot_Peer(1); bot.now+=1;
    for (int i=0;i<10;i++) { bot.now+=0.1f; Bot_ObserveBlock(&self,(rdVector3){0,1,0}); }
    assert(Bot_IsPeaceful(&self,1));
    bot.now+=0.5f; Bot_ObservePeers(&self); /* brief contact is forgotten */
    for (int i=0;i<32;i++) { bot.now+=0.1f; Bot_ObserveBlock(&self,(rdVector3){0,1,0}); }
    assert(!Bot_IsPeaceful(&self,1));
    peer.guid++; Bot_Peer(1); self.physicsParams.vel.y=0.4f;
    for (int i=0;i<40;i++) { bot.now+=0.1f; Bot_ObserveBlock(&self,(rdVector3){0,1,0}); }
    assert(Bot_IsPeaceful(&self,1)); self.physicsParams.vel.y=0;
    puts("PASS missed/occluded fire, rapid swaps, persistent blocking and passing-player exclusions");
    FILE *f=tmpfile(); assert(f); int a=9,b=9,c=9;
    fputs("version=1\nsabers_only=1\nfists_peace=0\nforce_enabled=1\n",f); rewind(f);
    assert(Bot_ReadBehavior(f,&a,&b,&c) && a==1 && b==0 && c==1); fclose(f);
    const char *bad[]={"version=1\nsabers_only=1\n", "version=2\nsabers_only=1\nfists_peace=0\nforce_enabled=1\n",
        "version=1\nsabers_only=1\nfists_peace=0\nforce_enabled=true\n",
        "version=1\nsabers_only=1\nfists_peace=0\nforce_enabled=1\nforce_enabled=0\n"};
    for (unsigned i=0;i<sizeof(bad)/sizeof(*bad);i++) {
        a=b=c=9; f=tmpfile(); assert(f); fputs(bad[i],f); rewind(f);
        assert(!Bot_ReadBehavior(f,&a,&b,&c) && a==9 && b==9 && c==9); fclose(f);
    }
    puts("PASS complete atomic behavior config and invalid/partial/duplicate rejection");
    jkBot_Configure("Bot_Weapon","ky.3do"); bot.joined=1; bot.now=10;
    sithPlayer_g_pLocalPlayerThing=&self; bot.targetSlot=1; bot.fistsPeace=0;
    remote.rd_thing.model3=&gun; peer.position=(rdVector3){0,4,0}; own.curWeaponID=SITHBIN_STORMTROOPER_RIFLE;
    for (int i=1;i<=10;i++) { own.aItems[i].state=SITHINVENTORY_ITEM_AVAILABLE; own.aItems[i].amount=1; }
    own.aItems[SITHBIN_ENERGY].amount=1; own.aItems[SITHBIN_POWER].amount=1;
    assert(Bot_HasWeapon(&self,SITHBIN_BRYARPISTOL)); assert(Bot_HasWeapon(&self,SITHBIN_REPEATER));
    assert(!Bot_HasWeapon(&self,SITHBIN_TUSKEN_PROD)); assert(!Bot_HasWeapon(&self,SITHBIN_CONCUSSION_RIFLE));
    bot.sabersOnly=1; Bot_SelectWeapon(&self,4);
    assert(bot.keys[INPUT_FUNC_SELECT1+SITHBIN_LIGHTSABER-1]);
    memset(bot.keys,0,sizeof(bot.keys)); Bot_Combat(&self,&peer);
    assert(!bot.keys[INPUT_FUNC_FIRE1] && !bot.keys[INPUT_FUNC_FIRE2]);
    bot.sabersOnly=0; bot.fistsPeace=1; remote.rd_thing.model3=&fists;
    assert(!Bot_SafeShot(&self,&peer,peer.position,0,0));
    remote.rd_thing.model3=&gun; sithNet_MultiModeFlags=MULTIMODEFLAG_TEAMS;
    own.teamNum=jkPlayer_playerInfos[1].teamNum=1;
    assert(!Bot_SafeShot(&self,&peer,peer.position,0,0)); sithNet_MultiModeFlags=0;
    puts("PASS real ammo thresholds, saber-only switch/fire restraint, peace and team fire safety");
    memset(bot.keys,0,sizeof(bot.keys)); bot.nextForce=0; bot.forceBin=-1;
    peer.position.y=0.75f;
    own.aItems[SITHBIN_F_GRIP].amount=3; own.aItems[SITHBIN_F_GRIP].state=SITHINVENTORY_ITEM_AVAILABLE;
    own.aItems[SITHBIN_FORCEMANA].amount=49; sithTime_g_secGameTime=10;
    assert(!Bot_RequestForce(&self,SITHBIN_F_GRIP,0.46f,1));
    own.aItems[SITHBIN_FORCEMANA].amount=50;
    assert(Bot_RequestForce(&self,SITHBIN_F_GRIP,0.46f,1));
    assert(bot.keys[Bot_PowerKey(SITHBIN_F_GRIP)] && own.aItems[SITHBIN_FORCEMANA].amount==50);
    bot.now+=0.2f; memset(bot.keys,0,sizeof(bot.keys)); Bot_ForceTick(&self,&peer,0);
    assert(bot.keys[Bot_PowerKey(SITHBIN_F_GRIP)]);
    bot.now+=0.3f; memset(bot.keys,0,sizeof(bot.keys)); Bot_ForceTick(&self,&peer,0);
    assert(!bot.keys[Bot_PowerKey(SITHBIN_F_GRIP)] && bot.forceBin<0);
    bot.nextForce=0; remote.rd_thing.model3=&fists;
    assert(!Bot_RequestForce(&self,SITHBIN_F_GRIP,0.46f,1));
    remote.rd_thing.model3=&gun; bot.forceEnabled=0;
    assert(!Bot_RequestForce(&self,SITHBIN_F_GRIP,0.46f,1)); bot.forceEnabled=1;
    own.aItems[SITHBIN_F_GRIP].binWait=11;
    assert(!Bot_RequestForce(&self,SITHBIN_F_GRIP,0.46f,1));
    own.aItems[SITHBIN_F_GRIP].binWait=0;
    assert(Bot_RequestForce(&self,SITHBIN_F_GRIP,0.46f,1));
    own.curPower=SITHBIN_F_GRIP; remote.rd_thing.model3=&fists;
    memset(bot.keys,0,sizeof(bot.keys)); Bot_ForceTick(&self,&peer,0);
    assert(bot.keys[Bot_PowerKey(SITHBIN_F_GRIP)] && bot.keys[INPUT_FUNC_NEXTSKILL]);
    own.curPower=SITHBIN_F_JUMP; memset(bot.keys,0,sizeof(bot.keys)); Bot_ForceTick(&self,&peer,0);
    assert(!bot.keys[Bot_PowerKey(SITHBIN_F_GRIP)] && bot.forceBin<0);
    puts("PASS Force mana/availability/cooldown gates, held targeting/release and peaceful-target cancellation");
    bot.nextForce=0; bot.forceBin=-1; bot.forceCancel=0;
    remote.rd_thing.model3=&gun; peer.position.y=2.0f;
    assert(!Bot_RequestForce(&self,SITHBIN_F_GRIP,0.46f,1));
    assert(Bot_ForceRange(&self,SITHBIN_F_GRIP)==1.0f);
    own.aItems[SITHBIN_F_PULL].amount=4;
    assert(Bot_ForceRange(&self,SITHBIN_F_PULL)==2.5f);
    own.aItems[SITHBIN_F_BLINDING].amount=2;
    assert(Bot_ForceRange(&self,SITHBIN_F_BLINDING)==3.0f);
    own.aItems[SITHBIN_S_DARK].amount=1; own.aItems[SITHBIN_FORCEMANA].amount=0;
    assert(Bot_ForceCost(&self,SITHBIN_F_GRIP)==50);
    assert(!Bot_ForceReady(&self,SITHBIN_F_GRIP,Bot_ForceCost(&self,SITHBIN_F_GRIP)));
    own.aItems[SITHBIN_FORCEMANA].amount=400;
    own.aItems[SITHBIN_F_DEADLYSIGHT].amount=4;
    own.aItems[SITHBIN_F_DEADLYSIGHT].state=SITHINVENTORY_ITEM_AVAILABLE;
    bot.fistsPeace=1;
    assert(!Bot_RequestForce(&self,SITHBIN_F_DEADLYSIGHT,0.1f,1));
    bot.fistsPeace=0; sithNet_MultiModeFlags=MULTIMODEFLAG_TEAMS;
    assert(!Bot_RequestForce(&self,SITHBIN_F_DEADLYSIGHT,0.1f,1)); sithNet_MultiModeFlags=0;
    assert(Bot_RequestForce(&self,SITHBIN_F_DEADLYSIGHT,0.1f,1));
    own.aItems[SITHBIN_F_DEADLYSIGHT].state|=SITHINVENTORY_ITEM_ACTIVATED;
    bot.fistsPeace=1; memset(bot.keys,0,sizeof(bot.keys)); Bot_ForceTick(&self,&peer,0);
    assert(bot.forceAvoid && !bot.keys[INPUT_FUNC_FIRE1] && !bot.keys[INPUT_FUNC_NEXTSKILL]);
    assert(sithInventory_IsInventoryActivated(&self,SITHBIN_F_DEADLYSIGHT));
    own.aItems[SITHBIN_F_DEADLYSIGHT].state=0;
    bot.nextForce=0; bot.forceBin=-1; bot.forceEffectBin=-1; bot.fistsPeace=0;
    SithCogSymbol victimSymbol={0}; SithCogSymbolTable table={0}; sithCog throwCog={0};
    victimSymbol.pName="victim"; victimSymbol.val.type=COG_TYPE_INT; victimSymbol.val.data[0]=peer.idx;
    table.aSymbols=&victimSymbol; table.tableSize=table.numUsedSymbols=1; throwCog.pSymbolTable=&table;
    testInventoryTypes[SITHBIN_F_THROW].cog=&throwCog;
    own.aItems[SITHBIN_F_THROW].amount=3; own.aItems[SITHBIN_F_THROW].state=SITHINVENTORY_ITEM_AVAILABLE;
    assert(Bot_RequestForce(&self,SITHBIN_F_THROW,0.46f,1)); own.curPower=SITHBIN_F_THROW;
    bot.fistsPeace=1; remote.rd_thing.model3=&fists; memset(bot.keys,0,sizeof(bot.keys));
    Bot_ForceTick(&self,&peer,0); assert(bot.forceCancel && bot.forceAvoid);
    assert(bot.keys[Bot_PowerKey(SITHBIN_F_THROW)] && !bot.keys[INPUT_FUNC_NEXTSKILL]);
    victimSymbol.val.data[0]=-1; memset(bot.keys,0,sizeof(bot.keys)); Bot_ForceTick(&self,&peer,0);
    assert(!bot.keys[Bot_PowerKey(SITHBIN_F_THROW)] && bot.forceBin<0 && !bot.forceCancel);
    puts("PASS stock Force ranges/surge eligibility, restricted area powers and source-correct Throw cancellation");
    memset(own.aItems,0,sizeof(own.aItems)); memset(bot.keys,0,sizeof(bot.keys));
    own.curWeaponID=SITHBIN_TUSKEN_PROD; own.aItems[SITHBIN_TUSKEN_PROD].amount=1;
    own.aItems[SITHBIN_TUSKEN_PROD].state=SITHINVENTORY_ITEM_AVAILABLE; own.aItems[SITHBIN_POWER].amount=10;
    bot.forceEnabled=0; bot.fistsPeace=1; bot.forceAvoid=bot.forceCancel=0;
    remote.rd_thing.model3=&gun; peer.position.y=2; bot.reactionUntil=0;
    Bot_Combat(&self,&peer); assert(!bot.keys[INPUT_FUNC_FIRE1] && bot.keys[INPUT_FUNC_FIRE2]);
    remote.rd_thing.model3=&fists; memset(bot.keys,0,sizeof(bot.keys));
    Bot_Combat(&self,&peer); assert(!bot.keys[INPUT_FUNC_FIRE1] && !bot.keys[INPUT_FUNC_FIRE2]);
    puts("PASS bowcaster uses immediate alternate, no charged release into a newly peaceful target");
    SithThing debris[2]={{0}}; SithWorld debrisWorld={0};
    debrisWorld.aThings=debris; debrisWorld.numThings=1; debrisWorld.numThingsLoaded=2;
    bot.world=&debrisWorld; debris[1].type=SITH_THING_DEBRIS; debris[1].position.y=1;
    assert(Bot_ForceDebris(&self)); /* final active slot is included */
    debrisWorld.numThings=0; assert(!Bot_ForceDebris(&self));
    debris[0].type=SITH_THING_DEBRIS; debrisWorld.numThingsLoaded=1;
    assert(Bot_ForceDebris(&self)); /* one-thing world uses highest index zero */
    debris[0].type=SITH_THING_FREE; debrisWorld.numThings=1;
    assert(!Bot_ForceDebris(&self)); /* final index is capped by allocated capacity */
    debrisWorld.numThings=-1; assert(!Bot_ForceDebris(&self));
    bot.world=NULL; assert(!Bot_ForceDebris(&self));
    puts("PASS Force debris includes final active slot and respects empty/single/capacity bounds");
    sithPlayer_g_pLocalPlayerThing=NULL;
}
