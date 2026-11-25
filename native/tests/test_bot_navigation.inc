/* Controlled map-goal tests; does not claim rendered traversal or CTF scores. */
static void test_initial_anchor_jump(void)
{
    SithWorld world={0}; SithSector sector={0}; SithThing self={0}; SithPlayer own={0};
    jkBot_Configure("Bot_InitialAnchor","ky.3do");
    /* This query fixture has no floors, which the standstill Force Jump model
       (fjump_standstill) needs to find a landing; it is tested on its own. */
    flex_t standstill=BT(FJUMP_STANDSTILL); BT(FJUMP_STANDSTILL)=0;
    corridorMode=fixtureMode=testSlopeActive=testBridgeActive=testC1Active=0;
    bot.world=&world; world.aSectors=&sector; world.numSectors=1; world.gravity=4;
    bot.now=5; bot.nextPlan=20; bot.goal=0; bot.nNodes=bot.routeCount=1;
    bot.route[0]=0; bot.nodes[0].item=-1; bot.nodes[0].sector=&sector;
    bot.nodes[0].pos=(rdVector3){0.40f,0,BOT_FOOT_HEIGHT+0.05f};
    self.position=(rdVector3){0,0,BOT_FOOT_HEIGHT}; self.sector=&sector;
    self.type=SITH_THING_PLAYER; self.actorParams.health=100; self.actorParams.pPlayer=&own;
    self.actorParams.maxRotVelocity=200; self.attach_flags=SITH_ATTACH_SURFACE;
    self.collideSize=self.moveSize=0.065f;
    self.orient.lvec=(rdVector3){1,0,0}; self.orient.rvec=(rdVector3){0,-1,0};
    nav.jumpVelocity=1.5f; nav.maxRunSpeed=1;
    /* The already grounded graph anchor is the nearest node, but there is
       no graph edge from the actual player position. This controlled query
       fixture rejects ground support while permitting the bounded jump arc. */
    assert(Bot_Nearest(&self)==0);
    BotNode takeoff=bot.nodes[0]; takeoff.pos=self.position;
    int drop=-1; flex_t duration;
    assert(!Bot_Walkable(&takeoff,&bot.nodes[0],&drop));
    assert(Bot_Jumpable(&takeoff,&bot.nodes[0],&duration));
    rdVector3 original=self.position;
    Bot_Navigate(&self);
    assert(bot.keys[INPUT_FUNC_JUMP] && nav.jumpUntil>bot.now);
    assert(bot.axes[INPUT_FUNC_FORWARD]>0.5f && Bot_Distance(self.position,original)==0);
    /* Once airborne the existing jump executor keeps normal forward input;
       it does not write a position, invent a graph node, or request Force. */
    self.attach_flags=0; bot.now+=0.10f; memset(bot.keys,0,sizeof(bot.keys));
    Bot_Navigate(&self);
    assert(!bot.keys[INPUT_FUNC_JUMP] && bot.axes[INPUT_FUNC_FORWARD]>0.5f && bot.nNodes==1);
    assert(bot.forceBin==-1 && !nav.forceJumpPending);
    nav.jumpUntil=0; bot.nextJump=0; self.attach_flags=SITH_ATTACH_SURFACE;
    bot.nodes[0].pos.x=.75f; memset(bot.keys,0,sizeof(bot.keys));
    Bot_Navigate(&self);
    assert(!bot.keys[INPUT_FUNC_JUMP] && !nav.jumpUntil && !nav.forceJumpPending);
    bot.nodes[0].pos.x=.40f; bot.nodes[0].pos.z=BOT_FOOT_HEIGHT+.22f;
    Bot_Navigate(&self);
    assert(!bot.keys[INPUT_FUNC_JUMP] && !nav.jumpUntil);
    own.aItems[SITHBIN_F_JUMP].state=SITHINVENTORY_ITEM_AVAILABLE;
    own.aItems[SITHBIN_F_JUMP].amount=3; own.aItems[SITHBIN_FORCEMANA].amount=19;
    Bot_Navigate(&self); assert(!nav.forceJumpPending);
    own.aItems[SITHBIN_FORCEMANA].amount=20;
    Bot_Navigate(&self);
    int jumpKey=Bot_PowerKey(SITHBIN_F_JUMP);
    assert(nav.forceJumpPending && bot.keys[jumpKey] && !bot.keys[INPUT_FUNC_JUMP]);
    assert(Bot_Distance(self.position,original)==0 && own.aItems[SITHBIN_FORCEMANA].amount==20);
    /* A shove before release ends the dry route and drops the normal key.
       Inventory scripts own any release effects, mana, and reactivation. */
    self.attach_flags=0; bot.now+=0.1f; memset(bot.keys,0,sizeof(bot.keys));
    Bot_Navigate(&self); Bot_ForceTick(&self,NULL,180.0f);
    assert(!nav.forceJumpPending && !nav.jumpUntil && bot.forceBin==-1 && !bot.keys[jumpKey]);
    for (int rank=3;rank<=4;rank++) {
        self.attach_flags=SITH_ATTACH_SURFACE; own.aItems[SITHBIN_F_JUMP].amount=rank;
        bot.now+=3; flex_t hold=rank*.35f;
        assert(Bot_RequestForce(&self,SITHBIN_F_JUMP,hold,-1));
        assert(fabsf(bot.forceUntil-(bot.now+hold))<0.001f);
        bot.now=bot.forceUntil-.01f; memset(bot.keys,0,sizeof(bot.keys));
        Bot_ForceTick(&self,NULL,180.0f); assert(bot.keys[jumpKey]);
        bot.now=bot.forceUntil+.01f; memset(bot.keys,0,sizeof(bot.keys));
        Bot_ForceTick(&self,NULL,180.0f); assert(!bot.keys[jumpKey] && bot.forceBin==-1);
    }
    assert(queryDepth==0); BT(FJUMP_STANDSTILL)=standstill;
    jkBot_Configure("Bot_Reset","ky.3do");
    puts("PASS dry initial anchor prefers ordinary jump, checks Force availability, releases on lost support and holds full rank 3/4 charge");
}

