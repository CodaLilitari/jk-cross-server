/* Controlled policy and input tests. Engine effects remain live-test work. */
#include <unistd.h>

static void test_force_trace(SithThing *self)
{
    /* Read back the same optional line consumed by a connected observer. */
    FILE *capture=tmpfile(); assert(capture);
    fflush(stderr);
    int saved=dup(STDERR_FILENO); assert(saved>=0);
    assert(dup2(fileno(capture),STDERR_FILENO)>=0);
    assert(unsetenv("JK_BOT_TRACE_FORCE")==0);
    jkBot_Configure("Bot_Trace","ky.3do");
    Bot_TraceForce(self); assert(ftell(capture)==0);
    assert(setenv("JK_BOT_TRACE_FORCE","1",1)==0);
    jkBot_Configure("Bot_Trace","ky.3do"); assert(unsetenv("JK_BOT_TRACE_FORCE")==0);
    SithPlayer *player=self->actorParams.pPlayer;
    memset(player->aItems,0,sizeof(player->aItems));
    self->idx=5; self->guid=901; self->actorParams.flags=SITH_AF_IMMOBILE;
    self->actorParams.health=94;
    player->aItems[SITHBIN_F_SEEING].amount=4;
    player->aItems[SITHBIN_F_SEEING].state=SITHINVENTORY_ITEM_ACTIVATED;
    player->aItems[SITHBIN_SHIELDS].amount=25; player->aItems[SITHBIN_FORCEMANA].amount=90;
    Bot_TraceForce(self); long first=ftell(capture); assert(first>0);
    bot.now=0.49f; Bot_TraceForce(self); assert(ftell(capture)==first);
    bot.now=0.5f; Bot_TraceForce(self); assert(ftell(capture)>first);
    assert(dup2(saved,STDERR_FILENO)>=0); close(saved);
    rewind(capture); char line[512]; assert(fgets(line,sizeof(line),capture));
    assert(!strcmp(line,"BOT_FORCE_STATE name=Bot_Trace t=0.00 thing=5 guid=901 health=94.00 shields=25.00 "
        "mana=90.00 blind=0 immobile=1 stars=0,0,4,0,0,0,0,0,0,0,0,0,0,0 active=0x4\n"));
    assert(fgets(line,sizeof(line),capture) && strstr(line,"t=0.50 "));
    assert(!fgets(line,sizeof(line),capture)); fclose(capture);
    puts("PASS local Force state receipt, opt-in gate, bin ordering and half-second cadence");
}

static void test_force_frame(void)
{
    memcpy(bot.previous,bot.keys,sizeof(bot.keys));
    memset(bot.keys,0,sizeof(bot.keys));
}

static void test_competitive_force(SithThing *self, SithThing *peer, rdModel3 *gun, rdModel3 *fists)
{
    SithPlayer *own=self->actorParams.pPlayer;
    assert(setenv("JK_BOT_FORCE_STYLE","competitive",1)==0);
    jkBot_Configure("Bot_Competitive","ky.3do");
    assert(unsetenv("JK_BOT_FORCE_STYLE")==0);
    bot.fistsPeace=1; /* written with fists-as-peace on; the logic is kept */
    bot.joined=1; bot.now=20; bot.targetSlot=1;
    memset(own->aItems,0,sizeof(own->aItems));
    peer->playerInfo->rd_thing.model3=gun;
    peer->position.y=0.7f; peer->idx=7;
    int seeing=SITHBIN_F_SEEING, absorb=SITHBIN_F_ABSORB, grip=SITHBIN_F_GRIP;
    own->aItems[seeing].amount=own->aItems[absorb].amount=4;
    own->aItems[seeing].state=own->aItems[absorb].state=SITHINVENTORY_ITEM_AVAILABLE;
    own->aItems[SITHBIN_FORCEMANA].amount=400;
    /* An unseen or peaceful peer alone supplies no engagement cue. */
    testLOS=0; Bot_ForceTick(self,peer,0); assert(bot.forceBin==-1); testLOS=1;
    peer->playerInfo->rd_thing.model3=fists;
    Bot_ForceTick(self,peer,0); assert(bot.forceBin==-1);
    peer->playerInfo->rd_thing.model3=gun;
    self->actorParams.flags=SITH_AF_CONTROLSDISABLED;
    Bot_ForceTick(self,peer,0); assert(bot.forceBin==-1); self->actorParams.flags=0;
    bot.forceEnabled=0; Bot_ForceTick(self,peer,0); assert(bot.forceBin==-1); bot.forceEnabled=1;
    own->aItems[SITHBIN_FORCEMANA].amount=29;
    Bot_ForceTick(self,peer,0); assert(bot.forceBin==-1);
    own->aItems[SITHBIN_FORCEMANA].amount=400;
    /* Engagement still warrants Absorb. Seeing requires a specific cue. */
    Bot_ForceTick(self,peer,0); assert(bot.forceBin==absorb);
    bot.now+=1; test_force_frame(); Bot_ForceTick(self,NULL,180);
    own->aItems[absorb].binWait=sithTime_g_secGameTime+1;
    Bot_ForceTick(self,peer,0); assert(bot.forceBin<0);
    bot.hurtUntil=bot.now+5;
    Bot_ForceTick(self,NULL,180); assert(bot.forceBin<0);
    bot.hurtUntil=0; bot.forceThreatUntil=bot.now+5;
    Bot_ForceTick(self,NULL,180); assert(bot.forceBin<0);
    bot.forceThreatUntil=0;
    peer->jkFlags|=JKFLAG_PERSUASION;
    /* Force Jump uses the same twinkle flag for 0.33 seconds. */
    Bot_ForceTick(self,peer,0); assert(bot.forceBin<0 && Bot_EnemyAllowed(self,1));
    peer->actorParams.flags|=SITH_AF_INVISIBLE;
    testLOS=0; Bot_ForceTick(self,NULL,180); assert(bot.forceBin<0); testLOS=1;
    peer->playerInfo->rd_thing.model3=fists;
    Bot_ForceTick(self,NULL,180); assert(bot.forceBin<0);
    peer->playerInfo->rd_thing.model3=gun;
    own->aItems[SITHBIN_FORCEMANA].amount=29;
    Bot_ForceTick(self,NULL,180); assert(bot.forceBin<0);
    own->aItems[SITHBIN_FORCEMANA].amount=400;
    Bot_ForceTick(self,NULL,180); assert(bot.forceBin==seeing && bot.keys[Bot_PowerKey(seeing)]);
    own->aItems[seeing].state|=SITHINVENTORY_ITEM_ACTIVATED;
    bot.now+=1; test_force_frame(); Bot_ForceTick(self,NULL,180); assert(bot.forceBin<0);
    Bot_ForceTick(self,NULL,180); assert(bot.forceBin<0);
    peer->jkFlags&=~JKFLAG_PERSUASION;
    peer->actorParams.flags&=~SITH_AF_INVISIBLE;
    own->aItems[seeing].state=SITHINVENTORY_ITEM_AVAILABLE;
    bot.now+=26; test_force_frame(); Bot_ForceTick(self,peer,0); assert(bot.forceBin<0);
    self->actorParams.flags=SITH_AF_BLIND;
    Bot_ForceTick(self,NULL,180); assert(bot.forceBin==seeing);
    assert(self->actorParams.flags&SITH_AF_BLIND); /* Seeing does not cure an existing Blind. */
    bot.now+=1; test_force_frame(); Bot_ForceTick(self,NULL,180);
    self->actorParams.flags=0;
    sithTime_g_secGameTime+=1;
    Bot_ForceTick(self,peer,0); assert(bot.forceBin==absorb);
    puts("PASS Seeing responds to local Blind or visible hostile Persuasion, skips routine combat and generic threats");
    bot.now+=1; test_force_frame(); Bot_ForceTick(self,NULL,180);
    own->aItems[seeing].state=0; bot.hurtUntil=0; bot.forceThreatUntil=bot.now+5;
    own->aItems[SITHBIN_F_HEALING].state=SITHINVENTORY_ITEM_AVAILABLE;
    own->aItems[SITHBIN_F_HEALING].amount=4; self->actorParams.health=50;
    Bot_ForceTick(self,NULL,180); assert(bot.forceBin==SITHBIN_F_HEALING);
    bot.now+=1; test_force_frame(); Bot_ForceTick(self,NULL,180); self->actorParams.health=100;
    Bot_ForceTick(self,NULL,180); assert(bot.forceBin==absorb);
    bot.now+=1; test_force_frame(); Bot_ForceTick(self,NULL,180); bot.forceThreatUntil=0;
    own->aItems[absorb].state=0; Bot_ForceTick(self,peer,0); assert(bot.forceBin<0);
    own->aItems[SITHBIN_FORCEMANA].amount=0;
    own->aItems[SITHBIN_F_PROTECTION].amount=4;
    assert(!Bot_RequestForce(self,SITHBIN_F_PROTECTION,0.1f,-1));
    own->aItems[SITHBIN_F_PROTECTION].state=SITHINVENTORY_ITEM_AVAILABLE;
    assert(Bot_RequestForce(self,SITHBIN_F_PROTECTION,0.1f,-1));
    puts("PASS urgent healing, provocation and Protection eligibility");
    bot.now+=1; test_force_frame(); Bot_ForceTick(self,NULL,180);
    own->aItems[SITHBIN_FORCEMANA].amount=400;
    own->aItems[grip].amount=4; own->aItems[grip].state=SITHINVENTORY_ITEM_AVAILABLE;
    SithCogSymbol marker={0}; SithCogSymbolTable table={0}; sithCog cog={0};
    table.aSymbols=&marker; table.tableSize=table.numUsedSymbols=1; cog.pSymbolTable=&table;
    int pull=SITHBIN_F_PULL;
    rdModel3 bryar={0}, saber={0};
    strcpy(bryar.filename,"bryg.3do"); strcpy(saber.filename,"sabg.3do");
    own->aItems[pull].amount=4; own->aItems[pull].state=SITHINVENTORY_ITEM_AVAILABLE;
    testInventoryTypes[pull].cog=&cog;
    marker.pName="victim"; marker.val.type=COG_TYPE_INT;
    bot.fistsPeace=0;
    peer->playerInfo->rd_thing.model3=&saber;
    assert(!Bot_RequestForce(self,pull,0.46f,1));
    peer->playerInfo->rd_thing.model3=fists;
    assert(!Bot_RequestForce(self,pull,0.46f,1));
    peer->playerInfo->rd_thing.model3=NULL;
    assert(!Bot_RequestForce(self,pull,0.46f,1));
    enum { PULL_WRONG_MARKER, PULL_NO_MARKER, PULL_DISARMED, PULL_SWAPPED_GUN, PULL_REARMED_DURING_LOCK,
           PULL_REUSED_INDEX, PULL_OUT_OF_RANGE, PULL_MATCH };
    for (int scenario=PULL_WRONG_MARKER;scenario<=PULL_MATCH;scenario++) {
        peer->playerInfo->rd_thing.model3=&bryar;
        peer->position.y=0.7f;
        if (scenario==PULL_MATCH) {
            jkBot_ObserveWeapon(peer,fists);
            jkBot_ObserveWeapon(peer,&bryar);
        }
        bot.now+=3; test_force_frame();
        assert(Bot_RequestForce(self,pull,0.46f,1)); own->curPower=pull;
        marker.val.data[0]=(int)peer->idx;
        if (scenario==PULL_WRONG_MARKER) marker.val.data[0]++;
        if (scenario==PULL_NO_MARKER) marker.val.data[0]=-1;
        if (scenario==PULL_DISARMED) peer->playerInfo->rd_thing.model3=fists;
        if (scenario==PULL_SWAPPED_GUN) peer->playerInfo->rd_thing.model3=gun;
        if (scenario==PULL_REARMED_DURING_LOCK) {
            jkBot_ObserveWeapon(peer,gun);
            jkBot_ObserveWeapon(peer,&bryar);
        }
        if (scenario==PULL_REUSED_INDEX) marker.val.data[0]=++peer->idx;
        if (scenario==PULL_OUT_OF_RANGE) peer->position.y=3;
        bot.now+=0.5f; test_force_frame(); Bot_ForceTick(self,peer,0);
        if (scenario!=PULL_MATCH) {
            assert(bot.forceCancel && bot.keys[INPUT_FUNC_NEXTSKILL]);
            own->curPower=SITHBIN_F_JUMP;
            test_force_frame(); Bot_ForceTick(self,peer,0);
            if (scenario==PULL_WRONG_MARKER || scenario==PULL_NO_MARKER) {
                assert(!Bot_RequestForce(self,pull,0.46f,1));
                assert(!bot.keys[Bot_PowerKey(pull)]);
            }
            if (scenario==PULL_WRONG_MARKER) {
                SithThing other=*peer;
                other.idx++; other.guid++;
                jkPlayer_maxPlayers=3; jkPlayer_playerInfos[2]=jkPlayer_playerInfos[1];
                jkPlayer_playerInfos[2].playerNetId++; jkPlayer_playerInfos[2].pLocalPlayer=&other;
                assert(Bot_RequestForce(self,pull,0.46f,2)); own->curPower=pull;
                bot.now+=0.5f; marker.val.data[0]=-1;
                test_force_frame(); Bot_ForceTick(self,&other,0);
                assert(bot.forceCancel);
                own->curPower=SITHBIN_F_JUMP;
                test_force_frame(); Bot_ForceTick(self,&other,0);
                jkPlayer_maxPlayers=2;
                memset(&jkPlayer_playerInfos[2],0,sizeof(jkPlayer_playerInfos[2]));
                bot.now+=0.49f;
                assert(!Bot_RequestForce(self,pull,0.46f,1)); /* 0.99 s after deselection */
                bot.now+=0.02f;
                assert(Bot_RequestForce(self,pull,0.46f,1));
                own->curPower=pull;
                bot.now+=0.5f; test_force_frame(); Bot_ForceTick(self,peer,0);
                assert(bot.forceCancel);
                own->curPower=SITHBIN_F_JUMP;
                test_force_frame(); Bot_ForceTick(self,peer,0);
            }
            if (scenario==PULL_NO_MARKER) {
                peer->flags|=SITH_TF_DEAD; Bot_ObservePeers(self);
                peer->flags&=~SITH_TF_DEAD;
                assert(Bot_RequestForce(self,pull,0.46f,1)); /* same thing, new life */
                own->curPower=pull;
                bot.now+=0.5f; test_force_frame(); Bot_ForceTick(self,peer,0);
                own->curPower=SITHBIN_F_JUMP;
                test_force_frame(); Bot_ForceTick(self,peer,0);
            }
            if (scenario==PULL_SWAPPED_GUN || scenario==PULL_REARMED_DURING_LOCK || scenario==PULL_REUSED_INDEX) {
                assert(Bot_RequestForce(self,pull,0.46f,1)); /* changed equipment or identity has no debt */
                own->curPower=pull;
                bot.now+=0.5f; test_force_frame(); Bot_ForceTick(self,peer,0);
            }
        }
        assert(bot.forceBin<0 && !bot.keys[Bot_PowerKey(pull)]);
    }
    puts("PASS cancelled Pull retries wait per gun and opponent, allow a changed gun and fresh life");
    /* The matching release above is still awaiting a visible weapon change. */
    bot.now+=0.5f; test_force_frame();
    assert(!Bot_RequestForce(self,pull,0.46f,1));
    /* A different opponent can be disarmed while the first one's result is pending. */
    SithThing other=*peer;
    other.idx++; other.guid++;
    jkPlayer_maxPlayers=3; jkPlayer_playerInfos[2]=jkPlayer_playerInfos[1];
    jkPlayer_playerInfos[2].playerNetId++; jkPlayer_playerInfos[2].pLocalPlayer=&other;
    assert(Bot_RequestForce(self,pull,0.46f,2));
    bot.now+=0.5f; test_force_frame(); Bot_ForceTick(self,&other,0);
    assert(bot.forceCancel); /* marker still points at the first opponent */
    own->curPower=SITHBIN_F_JUMP;
    test_force_frame(); Bot_ForceTick(self,&other,0);
    jkPlayer_maxPlayers=2; memset(&jkPlayer_playerInfos[2],0,sizeof(jkPlayer_playerInfos[2]));
    jkBot_ObserveWeapon(peer,NULL);
    assert(!Bot_RequestForce(self,pull,0.46f,1));
    bot.now+=2.0f;
    assert(Bot_RequestForce(self,pull,0.46f,1)); own->curPower=pull;
    bot.now+=0.5f; test_force_frame(); Bot_ForceTick(self,peer,0);
    bot.now+=2.5f;
    assert(!Bot_RequestForce(self,pull,0.46f,1)); /* unchanged weapon extends retry */
    jkBot_ObserveWeapon(peer,fists); /* late remote disarm then rearm */
    jkBot_ObserveWeapon(peer,&bryar);
    assert(Bot_RequestForce(self,pull,0.46f,1)); own->curPower=pull;
    bot.now+=0.5f; test_force_frame(); Bot_ForceTick(self,peer,0);
    peer->signature++; /* same slot, fresh identity */
    assert(Bot_RequestForce(self,pull,0.46f,1)); own->curPower=pull;
    peer->signature++; /* identity also changes during acquisition */
    bot.now+=0.5f; test_force_frame(); Bot_ForceTick(self,peer,0);
    assert(bot.forceCancel);
    own->curPower=SITHBIN_F_JUMP;
    test_force_frame(); Bot_ForceTick(self,peer,0);
    bot.now+=1; assert(Bot_RequestForce(self,pull,0.46f,1)); own->curPower=pull;
    bot.now+=0.5f; test_force_frame(); Bot_ForceTick(self,peer,0);
    peer->flags|=SITH_TF_DEAD; Bot_ObservePeers(self);
    peer->flags&=~SITH_TF_DEAD; /* stock can respawn using the same thing */
    assert(Bot_RequestForce(self,pull,0.46f,1)); own->curPower=pull;
    bot.now+=0.5f; test_force_frame(); Bot_ForceTick(self,peer,0);
    puts("PASS unchanged Pull results back off per opponent, reset on visible rearm, new identity or life");
    bot.fistsPeace=1; peer->playerInfo->rd_thing.model3=gun;
    own->aItems[pull].state=0; testInventoryTypes[pull].cog=NULL;
    puts("PASS competitive Pull permits Bryar and cancels on wrong marker, disarm or lost range");
    enum { WRONG_MARKER, NO_VICTIM, UNKNOWN_SYMBOL, MISSING_COG, WRONG_TYPE, REUSED_IDX, REUSED_NETID, REUSED_GUID, REUSED_SIGNATURE,
           OUT_OF_RANGE, LOST_LOS, PEACE_HOLD, TEAM_HOLD, DISABLED_HOLD, ACTIVE_PEACE, ACTIVE_DISABLED,
           ACTIVE_REUSED, MATCH };
    for (int scenario=WRONG_MARKER;scenario<=MATCH;scenario++) {
        marker.pName="victim"; marker.val.type=COG_TYPE_INT; marker.val.data[0]=peer->idx;
        testInventoryTypes[grip].cog=&cog;
        bot.now+=1; test_force_frame();
        assert(Bot_RequestForce(self,grip,0.46f,1)); own->curPower=grip;
        marker.val.data[0]=-1; bot.now+=0.2f; test_force_frame();
        if (scenario==WRONG_MARKER) {
            nav.waterExitUntil=bot.now+4;
            Bot_ContinueWaterExit(self,NULL);
            assert(nav.waterExitUntil==0 && bot.forceBin==grip);
        } else Bot_ForceTick(self,peer,0);
        assert(bot.keys[Bot_PowerKey(grip)] && !bot.keys[INPUT_FUNC_NEXTSKILL]);
        marker.val.data[0]=peer->idx;
        switch (scenario) {
            case WRONG_MARKER: marker.val.data[0]=peer->idx+1; break;
            case NO_VICTIM: marker.val.data[0]=-1; break;
            case UNKNOWN_SYMBOL: marker.pName=NULL; break;
            case MISSING_COG: testInventoryTypes[grip].cog=NULL; break;
            case WRONG_TYPE: marker.val.type=SITHCOG_VALUE_FLOAT; break;
            case REUSED_IDX: peer->idx++; marker.val.data[0]=peer->idx; break;
            case REUSED_NETID: jkPlayer_playerInfos[1].playerNetId++; break;
            case REUSED_GUID: peer->guid++; break;
            case REUSED_SIGNATURE: peer->signature++; break;
            case OUT_OF_RANGE: peer->position.y=1.1f; break;
            case LOST_LOS: testLOS=0; break;
            case PEACE_HOLD: peer->playerInfo->rd_thing.model3=fists; break;
            case TEAM_HOLD: sithNet_MultiModeFlags=MULTIMODEFLAG_TEAMS; break;
            case DISABLED_HOLD: bot.forceEnabled=0; break;
        }
        int originalMarker=marker.val.data[0];
        bot.now+=0.3f; test_force_frame();
        if (scenario==WRONG_MARKER) {
            nav.waterExitUntil=bot.now+4;
            Bot_ContinueWaterExit(self,NULL);
            assert(!nav.waterExitUntil && bot.forceCancel);
        } else Bot_ForceTick(self,peer,0);
        assert((int)marker.val.data[0]==originalMarker);
        if (scenario<ACTIVE_PEACE) {
            assert(bot.keys[Bot_PowerKey(grip)] && bot.keys[INPUT_FUNC_NEXTSKILL]);
            own->curPower=SITHBIN_F_JUMP; test_force_frame(); Bot_ForceTick(self,NULL,180);
            assert(!bot.keys[Bot_PowerKey(grip)] && bot.forceBin<0);
        } else {
            assert(!bot.keys[Bot_PowerKey(grip)] && !bot.keys[INPUT_FUNC_NEXTSKILL] && bot.forceBin<0);
            /* Fixture supplies the active bin that a successful stock release sets. */
            own->aItems[grip].state|=SITHINVENTORY_ITEM_ACTIVATED;
            own->aItems[SITHBIN_F_JUMP].state=SITHINVENTORY_ITEM_AVAILABLE;
            own->aItems[SITHBIN_F_JUMP].amount=4;
            assert(!Bot_RequestForce(self,SITHBIN_F_JUMP,0.1f,-1)); /* navigation entry */
            if (scenario==ACTIVE_PEACE) peer->playerInfo->rd_thing.model3=fists;
            if (scenario==ACTIVE_DISABLED) bot.forceEnabled=0;
            if (scenario==ACTIVE_REUSED) peer->signature++;
            own->curWeaponID=SITHBIN_STORMTROOPER_RIFLE;
            own->aItems[own->curWeaponID].state=SITHINVENTORY_ITEM_AVAILABLE;
            own->aItems[own->curWeaponID].amount=own->aItems[SITHBIN_ENERGY].amount=1;
            own->aItems[seeing].state=SITHINVENTORY_ITEM_AVAILABLE;
            test_force_frame(); Bot_Combat(self,peer);
            assert(bot.keys[INPUT_FUNC_NEXTSKILL]==(scenario!=MATCH));
            if (scenario==MATCH) assert(bot.keys[INPUT_FUNC_FIRE1] && !bot.keys[Bot_PowerKey(seeing)]);
            if (scenario==MATCH) {
                own->aItems[SITHBIN_BACTATANK].state=SITHINVENTORY_ITEM_AVAILABLE;
                own->aItems[SITHBIN_BACTATANK].amount=1;
                self->actorParams.health=55;
                test_force_frame(); Bot_ForceTick(self,peer,0);
                assert(bot.keys[Bot_PowerKey(SITHBIN_BACTATANK)] && !bot.keys[INPUT_FUNC_NEXTSKILL]);
                self->actorParams.health=100;
            }
            own->aItems[grip].state=SITHINVENTORY_ITEM_AVAILABLE;
            own->aItems[seeing].state=0;
        }
        peer->position.y=0.7f; testLOS=1; bot.forceEnabled=1;
        sithNet_MultiModeFlags=0; peer->playerInfo->rd_thing.model3=gun;
    }
    testInventoryTypes[grip].cog=NULL;
    bot.now+=2; assert(Bot_RequestForce(self,SITHBIN_F_JUMP,0.1f,-1));
    puts("PASS competitive Grip marker and generation checks, ordinary release/cancel, active weapon fire and Bacta");

    const char *legacy[]={"balanced","master"};
    for (unsigned i=0;i<sizeof(legacy)/sizeof(*legacy);i++) {
        assert(setenv("JK_BOT_FORCE_STYLE",legacy[i],1)==0);
        jkBot_Configure("Bot_Legacy","ky.3do"); bot.now=30;
        own->aItems[grip].state=own->aItems[absorb].state=0;
        own->aItems[seeing].state=SITHINVENTORY_ITEM_AVAILABLE;
        Bot_ForceTick(self,peer,0); assert(bot.forceBin<0); /* no proactive Seeing */
        own->aItems[SITHBIN_FORCEMANA].amount=0;
        assert(Bot_RequestForce(self,SITHBIN_F_PROTECTION,0.1f,-1));
        bot.now=30.2f; test_force_frame(); Bot_ForceTick(self,peer,0);
        own->aItems[SITHBIN_FORCEMANA].amount=400;
        bot.now=32.39f; assert(!Bot_RequestForce(self,seeing,0.1f,-1));
        bot.now=32.41f; assert(Bot_RequestForce(self,seeing,0.1f,-1));
    }
    assert(unsetenv("JK_BOT_FORCE_STYLE")==0);
    puts("PASS balanced and master sequencing, original cross-power interval and Protection threshold");
}