static void test_static_bridge_route(void)
{
    SithWorld world={0}; SithThing self={0}; SithPlayer player={0};
    jkBot_Configure("Bot_StaticBridge","ky.3do");
    memset(testBridgeSectors,0,sizeof(testBridgeSectors));
    memset(testBridgeThings,0,sizeof(testBridgeThings));
    world.aSectors=testBridgeSectors; world.numSectors=2; world.gravity=4;
    bot.world=&world; bot.now=1; testBridgeActive=1; corridorMode=fixtureMode=0;
    for (int i=0;i<2;i++) {
        testBridgeThings[i].type=SITH_THING_COG; testBridgeThings[i].collide=SITH_COLLIDE_FACE;
        testBridgeThings[i].sector=&testBridgeSectors[i]; testBridgeThings[i].moveType=SITH_MT_PATH;
    }
    self.position=(rdVector3){39.475052f,8.31f,28.598123f+BOT_FOOT_HEIGHT};
    self.sector=&testBridgeSectors[0]; self.actorParams.pPlayer=&player; self.actorParams.health=100;
    rdVector3 pickup={39.473076f,5.660943f,28.599879f+BOT_FOOT_HEIGHT};
    int start=Bot_AddNode(self.position,self.sector,-1,0.5f);
    int finish=Bot_AddNode(pickup,&testBridgeSectors[1],-1,0.5f);
    assert(start==0 && finish==1);
    rdVector3 sample=Bot_Mix(bot.nodes[start].pos,bot.nodes[finish].pos,1.0f/13.0f);
    sample.z+=0.02f;
    assert(sample.y>testBridgeBoundary && sample.y<8.120105f);
    /* Reproduce the original query's missing support, despite continuous
       physical bridge support at the actual walk sampling location. */
    rdVector3 down={0,0,-1}, floor; SithSector *floorSector=NULL;
    sithCollision_SearchForCollisions(self.sector,NULL,&sample,&down,0.52f,0,RAYCAST_200|RAYCAST_2000);
    assert(sithCollision_PopStack()==NULL); sithCollision_DecreaseStackLevel();
    assert(Bot_Floor(sample,self.sector,0.52f,&floor,&floorSector));
    assert(floorSector==self.sector && floorSector!=testBridgeThings[1].sector);
    int drop=-1;
    assert(Bot_Walkable(&bot.nodes[start],&bot.nodes[finish],&drop) && !drop);
    SithThing *previousLocal=sithPlayer_g_pLocalPlayerThing; sithPlayer_g_pLocalPlayerThing=NULL;
    while (!bot.graphDone) Bot_BuildGraphStep();
    sithPlayer_g_pLocalPlayerThing=previousLocal;
    flex_t distance[BOT_NODES]; int parent[BOT_NODES];
    Bot_PathDistances(&self,start,distance,parent);
    assert(distance[finish]<1e19f && parent[finish]==start);
    testBridgeThings[1].trackParams.loadedFrames=2;
    assert(!Bot_Floor(sample,self.sector,0.52f,&floor,&floorSector));
    assert(!Bot_Walkable(&bot.nodes[start],&bot.nodes[finish],&drop));
    testBridgeThings[1].trackParams.loadedFrames=0;
    testBridgeThings[1].flags=SITH_TF_DISABLED;
    assert(!Bot_Floor(sample,self.sector,0.52f,&floor,&floorSector));
    assert(!Bot_Walkable(&bot.nodes[start],&bot.nodes[finish],&drop));
    assert(queryDepth==0); testBridgeActive=0;
    jkBot_Configure("Bot_Reset","ky.3do");
    puts("PASS adjacent-sector static mesh overhang supports real graph route; moving/missing bridge rejected");
}