/* Force Pull on an item: aim, hold until the stock marker names the item,
   release, stand to catch; a wrong marker cancels through deselection. */
static void test_item_pull(SithThing *self)
{
    static SithWorld world; static SithThing items[3]; static SithSector dry;
    SithPlayer *own=self->actorParams.pPlayer;
    SithCogSymbol marker={0}; SithCogSymbolTable table={0}; sithCog cog={0};
    int pull=SITHBIN_F_PULL, key;
    flex_t least;
    memset(&dry,0,sizeof(dry)); memset(items,0,sizeof(items));
    assert(setenv("JK_BOT_FORCE_STYLE","competitive",1)==0);
    jkBot_Configure("Bot_Puller","ky.3do");
    assert(unsetenv("JK_BOT_FORCE_STYLE")==0);
    bot.joined=1; bot.now=50; bot.elite=1; jkPlayer_maxPlayers=0;
    flex_t saved=BT(ITEM_PULL); least=2.0f; BT(ITEM_PULL)=least; /* the default */
    /* The pull made standing still; pull_on_move is covered in test_bot_tactic_fixes.inc. */
    flex_t savedMove=BT(PULL_ON_MOVE); BT(PULL_ON_MOVE)=0;
    memset(own->aItems,0,sizeof(own->aItems));
    own->aItems[pull].amount=4; own->aItems[pull].state=SITHINVENTORY_ITEM_AVAILABLE;
    own->aItems[SITHBIN_F_JUMP].amount=4; own->aItems[SITHBIN_F_JUMP].state=SITHINVENTORY_ITEM_AVAILABLE;
    own->aItems[SITHBIN_FORCEMANA].amount=400; own->curPower=SITHBIN_F_JUMP;
    own->aItems[SITHBIN_POWER].amount=500; own->aItems[SITHBIN_POWER].state=SITHINVENTORY_ITEM_AVAILABLE;
    table.aSymbols=&marker; table.tableSize=table.numUsedSymbols=1; cog.pSymbolTable=&table;
    marker.pName="victim"; marker.val.type=COG_TYPE_INT; marker.val.data[0]=-1;
    testInventoryTypes[pull].cog=&cog;
    self->sector=&dry; self->position=(rdVector3){0,0,0}; self->attach_flags=SITH_ATTACH_SURFACE;
    self->actorParams.health=100; self->actorParams.headPYR=(rdVector3){0,0,0};
    bot.world=sithWorld_g_pCurrentWorld=&world; world.aThings=items; world.numThings=2; world.numThingsLoaded=3;
    const char *names[3]={"concrifle","powercell","concrifle"};
    for (int i=0;i<3;i++) {
        items[i].type=SITH_THING_ITEM; items[i].idx=i; items[i].guid=300+i; items[i].sector=&dry;
        strcpy(items[i].aName,names[i]);
    }
    items[0].position=(rdVector3){0,1.5f,0};   /* a missing rifle in reach, dead ahead */
    items[1].position=(rdVector3){0.5f,1.0f,0}; /* cells it is full of: not worth a cast */
    items[2].position=(rdVector3){0,4.0f,0};   /* out of reach at rank 4 */
    key=Bot_PowerKey(pull); assert(key>=0);
    /* Off in the legacy table. */
    BT(ITEM_PULL)=0; Bot_ForceTick(self,NULL,180); assert(!bot.pullItem && bot.forceBin<0);
    BT(ITEM_PULL)=least;
    /* A flag never; out of sight never. */
    items[0].itemParams.flags=SITH_ITEM_8; Bot_ForceTick(self,NULL,180); assert(!bot.pullItem);
    items[0].itemParams.flags=0; testLOS=0; bot.nextItemPull=0;
    Bot_ForceTick(self,NULL,180); assert(!bot.pullItem); testLOS=1; bot.nextItemPull=0;
    /* Chosen, then aimed and cast while standing still. */
    Bot_ForceTick(self,NULL,180); assert(bot.pullItem==1 && bot.pullPhase==1);
    bot.axes[INPUT_FUNC_FORWARD]=1; test_force_frame(); Bot_ForceTick(self,NULL,180);
    assert(bot.pullPhase==2 && bot.forceBin==pull && bot.keys[key] && bot.axes[INPUT_FUNC_FORWARD]==0);
    own->curPower=pull;
    /* Held until the marker names the item, then released. */
    bot.now+=0.3f; test_force_frame(); Bot_ForceTick(self,NULL,180); assert(bot.keys[key]);
    marker.val.data[0]=0;
    bot.now+=0.3f; test_force_frame(); Bot_ForceTick(self,NULL,180);
    assert(!bot.keys[key] && bot.forceBin<0 && bot.pullPhase==3 && bot.tele.itemPulls==1);
    /* Standing to catch it; its pickup ends the pull. */
    items[0].position=(rdVector3){0,0.4f,0}; /* in flight */
    bot.now+=0.1f; test_force_frame(); Bot_ForceTick(self,NULL,180); assert(bot.pullPhase==3);
    items[0].flags|=SITH_TF_DISABLED;
    bot.now+=0.1f; test_force_frame(); Bot_ForceTick(self,NULL,180);
    assert(!bot.pullItem && bot.tele.itemCaught==1);
    puts("PASS Force Pull draws an item worth the cast: aims, holds for the stock marker, releases and stands to catch it");
    /* A wrong marker after the hold: deselect instead of pulling something else. */
    items[0].flags=0; items[0].position=(rdVector3){0,1.5f,0}; own->curPower=SITHBIN_F_JUMP;
    marker.val.data[0]=-1; bot.now+=2; bot.nextItemPull=0; bot.pullItemLast=0;
    test_force_frame(); Bot_ForceTick(self,NULL,180); assert(bot.pullPhase==1);
    test_force_frame(); Bot_ForceTick(self,NULL,180); assert(bot.pullPhase==2); own->curPower=pull;
    marker.val.data[0]=1;
    bot.now+=1.0f; test_force_frame(); Bot_ForceTick(self,NULL,180);
    assert(bot.forceCancel && bot.keys[INPUT_FUNC_NEXTSKILL] && bot.tele.pullCancels==1);
    own->curPower=SITHBIN_F_JUMP; test_force_frame(); Bot_ForceTick(self,NULL,180);
    assert(!bot.pullItem && bot.forceBin<0 && !bot.keys[key]);
    /* That item rests ten seconds before another try. */
    bot.now+=2; bot.nextItemPull=0; test_force_frame(); Bot_ForceTick(self,NULL,180); assert(!bot.pullItem);
    bot.now+=9; bot.nextItemPull=0; test_force_frame(); Bot_ForceTick(self,NULL,180); assert(bot.pullItem==1);
    /* An enemy in the fight takes precedence while aiming. */
    SithThing enemy={0}; test_force_frame(); Bot_ForceTick(self,&enemy,0); assert(!bot.pullItem);
    marker.val.data[0]=-1; testInventoryTypes[pull].cog=NULL; own->curPower=SITHBIN_F_JUMP;
    bot.world=sithWorld_g_pCurrentWorld=NULL; self->attach_flags=0; BT(ITEM_PULL)=saved; BT(PULL_ON_MOVE)=savedMove;
    puts("PASS a wrong marker deselects, the item rests before a retry, and a fight takes precedence");
}

/* Absorb at rank four turns all Force damage (Grip among it) into mana, and
   costs 200: optional casts keep that much while it is down, and a Grip is
   answered with it before bacta. */
static void test_grip_answer(SithThing *self)
{
    SithPlayer *own=self->actorParams.pPlayer;
    int absorb=SITHBIN_F_ABSORB, pull=SITHBIN_F_PULL;
    assert(setenv("JK_BOT_FORCE_STYLE","competitive",1)==0);
    jkBot_Configure("Bot_Gripped","ky.3do");
    assert(unsetenv("JK_BOT_FORCE_STYLE")==0);
    bot.joined=1; bot.now=80; jkPlayer_maxPlayers=0;
    flex_t reserve=BT(ABSORB_RESERVE); BT(ABSORB_RESERVE)=1;
    memset(own->aItems,0,sizeof(own->aItems));
    own->aItems[absorb].amount=4; own->aItems[absorb].state=SITHINVENTORY_ITEM_AVAILABLE;
    own->aItems[pull].amount=4; own->aItems[pull].state=SITHINVENTORY_ITEM_AVAILABLE;
    own->aItems[SITHBIN_F_JUMP].amount=4; own->aItems[SITHBIN_F_JUMP].state=SITHINVENTORY_ITEM_AVAILABLE;
    own->aItems[SITHBIN_FORCEMANA].amount=210;
    assert(!Bot_ForceReady(self,pull,20) && "210 leaves less than Absorb's 200 after a pull");
    own->aItems[SITHBIN_FORCEMANA].amount=220; assert(Bot_ForceReady(self,pull,20));
    own->aItems[SITHBIN_FORCEMANA].amount=150; assert(Bot_ForceReady(self,SITHBIN_F_JUMP,20) && "jumps are not held back");
    own->aItems[absorb].state|=SITHINVENTORY_ITEM_ACTIVATED; assert(Bot_ForceReady(self,pull,20) && "Absorb already up");
    own->aItems[absorb].state=SITHINVENTORY_ITEM_AVAILABLE;
    BT(ABSORB_RESERVE)=0; assert(Bot_ForceReady(self,pull,20) && "legacy spends freely"); BT(ABSORB_RESERVE)=1;
    puts("PASS optional casts keep 200 mana for Absorb while it is down; jumps and the legacy table do not");
    /* Gripped and hurt, with bacta in hand: Absorb first. */
    own->aItems[SITHBIN_FORCEMANA].amount=250; self->actorParams.health=50;
    own->aItems[SITHBIN_BACTATANK].amount=1; own->aItems[SITHBIN_BACTATANK].state=SITHINVENTORY_ITEM_AVAILABLE;
    bot.grippedUntil=bot.now+0.8f; bot.nextForce=0; bot.forceBin=-1;
    test_force_frame(); Bot_ForceTick(self,NULL,180);
    assert(bot.forceBin==absorb && !bot.keys[Bot_PowerKey(SITHBIN_BACTATANK)]);
    /* Not gripped: bacta comes first as before. */
    bot.now+=1; test_force_frame(); Bot_ForceTick(self,NULL,180); bot.forceBin=-1; bot.grippedUntil=0; bot.nextForce=0;
    test_force_frame(); Bot_ForceTick(self,NULL,180);
    assert(bot.keys[Bot_PowerKey(SITHBIN_BACTATANK)] && bot.forceBin<0);
    puts("PASS a Grip is answered with Absorb before bacta");
    self->actorParams.health=100; BT(ABSORB_RESERVE)=reserve; bot.nextForce=0; bot.forceBin=-1;
    memset(own->aItems,0,sizeof(own->aItems));
}