static void test_c1_portal_route(void)
{
    SithWorld world={0}; SithThing self={0}; SithPlayer player={0};
    SithSurface portal={0}; SithSurfaceAdjoin adjoin={0};
    rdVector3 vertices[4]={{-0.7f,-7.599999f,0.9f},{-0.5f,-7.599999f,0.9f},{-0.5f,-7.599999f,1.3f},{-0.7f,-7.599999f,1.3f}};
    int32_t indices[4]={0,1,2,3};
    jkBot_Configure("Bot_C1_Corridor","ky.3do");
    memset(testC1Sectors,0,sizeof(testC1Sectors));
    world.aSectors=testC1Sectors; world.numSectors=4; world.aVertices=vertices; world.numVertices=4;
    world.surfaces=&portal; world.numSurfaces=1; world.gravity=4;
    bot.world=&world; bot.now=1; testC1Active=1; corridorMode=fixtureMode=0;
    nav.ctf=1; nav.mark[0]=3; nav.mark[1]=0; nav.requestedTeam=1;
    portal.pSector=&testC1Sectors[3]; portal.pAdjoin=&adjoin;
    portal.surfaceInfo.face.normal=(rdVector3){0,-1,0};
    portal.surfaceInfo.face.numVertices=4; portal.surfaceInfo.face.vertexPosIdx=indices;
    adjoin.flags=SITHSURF_ADJOIN_ALLOW_MOVEMENT; adjoin.sector=&testC1Sectors[2];
    self.position=(rdVector3){-0.6f,-6.5f,0.9f+BOT_FOOT_HEIGHT};
    self.sector=&testC1Sectors[0]; self.actorParams.pPlayer=&player; self.actorParams.health=100;
    int start=Bot_AddRawNode(self.position,self.sector,-1); assert(start==0);
    /* The original .42 offset has support and a clear crossing, but its
       anchor sphere straddles the lobby's next sector plane. */
    rdVector3 rejected={-0.6f,vertices[0].y+0.42f,0.9f+BOT_FOOT_HEIGHT};
    assert(Bot_AddRawNode(rejected,self.sector,-1)==-1);
    Bot_AddTeamEntries(); assert(nav.entryCount==1);
    int entry=nav.entries[0].node;
    assert(bot.nodes[entry].sector==&testC1Sectors[2]);
    assert(fabsf(bot.nodes[entry].pos.y+7.36f)<0.001f);
    SithThing *previousLocal=sithPlayer_g_pLocalPlayerThing; sithPlayer_g_pLocalPlayerThing=NULL;
    while (!bot.graphDone) Bot_BuildGraphStep();
    sithPlayer_g_pLocalPlayerThing=previousLocal;
    flex_t distance[BOT_NODES]; int parent[BOT_NODES];
    Bot_PathDistances(&self,start,distance,parent);
    assert(distance[entry]<1e19f && parent[entry]==start);
    Bot_UpdateObjective(&self);
    assert(Bot_ObjectiveNode(&self,distance)==entry);
    bot.nodes[start].nEdges=0;
    Bot_PathDistances(&self,start,distance,parent);
    assert(Bot_ObjectiveNode(&self,distance)==-1);
    assert(queryDepth==0); testC1Active=0;
    jkBot_Configure("Bot_Reset","ky.3do");
    puts("PASS C1 boundary anchor fallback has a collision-checked lobby route and rejects disconnected entry");
}