static void test_bot_behavior(void)
{
    SithSector sector={0}; SithThing self={0},peer={0},shot={0};
    SithPlayer own={0}; jkPlayerInfo remote={0}; rdModel3 fists={0},gun={0},saber={0},bomb={0};
    strcpy(fists.filename,"fistg.3do"); strcpy(gun.filename,"strg.3do");
    strcpy(saber.filename,"sabg.3do"); strcpy(bomb.filename,"detg.3do");
    jkBot_Configure("Bot_Policy","ky.3do"); bot.joined=1; bot.now=10;
    assert(!bot.fistsPeace && "fists as peace is taken out for now");
    bot.fistsPeace=1; /* the peace logic is kept for when it comes back */
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
    assert(Bot_EnemyAllowed(&self,1)); /* Jump twinkles leave an ordinary target. */
    peer.actorParams.flags|=SITH_AF_INVISIBLE;
    assert(!Bot_EnemyAllowed(&self,1));
    own.aItems[SITHBIN_F_SEEING].state=SITHINVENTORY_ITEM_ACTIVATED;
    assert(Bot_EnemyAllowed(&self,1));
    own.aItems[SITHBIN_F_SEEING].state=0;
    bot.targetSlot=1; bot.targetGuid=(int)peer.guid; bot.nextScan=0;
    assert(Bot_UpdateTarget(&self)==NULL && bot.targetSlot==-1);
    peer.jkFlags=0; peer.actorParams.flags&=~SITH_AF_INVISIBLE; self.actorParams.flags=SITH_AF_BLIND;
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
    {   /* A settings file that still asks for fists-as-peace is read but not obeyed. */
        char path[]="/tmp/jk-bot-behaviorXXXXXX"; int fd=mkstemp(path); assert(fd>=0);
        FILE *w=fdopen(fd,"w"); assert(w);
        fputs("version=1\nsabers_only=0\nfists_peace=1\nforce_enabled=1\n",w); fclose(w);
        strcpy(bot.behaviorFile,path); bot.fistsPeace=1; bot.sabersOnly=1; bot.now=50;
        Bot_ReloadBehavior();
        assert(!bot.fistsPeace && !bot.sabersOnly && bot.forceEnabled);
        unlink(path); bot.behaviorFile[0]=0;
    }
    puts("PASS complete atomic behavior config and invalid/partial/duplicate rejection; fists_peace=1 is ignored");
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
    test_competitive_force(&self,&peer,&gun,&fists);
    test_item_pull(&self);
    test_grip_answer(&self);
    test_force_trace(&self);
    sithPlayer_g_pLocalPlayerThing=NULL;
}