static void test_bot_pickup_preferences(void)
{
    jkBot_Configure("Bot_Supply","ky.3do");
    SithSector sector={0}; SithWorld world={0}; SithThing self={0}, racks[2]={{0}}; SithPlayer own={0};
    self.type=SITH_THING_PLAYER; self.sector=&sector; self.actorParams.pPlayer=&own; self.actorParams.health=100;
    world.aThings=racks; world.numThings=1; world.numThingsLoaded=2; bot.world=&world;
    bot.now=20; bot.nNodes=3; bot.graphDone=1; bot.sabersOnly=0; bot.elite=0;
    for (int i=0;i<2;i++) { racks[i].type=SITH_THING_ITEM; racks[i].sector=&sector; }
    /* A loaded bowcaster in hand: armed, so the values below are the plain
       ones (resupply raises every real gun to 12 for a bot out of shots). */
    own.aItems[SITHBIN_TUSKEN_PROD].state=SITHINVENTORY_ITEM_AVAILABLE;
    own.aItems[SITHBIN_TUSKEN_PROD].amount=1; own.aItems[SITHBIN_POWER].amount=40;
    strcpy(racks[0].aName,"railgun"); strcpy(racks[1].aName,"concrifle");
    assert(Bot_ItemValue(&self,0)==8 && Bot_ItemValue(&self,1)==8);
    bot.elite=1;
    assert(Bot_ItemValue(&self,0)==12 && Bot_ItemValue(&self,1)==18);
    strcpy(racks[0].aName,"repeatergun"); assert(Bot_ItemValue(&self,0)==10);
    strcpy(racks[0].aName,"strifle"); assert(Bot_ItemValue(&self,0)==8);
    strcpy(racks[0].aName,"railgun");
    bot.nodes[0]=(BotNode){.sector=&sector,.item=-1};
    bot.nodes[1]=(BotNode){.pos={1,0,0},.sector=&sector,.item=0};
    bot.nodes[2]=(BotNode){.pos={0,1,0},.sector=&sector,.item=1};
    bot.nodes[0].edges[0]=(BotEdge){1,1,BOT_ROUTE_WALK};
    bot.nodes[0].edges[1]=(BotEdge){2,5,BOT_ROUTE_WALK}; bot.nodes[0].nEdges=2;
    unsigned char strategy[28]={0}; strategy[8]=CP_RESOURCE;
    assert(Companion_SetPolicy(&self,strategy,100)==CP_OK); Bot_Plan(&self);
    assert(bot.goal==1 && bot.routeCount==1 && bot.route[0]==1);
    strategy[9]=SITHBIN_CONCUSSION_RIFLE;
    assert(Companion_SetPolicy(&self,strategy,100)==CP_OK); Bot_Plan(&self);
    assert(bot.goal==2 && bot.routeCount==1 && bot.route[0]==2 && !own.aItems[SITHBIN_CONCUSSION_RIFLE].amount);
    bot.nodes[0].nEdges=1; bot.goal=-1; Bot_Plan(&self); assert(bot.goal==1);
    self.actorParams.health=25; strcpy(racks[0].aName,"healthpack");
    assert(Bot_ItemValue(&self,0)>Bot_ItemValue(&self,1)); self.actorParams.health=100;
    bot.sabersOnly=1; assert(Bot_ItemValue(&self,1)==0); bot.sabersOnly=0;
    own.aItems[SITHBIN_CONCUSSION_RIFLE].state=SITHINVENTORY_ITEM_AVAILABLE;
    own.aItems[SITHBIN_CONCUSSION_RIFLE].amount=1; own.aItems[SITHBIN_POWER].amount=500;
    assert(Bot_ItemValue(&self,1)==0); own.aItems[SITHBIN_CONCUSSION_RIFLE].amount=0;
    racks[1].flags=SITH_TF_DISABLED; racks[1].itemParams.secRespawnInterval=30;
    assert(Bot_ItemValue(&self,1)==0); bot.now+=28;
    assert(Bot_ItemValue(&self,1)>0 && Bot_ItemValue(&self,1)<2);
    racks[1].flags=SITH_TF_DESTROYED; assert(Bot_ItemValue(&self,1)==0);
    puts("PASS elite supply priorities and legal companion preference alter reachable routes; health, saber, ammo and absence guards");
}

static void test_dropped_pack_contents(void)
{
    jkBot_Configure("Bot_Pack","ky.3do");
    SithSector sector={0}; SithPlayer own={0};
    SithThing self={.type=SITH_THING_PLAYER,.sector=&sector};
    self.actorParams.pPlayer=&own;
    SithThing pack={.type=SITH_THING_ITEM,.guid=421,.signature=17,.sector=&sector};
    strcpy(pack.aName,"+backpack"); pack.itemParams.flags=SITH_ITEM_BACKPACK;
    SithWorld world={.aThings=&pack,.numThings=0,.numThingsLoaded=1};
    bot.world=&world;
    own.aItems[SITHBIN_CONCUSSION_RIFLE].state=SITHINVENTORY_ITEM_AVAILABLE;
    own.aItems[SITHBIN_RAIL_DETONATOR].state=SITHINVENTORY_ITEM_AVAILABLE;
    int cap=(int)(sizeof(pack.itemParams.contents)/sizeof(pack.itemParams.contents[0]));
    pack.itemParams.numBins=cap;
    pack.itemParams.contents[0]=(SithBackpackItem){.binIdx=SITHBIN_CONCUSSION_RIFLE,.value=1};
    pack.itemParams.contents[cap-1]=(SithBackpackItem){.binIdx=SITHBIN_POWER,.value=8};
    assert(Bot_ItemValue(&self,0)==18 && own.aItems[SITHBIN_CONCUSSION_RIFLE].amount==0);
    pack.itemParams.contents[cap-1].value=7; assert(!Bot_PackValue(&self,&pack));
    own.aItems[SITHBIN_POWER].amount=1; assert(Bot_PackValue(&self,&pack)==18);
    pack.itemParams.numBins=cap+1; assert(!Bot_PackValue(&self,&pack));
    pack.itemParams.numBins=-1; assert(!Bot_PackValue(&self,&pack));
    pack.itemParams.numBins=1;pack.itemParams.contents[0]=(SithBackpackItem){.binIdx=SITHBIN_RAILCHARGES,.value=1};
    assert(!Bot_PackValue(&self,&pack)); own.aItems[SITHBIN_RAIL_DETONATOR].amount=1;
    assert(Bot_PackValue(&self,&pack)==12); own.aItems[SITHBIN_RAILCHARGES].amount=30;
    assert(!Bot_PackValue(&self,&pack)); own.aItems[SITHBIN_RAILCHARGES].amount=0;
    pack.itemParams.contents[0].value=NAN; assert(!Bot_PackValue(&self,&pack));
    pack.itemParams.contents[0].binIdx=SITHBIN_THERMAL_DETONATOR;
    pack.itemParams.contents[0].value=4; assert(!Bot_PackValue(&self,&pack));
    pack.itemParams.contents[0].binIdx=-1; assert(!Bot_PackValue(&self,&pack));
    pack.itemParams.contents[0].binIdx=SITHBIN_RAILCHARGES;
    BotNode contact={0}; pack.flags=SITH_TF_DESTROYED;
    assert(!Bot_PackValue(&self,&pack) && !Bot_PackContact(&self,&pack,&contact)); pack.flags=SITH_TF_DISABLED;
    assert(!Bot_PackValue(&self,&pack)); pack.flags=0;
    nav.itemGuid[0]=pack.guid; pack.guid++; pack.signature++;
    assert(!Bot_ItemValue(&self,0) && Bot_PackValue(&self,&pack)==12);
    bot.sabersOnly=1; assert(!Bot_PackValue(&self,&pack));
    puts("PASS dropped pack valuation uses bounded synced entries, ownership and combined ammo; expired, empty, reused and unusable contents");
}

static void test_bot_navigation(void)
{
    test_bot_pickup_preferences();
    test_dropped_pack_contents();
    SithSector sectors[2]={{0}};
    SithWorld world={0}; SithThing self={0}, items[4]={{0}}, templates[4]={{0}};
    SithPlayer own={0}; rdModel3 model={0};
    jkBot_Configure("Bot_Navigation","ky.3do"); bot.now=10;
    corridorMode=0; corridorSector=&sectors[0];
    self.sector=&sectors[0]; self.type=SITH_THING_PLAYER; self.actorParams.pPlayer=&own;
    self.actorParams.health=100; self.actorParams.jumpSpeed=1.5f; self.physicsParams.maxVelocity=1;
    world.aSectors=sectors; world.numSectors=2; world.gravity=4;
    world.aThings=items; world.numThings=3; world.numThingsLoaded=4;
    bot.world=&world;
    for (int i=0;i<4;i++) { items[i].idx=(uint32_t)i; items[i].guid=100u+(uint32_t)i;
        items[i].type=SITH_THING_ITEM; items[i].sector=&sectors[0]; items[i].pTemplate=&templates[i]; }
    const char *names[]={"energycell","healthpack","manaboost","ctf_goldflag"};
    for (int i=0;i<4;i++) strcpy(templates[i].aName,names[i]);
    assert(Bot_ThingCount()==4 && Bot_NavThing(3)==&items[3] && !Bot_NavThing(4));
    strcpy(templates[3].aName,"healthpack"); self.actorParams.health=25;
    assert(Bot_ItemValue(&self,3)>=10 && Bot_ItemValue(&self,4)==0);
    world.numThings=100; assert(Bot_ThingCount()==4 && !Bot_NavThing(4));
    world.numThings=-1; assert(Bot_ThingCount()==0 && !Bot_NavThing(0));
    world.numThings=0; assert(Bot_ThingCount()==1 && Bot_NavThing(0)==&items[0]);
    world.numThingsLoaded=0; assert(Bot_ThingCount()==0 && !Bot_NavThing(0));
    world.numThings=3; world.numThingsLoaded=4; self.actorParams.health=100;
    strcpy(templates[3].aName,names[3]);
    puts("PASS highest-active thing slot is included and bounded by allocation capacity");
    bot.sabersOnly=0;
    assert(Bot_ItemValue(&self,0)>0);
    own.aItems[SITHBIN_ENERGY].amount=500; assert(Bot_ItemValue(&self,0)==0);
    own.aItems[SITHBIN_ENERGY].amount=0; bot.sabersOnly=1; assert(Bot_ItemValue(&self,0)==0);
    bot.sabersOnly=0; assert(Bot_ItemValue(&self,1)==0);
    self.actorParams.health=25; assert(Bot_ItemValue(&self,1)>=10);
    bot.forceEnabled=1; assert(Bot_ItemValue(&self,2)==0);
    own.aItems[SITHBIN_JEDI_RANK].amount=4; own.aItems[SITHBIN_FORCEMANA].amount=20;
    assert(Bot_ItemValue(&self,2)>=5); bot.forceEnabled=0; assert(Bot_ItemValue(&self,2)==0);
    assert(Bot_ItemValue(&self,3)==0);
    strcpy(templates[0].aName,"m5railgun"); strcpy(model.filename,"rldp.3do"); items[0].renderData.model3=&model;
    assert(Bot_ItemValue(&self,0)>=7); bot.sabersOnly=1; assert(Bot_ItemValue(&self,0)==0); bot.sabersOnly=0;
    /* Thermals and charges: never collected under the legacy table; a few
       to throw and lay with thermals and mines on. */
    flex_t thermals=BT(THERMALS), mines=BT(MINES); BT(THERMALS)=BT(MINES)=0;
    strcpy(templates[0].aName,"detonator"); assert(Bot_ItemValue(&self,0)==0);
    strcpy(templates[0].aName,"seqcharge"); assert(Bot_ItemValue(&self,0)==0);
    BT(THERMALS)=BT(MINES)=1;
    assert(Bot_ItemValue(&self,0)==2.5f);
    strcpy(templates[0].aName,"detonator"); assert(Bot_ItemValue(&self,0)==2.0f);
    own.aItems[SITHBIN_THERMAL_DETONATOR].amount=4; assert(Bot_ItemValue(&self,0)==0);
    own.aItems[SITHBIN_THERMAL_DETONATOR].amount=0; BT(THERMALS)=thermals; BT(MINES)=mines;
    strcpy(templates[0].aName,"seqcharge");
    puts("PASS stock pickup need scoring, saber-only/Force gates and inherited model aliases");
    items[1].flags=SITH_TF_DISABLED; items[1].itemParams.secRespawnInterval=30;
    assert(Bot_ItemValue(&self,1)==0); bot.now=37;
    flex_t anticipated=Bot_ItemValue(&self,1); assert(anticipated>0 && anticipated<3);
    items[1].flags=0; assert(Bot_ItemValue(&self,1)>anticipated);
    nav.itemGuid[1]=items[1].guid; items[1].guid++; assert(Bot_ItemValue(&self,1)==0);
    puts("PASS pickup respawn estimate remains bounded and rejects recycled thing identity");
    jkBot_Configure("Bot_Navigation","ky.3do"); bot.world=&world; bot.now=1; bot.nNodes=4;
    for (int i=0;i<4;i++) { bot.nodes[i].sector=&sectors[0]; bot.nodes[i].item=-1; }
    bot.nodes[0].edges[0]=(BotEdge){1,1,BOT_ROUTE_WALK};
    bot.nodes[0].edges[1]=(BotEdge){2,5,BOT_ROUTE_WALK}; bot.nodes[0].nEdges=2;
    bot.nodes[1].edges[0]=(BotEdge){2,1,BOT_ROUTE_WALK};
    bot.nodes[1].edges[1]=(BotEdge){3,1,BOT_ROUTE_FORCEJUMP}; bot.nodes[1].nEdges=2;
    flex_t distances[BOT_NODES]; int parents[BOT_NODES];
    Bot_PathDistances(&self,0,distances,parents);
    assert(fabsf(distances[2]-2)<0.001f && parents[2]==1 && distances[3]>1e19f);
    bot.forceEnabled=1; own.aItems[SITHBIN_F_JUMP].amount=1; own.aItems[SITHBIN_FORCEMANA].amount=20;
    Bot_PathDistances(&self,0,distances,parents); assert(fabsf(distances[3]-2)<0.001f);
    own.aItems[SITHBIN_FORCEMANA].amount=19; Bot_PathDistances(&self,0,distances,parents); assert(distances[3]>1e19f);
    bot.nodes[1].edges[1].drop=BOT_ROUTE_DROP; self.actorParams.health=20;
    Bot_PathDistances(&self,0,distances,parents); assert(distances[3]>1e19f);
    self.actorParams.health=100; Bot_PathDistances(&self,0,distances,parents); assert(distances[3]<1e19f);
    puts("PASS shortest routes, directed low-health drops and legal Force-jump resource gate");
    nav.jumpVelocity=1.5f; nav.maxRunSpeed=1; nav.forceJumpKnown=1;
    /* The running-arc Force Jump model; test_fix_force_jump covers the
       standstill one (fjump_standstill), which refuses these legs. */
    flex_t standstill=BT(FJUMP_STANDSTILL); BT(FJUMP_STANDSTILL)=0;
    BotNode a={0},b={0}; a.sector=b.sector=&sectors[0]; b.pos=(rdVector3){0.4f,0,0};
    flex_t duration;
    assert(Bot_Jumpable(&a,&b,&duration) && duration>0.7f && duration<0.8f);
    b.pos.x=2; assert(!Bot_Jumpable(&a,&b,&duration));
    b.pos=(rdVector3){0.5f,0,0.5f}; assert(Bot_ForceJumpable(&a,&b,&duration));
    nav.forceJumpKnown=0; assert(!Bot_ForceJumpable(&a,&b,&duration)); nav.forceJumpKnown=1;
    flex_t hold;
    b.pos=(rdVector3){0.6f,0,1.05f};
    assert(!Bot_ForceJumpProfile(&a,&b,1,&duration,&hold));
    assert(Bot_ForceJumpProfile(&a,&b,3,&duration,&hold) && fabsf(hold-0.75f)<0.001f);
    b.pos.z=1.5f; assert(!Bot_ForceJumpProfile(&a,&b,4,&duration,&hold));
    corridorMode=1; corridorCeiling=-0.05f; a.pos=(rdVector3){-2,-1.85f,-0.129886f};
    b.pos=(rdVector3){-2.4f,-1.85f,-0.129886f};
    assert(!Bot_Jumpable(&a,&b,&duration) && !Bot_ForceJumpable(&a,&b,&duration));
    assert(!Bot_ForceJumpProfile(&a,&b,3,&duration,&hold));
    assert(queryDepth==0); corridorMode=0; BT(FJUMP_STANDSTILL)=standstill;
    puts("PASS bounded normal/Force jump arcs and real low-ceiling rejection");
    jkBot_Configure("Bot_CTF","ky.3do"); bot.world=&world; bot.now=5;
    memset(jkPlayer_playerInfos,0,sizeof(jkPlayer_playerInfos)); jkPlayer_maxPlayers=3;
    SithThing enemy={0}, ally={0}; enemy.type=ally.type=SITH_THING_PLAYER;
    enemy.sector=ally.sector=&sectors[0]; enemy.position=(rdVector3){2,0,0}; ally.position=(rdVector3){3,0,0};
    self.actorParams.pPlayer=&jkPlayer_playerInfos[0]; self.actorParams.health=100;
    for (int i=0;i<3;i++) { jkPlayer_playerInfos[i].flags=1; jkPlayer_playerInfos[i].playerNetId=10+i*10; }
    jkPlayer_playerInfos[0].pLocalPlayer=&self; jkPlayer_playerInfos[0].teamNum=1;
    jkPlayer_playerInfos[1].pLocalPlayer=&enemy; jkPlayer_playerInfos[1].teamNum=2;
    jkPlayer_playerInfos[2].pLocalPlayer=&ally; jkPlayer_playerInfos[2].teamNum=1;
    nav.ctf=1; nav.flag[0]=0; nav.flag[1]=1; nav.base[0]=2; nav.base[1]=3;
    nav.mark[0]=0; nav.mark[1]=1; nav.requestedTeam=2;
    for (int i=0;i<4;i++) { items[i].flags=0; items[i].attach_flags=0; items[i].attachedThing=NULL; }
    items[0].position=items[2].position=(rdVector3){0,0,0}; items[1].position=items[3].position=(rdVector3){5,0,0};
    Bot_UpdateObjective(&self); assert(nav.objective==BOT_OBJECTIVE_CAPTURE);
    assert(!Bot_ObjectiveCarrier(NULL));
    jkPlayer_playerInfos[0].playerNetId=40;
    Bot_UpdateObjective(&self); assert(nav.objective==BOT_OBJECTIVE_DEFEND);
    jkPlayer_playerInfos[0].playerNetId=10;
    items[1].attach_flags=SITH_ATTACH_NOMOVE; items[1].attachedThing=&self;
    Bot_UpdateObjective(&self); assert(nav.objective==BOT_OBJECTIVE_RETURN && Bot_ObjectiveUrgent(&self));
    assert(Bot_ObjectiveCarrier(&self));
    /* Remote inventory amounts are irrelevant; actual flag attachment wins. */
    jkPlayer_playerInfos[0].aItems[82].amount=0;
    Bot_UpdateObjective(&self); assert(nav.objective==BOT_OBJECTIVE_RETURN);
    items[0].position.x=1; Bot_UpdateObjective(&self); assert(nav.objective==BOT_OBJECTIVE_RECOVER);
    items[1].attach_flags=0; items[1].attachedThing=NULL;
    items[0].attach_flags=SITH_ATTACH_NOMOVE; items[0].attachedThing=&enemy;
    Bot_UpdateObjective(&self); assert(nav.objective==BOT_OBJECTIVE_INTERCEPT);
    items[0].attach_flags=0; items[0].attachedThing=NULL; items[0].position.x=0;
    items[1].attach_flags=SITH_ATTACH_NOMOVE; items[1].attachedThing=&ally;
    Bot_UpdateObjective(&self); assert(nav.objective==BOT_OBJECTIVE_ESCORT);
    jkPlayer_playerInfos[0].teamNum=0;
    Bot_UpdateObjective(&self); assert(nav.objective==BOT_OBJECTIVE_JOIN && nav.objectiveSector==&sectors[1]);
    assert(Bot_ObjectiveUrgent(&self));
    /* A stale pointer without an active roster carrier cannot claim possession. */
    jkPlayer_playerInfos[2].flags=0; assert(Bot_FlagCarrier(2)==NULL);
    puts("PASS CTF corridor selection, capture/return/recover/escort/intercept and synchronized possession");
    /* Stock C1 has a vertical entry above a deep shaft; C2/C3 use a sloping
       entry plane. Cross that entrance instead of seeking the shaft floor. */
    rdVector3 portalVertices[4]={{-0.1f,0,0.9f},{0.1f,0,0.9f},{0.1f,0,1.3f},{-0.1f,0,1.3f}};
    int32_t portalIndices[4]={0,1,2,3}; SithSurface portal={0};
    world.aVertices=portalVertices; world.numVertices=4;
    portal.pSector=&sectors[1]; portal.surfaceInfo.face.numVertices=4;
    portal.surfaceInfo.face.vertexPosIdx=portalIndices; portal.surfaceInfo.face.normal=(rdVector3){0,-1,0};
    rdVector3 approach={0,0.42f,1.020114f},inside;
    assert(Bot_CtfPortalPoints(&portal,approach,&inside));
    assert(fabsf(inside.y+0.12f)<0.001f && fabsf(inside.z-approach.z)<0.001f);
    assert(!Bot_CtfPortalPoints(&portal,(rdVector3){0,-0.2f,approach.z},&inside));
    portal.surfaceInfo.face.normal=(rdVector3){0,0,1};
    assert(!Bot_CtfPortalPoints(&portal,approach,&inside));
    portal.surfaceInfo.face.normal=(rdVector3){0,-0.5547f,-0.83205f};
    portalVertices[0]=(rdVector3){-0.15f,0.3f,0.9f}; portalVertices[1]=(rdVector3){0.15f,0.3f,0.9f};
    portalVertices[2]=(rdVector3){0.15f,-0.3f,1.3f}; portalVertices[3]=(rdVector3){-0.15f,-0.3f,1.3f};
    assert(Bot_CtfPortalPoints(&portal,approach,&inside));
    bot.nNodes=2; bot.nodes[0].pos=approach; bot.nodes[0].sector=&sectors[0]; bot.nodes[0].avoidUntil=0;
    bot.nodes[1].pos=(rdVector3){0,-2,-4}; bot.nodes[1].sector=&sectors[1];
    nav.entryCount=1; nav.entries[0]=(BotTeamEntry){1,0,inside,&sectors[1]};
    nav.requestedTeam=1; nav.objective=BOT_OBJECTIVE_JOIN; nav.objectivePos=bot.nodes[1].pos;
    distances[0]=0.1f; distances[1]=1e20f;
    assert(Bot_ObjectiveNode(&self,distances)==0 && nav.selectedEntry==0);
    assert(nav.objectivePos.z>1.0f);
    self.position=approach; self.sector=&sectors[0]; self.collideSize=0.065f;
    self.orient.lvec=(rdVector3){0,-1,0}; self.orient.rvec=(rdVector3){1,0,0};
    bot.now=10; memset(bot.axes,0,sizeof(bot.axes));
    assert(Bot_JoinMove(&self) && nav.crossingEntry==1 && bot.axes[INPUT_FUNC_FORWARD]>0);
    assert(Bot_Distance(self.position,approach)==0 && self.actorParams.pPlayer->teamNum==0);
    self.sector=&sectors[1];
    assert(Bot_JoinMove(&self) && bot.axes[INPUT_FUNC_FORWARD]==0 && bot.axes[INPUT_FUNC_SLIDE]==0);
    self.actorParams.pPlayer->teamNum=1;
    assert(!Bot_JoinMove(&self) && !nav.crossingEntry && bot.goal==-1);
    self.actorParams.pPlayer->teamNum=0; self.sector=&sectors[0]; bot.now=12;
    assert(Bot_JoinMove(&self)); bot.now=14;
    assert(!Bot_JoinMove(&self) && nav.selectedEntry==-1 && bot.nodes[0].avoidUntil>bot.now);
    puts("PASS CTF vertical/sloped portal approach, ordinary input crossing and bounded server-response wait");
    SithCogSymbol symbols[7]={{0}}; SithCogSymbolTable table={0}; SithCogScript script={0}; sithCog cog={0};
    const char *bindings[]={"flag_red","flag_gold","flag_ghost_red","flag_ghost_gold","start_room","mark_red","mark_gold"};
    int values[]={0,1,2,3,0,0,1};
    for (int i=0;i<7;i++) { symbols[i].pName=(char *)bindings[i]; symbols[i].val.type=COG_TYPE_INT; symbols[i].val.data[0]=values[i]; }
    table.aSymbols=symbols; table.numUsedSymbols=table.tableSize=7;
    strcpy(script.aName,"CTF_MAIN.cog"); cog.pScript=&script; cog.pSymbolTable=&table;
    world.aCogs=&cog; world.numCogs=1;
    Bot_ReadCtfBindings(); assert(nav.ctf && nav.flag[0]==0 && nav.flag[1]==1 && nav.mark[1]==1);
    symbols[6].val.data[0]=1000; Bot_ReadCtfBindings(); assert(!nav.ctf);
    symbols[6].val.data[0]=1; strcpy(script.aName,"other.cog"); Bot_ReadCtfBindings(); assert(!nav.ctf);
    puts("PASS exact stock CTF script and bounded thing/sector binding validation");
    jkBot_Configure("Bot_Reset","ky.3do");
    assert(!nav.ctf && !nav.forceJumpPending && nav.waitUntil==0);
    test_c1_portal_route();
    test_static_bridge_route();
    test_initial_anchor_jump();
}
