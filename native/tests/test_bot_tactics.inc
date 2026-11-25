/* Tactic table, run and diagonal movement, water policy and the confinement
 * watchdog under the new defaults. Controlled fixtures only: flat synthetic
 * ground and hand-built graphs, not a level or a live match. */
static void TacticsUse(int legacy)
{
    for (int i=0;i<BT_COUNT;i++)
        tactics.value[i]=legacy ? botTacticSpecs[i].legacy : botTacticSpecs[i].initial;
}

static void PlainSelf(SithThing *self,SithPlayer *own)
{
    memset(self,0,sizeof(*self)); memset(own,0,sizeof(*own));
    self->type=SITH_THING_PLAYER; self->sector=&plainLand; self->actorParams.pPlayer=own;
    self->actorParams.health=100; self->actorParams.maxThrust=2; self->actorParams.maxRotVelocity=200;
    self->physicsParams.surfDrag=3; self->moveSize=self->collideSize=0.065f;
    self->position=(rdVector3){0,0,BOT_FOOT_HEIGHT};
    self->orient.lvec=(rdVector3){1,0,0}; self->orient.rvec=(rdVector3){0,-1,0};
    self->orient.uvec=(rdVector3){0,0,1};
    self->attach_flags=SITH_ATTACH_SURFACE; self->attachedSurface=&plainGround;
}

/* One movement request along +x; returns whether the run key was pressed. */
static int PlainMove(SithThing *self,int run,int boost,int allowDrop)
{
    memset(bot.axes,0,sizeof(bot.axes)); memset(bot.keys,0,sizeof(bot.keys));
    bot.moveRun=run; bot.moveBoost=boost;
    Bot_Move(self,(rdVector3){1,0,0},allowDrop);
    assert(!bot.moveRun && !bot.moveBoost && queryDepth==0);
    return bot.keys[INPUT_FUNC_FAST];
}

/* Thrust the stock ground controls would apply for the current axes. */
static rdVector3 PlainThrust(SithThing *self)
{
    flex_t forward=bot.axes[INPUT_FUNC_FORWARD], slide=bot.axes[INPUT_FUNC_SLIDE]*0.7f;
    if (forward<0 && self->attach_flags) forward*=0.5f;
    rdVector3 thrust={self->orient.lvec.x*forward+self->orient.rvec.x*slide,
                      self->orient.lvec.y*forward+self->orient.rvec.y*slide,0};
    return thrust;
}

static void PlainFace(SithThing *self,flex_t yaw)
{
    self->orient.lvec=(rdVector3){cosf(yaw),sinf(yaw),0};
    self->orient.rvec=(rdVector3){sinf(yaw),-cosf(yaw),0};
}

static void test_tactic_table(void)
{
    float values[BT_COUNT];
    assert(BT_COUNT<=255 && BOT_TACTICS_WIRE_PAIRS*5+10<=118);
    for (int i=0;i<BT_COUNT;i++) {
        const BotTacticSpec *spec=&botTacticSpecs[i];
        assert(spec->low<=spec->initial && spec->initial<=spec->high);
        assert(spec->low<=spec->legacy && spec->legacy<=spec->high);
        for (int j=0;j<i;j++) assert(strcmp(spec->name,botTacticSpecs[j].name));
    }
    /* The legacy column switches every new behaviour off. */
    assert(botTacticSpecs[BT_RUN].legacy==0 && botTacticSpecs[BT_EXACT_THRUST].legacy==0 &&
           botTacticSpecs[BT_STRAFE_RUN].legacy==0 && botTacticSpecs[BT_CONFINE_SECONDS].legacy==0 &&
           botTacticSpecs[BT_WATER_ENTRY_COST].legacy==0 && botTacticSpecs[BT_DIVE_MIN_VALUE].legacy==0 &&
           botTacticSpecs[BT_EXPLORE_WET].legacy==1);
    const char *good="version=1\n# coach baseline\r\nvalue_conc=22.5\r\nrun=0\n\ngun_far=3\n";
    assert(Bot_ReadTactics(good,strlen(good),values));
    assert(values[BT_VALUE_CONC]==22.5f && values[BT_RUN]==0 && values[BT_GUN_FAR]==3);
    assert(values[BT_VALUE_RAIL]==tactics.value[BT_VALUE_RAIL]);
    static const char *bad[]={
        "value_conc=22\n",                     /* no version */
        "version=2\nvalue_conc=22\n",          /* unknown version */
        "version=1\nversion=1\n",              /* repeated version */
        "version=1\nvalue_conk=22\n",          /* unknown name */
        "version=1\nvalue_conc=22\nvalue_conc=23\n", /* repeated name */
        "version=1\nvalue_conc=41\n",          /* above the range */
        "version=1\ndive_seconds=1\n",         /* below the range */
        "version=1\nvalue_conc=nan\n", "version=1\nvalue_conc=1e1\n",
        "version=1\nvalue_conc=\n", "version=1\nvalue_conc\n", "version=1\n=3\n",
    };
    for (unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);i++)
        assert(!Bot_ReadTactics(bad[i],strlen(bad[i]),values));
    jkBot_Configure("Tactics_File","ky.3do");
    char path[]="/tmp/jk-bot-tactics-XXXXXX";
    int fd=mkstemp(path); assert(fd>=0); close(fd);
    assert(strlen(path)<sizeof(tactics.file)); strcpy(tactics.file,path);
    float before=BT(VALUE_CONC);
    FILE *file=fopen(path,"w"); assert(file); fputs("version=1\nvalue_conc=30\n",file); fclose(file);
    bot.goal=3; bot.nextPlan=bot.armNext=50;
    Bot_ReloadTactics();
    assert(BT(VALUE_CONC)==30 && tactics.revision==1 && bot.nextPlan==0 && bot.armNext==0);
    assert(bot.goal==3 && "a new table must not drop the current goal");
    Bot_ReloadTactics(); assert(tactics.revision==1 && "unchanged content is not applied twice");
    file=fopen(path,"w"); assert(file); fputs("version=1\nvalue_conc=300\n",file); fclose(file);
    Bot_ReloadTactics(); assert(BT(VALUE_CONC)==30 && tactics.revision==1);
    /* A complete revision replaces the table: omitted names return to baseline. */
    file=fopen(path,"w"); assert(file); fputs("version=1\nvalue_rail=5\n",file); fclose(file);
    Bot_ReloadTactics();
    assert(BT(VALUE_RAIL)==5 && BT(VALUE_CONC)==before && tactics.revision==2);
    unlink(path);
    puts("PASS tactic bounds, legacy column, strict complete file revisions and unchanged-content reuse");
}

static void test_tactic_thrust(void)
{
    SithThing self; SithPlayer own;
    testPlainActive=1; plainEdge=plainWall=1e9f; plainGround.flags=0;
    jkBot_Configure("Thrust_Test","ky.3do"); TacticsUse(0);
    PlainSelf(&self,&own);
    flex_t worstLegacy=0;
    for (int air=0;air<2;air++) for (int diagonal=0;diagonal<2;diagonal++)
    for (int degrees=-180;degrees<=180;degrees+=5) {
        flex_t yaw=degrees/BOT_DEG;
        PlainFace(&self,yaw); self.attach_flags=air ? 0 : SITH_ATTACH_SURFACE;
        memset(bot.axes,0,sizeof(bot.axes));
        Bot_ThrustAxes(&self,(rdVector3){1,0,0},diagonal);
        flex_t forward=bot.axes[INPUT_FUNC_FORWARD], slide=bot.axes[INPUT_FUNC_SLIDE];
        assert(fabsf(forward)<=1.0f && fabsf(slide)<=1.0f && "never more than a full key");
        rdVector3 thrust=PlainThrust(&self);
        flex_t size=Bot_Horizontal(thrust), c=fabsf(cosf(yaw)), s=fabsf(sinf(yaw));
        assert(fabsf(thrust.y)<0.0005f && thrust.x>0 && "thrust lies exactly along the wanted direction");
        flex_t gain=cosf(yaw)<0 && !air ? 0.5f : 1.0f, limit=diagonal ? BOT_DIAGONAL_GAIN : 1.0f;
        if (c>0.0001f) limit=Bot_Min(limit,gain/c);
        if (s>0.0001f) limit=Bot_Min(limit,BOT_STRAFE_GAIN/s);
        assert(fabsf(size-limit)<0.0005f && size<=BOT_DIAGONAL_GAIN+0.0005f);
        /* The earlier axes pushed off the wanted line whenever the body was turned. */
        if (!air && !diagonal && degrees>-90 && degrees<90) {
            flex_t oldForward=cosf(yaw), oldSlide=0.7f*sinf(yaw);
            worstLegacy=Bot_Max(worstLegacy,fabsf(atan2f(oldSlide,oldForward)-yaw)*BOT_DEG);
        }
    }
    assert(worstLegacy>9.5f && worstLegacy<10.5f);
    /* Both keys at the diagonal angle: a full fifth more thrust than forward alone. */
    self.attach_flags=SITH_ATTACH_SURFACE; PlainFace(&self,BOT_DIAGONAL_ANGLE);
    Bot_ThrustAxes(&self,(rdVector3){1,0,0},1);
    assert(fabsf(bot.axes[INPUT_FUNC_FORWARD]-1.0f)<0.0005f && fabsf(fabsf(bot.axes[INPUT_FUNC_SLIDE])-1.0f)<0.0005f);
    assert(fabsf(Bot_Horizontal(PlainThrust(&self))-BOT_DIAGONAL_GAIN)<0.0005f);
    Bot_ThrustAxes(&self,(rdVector3){1,0,0},0);
    assert(fabsf(Bot_Horizontal(PlainThrust(&self))-1.0f)<0.0005f);
    testPlainActive=0;
    puts("PASS exact thrust direction at every body angle, full-key axis bound and diagonal gain");
}

static void test_tactic_run(void)
{
    SithThing self; SithPlayer own;
    testPlainActive=1; plainEdge=plainWall=1e9f; plainGround.flags=0;
    jkBot_Configure("Run_Test","ky.3do"); TacticsUse(0); bot.now=5;
    PlainSelf(&self,&own);
    assert(PlainMove(&self,1,0,0) && fabsf(bot.axes[INPUT_FUNC_FORWARD]-1.0f)<0.0005f);
    assert(!PlainMove(&self,0,0,0) && bot.axes[INPUT_FUNC_FORWARD]>0.99f && "no run without a cleared leg");
    assert(!PlainMove(&self,1,0,1) && "a drop leg is walked");
    /* Coasting from a run needs about 0.69 units of checked floor. */
    plainEdge=0.60f; assert(!PlainMove(&self,1,0,0) && bot.axes[INPUT_FUNC_FORWARD]>0.99f);
    plainEdge=0.75f; assert(PlainMove(&self,1,0,0));
    /* always_run: a wall ahead is nothing to fall from; the full-body
       runway the run used to need refused it. */
    plainEdge=1e9f; plainWall=0.60f; assert(PlainMove(&self,1,0,0));
    BT(ALWAYS_RUN)=0; assert(!PlainMove(&self,1,0,0)); BT(ALWAYS_RUN)=1;
    plainWall=1e9f;
    /* A ledge inside ordinary stopping distance steers aside and never runs. */
    plainEdge=0.15f; assert(!PlainMove(&self,1,1,0) && fabsf(bot.axes[INPUT_FUNC_SLIDE])>0.1f);
    plainEdge=1e9f;
    self.physicsParams.flags=SITH_PF_CROUCHING; assert(!PlainMove(&self,1,0,0));
    self.physicsParams.flags=0;
    self.actorParams.flags=SITH_AF_IMMOBILE; assert(!PlainMove(&self,1,0,0));
    self.actorParams.flags=0;
    plainGround.flags=SITH_SURFACE_ICY; assert(!PlainMove(&self,1,0,0));
    plainGround.flags=SITH_SURFACE_WATER; assert(!PlainMove(&self,1,0,0));
    plainGround.flags=0;
    plainLand.flags=SITH_SECTOR_USETHRUST; assert(!PlainMove(&self,1,0,0));
    plainLand.flags=0;
    self.attach_flags=0; assert(!PlainMove(&self,1,0,0));
    self.attach_flags=SITH_ATTACH_SURFACE;
    self.physicsParams.surfDrag=0; assert(!PlainMove(&self,1,0,0) && "unknown footing is walked");
    self.physicsParams.surfDrag=3;
    /* Stock Speed adds to thrust, so the same run needs a longer runway. */
    self.actorParams.extraSpeed=2;
    plainEdge=1.0f; assert(!PlainMove(&self,1,0,0));
    plainEdge=1.3f; assert(PlainMove(&self,1,0,0));
    self.actorParams.extraSpeed=0; plainEdge=1e9f;
    /* The diagonal is granted with the run and remembered for the next aim. */
    PlainFace(&self,BOT_DIAGONAL_ANGLE); bot.boostedAt=0;
    assert(PlainMove(&self,1,1,0) && bot.boostedAt==bot.now);
    assert(fabsf(Bot_Horizontal(PlainThrust(&self))-BOT_DIAGONAL_GAIN)<0.0005f);
    /* It needs more room than the run alone: here the run stays, the diagonal goes. */
    plainEdge=0.75f; bot.boostedAt=0;
    assert(PlainMove(&self,1,1,0) && bot.boostedAt==0);
    assert(fabsf(Bot_Horizontal(PlainThrust(&self))-1.0f)<0.0005f);
    plainEdge=1e9f;
    BT(RUN)=0; bot.boostedAt=0;
    assert(!PlainMove(&self,1,1,0) && bot.boostedAt==bot.now && "the diagonal alone still needs its corridor");
    BT(STRAFE_RUN)=0; bot.boostedAt=0; assert(!PlainMove(&self,1,1,0) && bot.boostedAt==0);
    /* Legacy values reproduce the earlier inputs exactly. */
    TacticsUse(1); PlainFace(&self,45/BOT_DEG); bot.boostedAt=0;
    assert(!PlainMove(&self,1,1,0) && bot.boostedAt==0);
    assert(fabsf(bot.axes[INPUT_FUNC_FORWARD]-cosf(45/BOT_DEG))<0.0005f);
    assert(fabsf(fabsf(bot.axes[INPUT_FUNC_SLIDE])-sinf(45/BOT_DEG))<0.0005f);
    PlainFace(&self,180/BOT_DEG); PlainMove(&self,1,1,0);
    assert(fabsf(bot.axes[INPUT_FUNC_FORWARD]+0.65f)<0.0005f);
    testPlainActive=0;
    puts("PASS run key only on checked dry runway: ledge, wall, drop leg, crouch, ice, water, thrust sector, Speed and legacy");
}

static void RouteNode(int index,flex_t x,flex_t y)
{
    BotNode *node=&bot.nodes[index];
    memset(node,0,sizeof(*node));
    node->pos=(rdVector3){x,y,BOT_FOOT_HEIGHT}; node->sector=&plainLand; node->item=-1; node->visited=-120;
}

static void RouteEdge(int from,int to,int mode)
{
    BotNode *node=&bot.nodes[from];
    node->edges[node->nEdges++]=(BotEdge){to,Bot_Distance(node->pos,bot.nodes[to].pos),mode};
}

static int RouteStep(SithThing *self,flex_t x,int position)
{
    memset(bot.axes,0,sizeof(bot.axes)); memset(bot.keys,0,sizeof(bot.keys));
    self->position.x=x; bot.routePos=position; bot.moveRun=bot.moveBoost=0;
    bot.goal=4; bot.routeCount=4; bot.nextPlan=1e9f;
    Bot_Navigate(self);
    assert(bot.goal==4 && bot.routePos==position && queryDepth==0);
    return bot.keys[INPUT_FUNC_FAST];
}

static void test_tactic_route_run(void)
{
    /* The body turn is read from the keyboard axes here. */
    flex_t turnRate=BT(TURN_RATE); BT(TURN_RATE)=0;
    SithThing self; SithPlayer own;
    testPlainActive=1; plainEdge=plainWall=1e9f; plainGround.flags=0; plainLand.flags=0;
    jkBot_Configure("Route_Test","ky.3do"); TacticsUse(0); bot.now=5; BT(TURN_RATE)=0;
    PlainSelf(&self,&own);
    bot.world=NULL; bot.graphDone=1; bot.nNodes=5;
    RouteNode(0,0,0); RouteNode(1,1,0); RouteNode(2,2,0); RouteNode(3,3,0); RouteNode(4,3.5f,0);
    RouteEdge(0,1,BOT_ROUTE_WALK); RouteEdge(1,2,BOT_ROUTE_WALK); RouteEdge(2,3,BOT_ROUTE_WALK);
    RouteEdge(3,4,BOT_ROUTE_JUMP);
    for (int i=0;i<4;i++) bot.route[i]=i+1;
    bot.routePos=0; bot.routeCount=4; self.position.x=0.1f;
    assert(fabsf(Bot_StraightWalk(&self,10)-2.9f)<0.0005f && "the jump leg ends the stretch");
    assert(Bot_StraightWalk(&self,1)>=1 && Bot_StraightWalk(&self,1)<2.9f && "stops measuring once enough");
    /* Open straight: run, take the diagonal, then turn the body off the path. */
    bot.boostedAt=0;
    assert(RouteStep(&self,0.1f,0) && bot.boostedAt==bot.now && fabsf(bot.axes[INPUT_FUNC_TURN])<0.01f);
    bot.now+=0.033f;
    assert(RouteStep(&self,0.1f,0) && fabsf(bot.axes[INPUT_FUNC_TURN])>0.3f);
    assert(fabsf(Bot_Horizontal(PlainThrust(&self))-1.0f)<0.0005f && PlainThrust(&self).x>0.999f);
    /* An opponent owns the aim; the path still gets its run. */
    bot.targetSlot=0; bot.now+=0.033f;
    assert(RouteStep(&self,0.1f,0) && fabsf(bot.axes[INPUT_FUNC_TURN])<0.01f);
    bot.targetSlot=-1;
    /* 1.5 units of straight walking remain: run. Half a unit before the jump: walk. */
    assert(RouteStep(&self,1.5f,1));
    bot.boostedAt=0;
    assert(!RouteStep(&self,2.5f,2) && bot.boostedAt==0 && bot.axes[INPUT_FUNC_FORWARD]>0.99f);
    BT(RUN_BRAKE)=0.4f; assert(RouteStep(&self,2.5f,2)); BT(RUN_BRAKE)=0.8f;
    /* A square corner ends the stretch at the corner. */
    RouteNode(3,2,1); RouteNode(4,2,1.5f);
    bot.nodes[2].nEdges=0; RouteEdge(2,3,BOT_ROUTE_WALK); RouteEdge(3,4,BOT_ROUTE_WALK);
    bot.routePos=1; self.position.x=1.5f;
    assert(fabsf(Bot_StraightWalk(&self,10)-0.5f)<0.0005f);
    /* always_run takes the corner running, on open floor; the old rule walked. */
    assert(RouteStep(&self,1.5f,1));
    BT(ALWAYS_RUN)=0; assert(!RouteStep(&self,1.5f,1)); BT(ALWAYS_RUN)=1;
    /* A gentle bend does not. */
    RouteNode(3,3,0.3f); RouteNode(4,4,0.3f);
    bot.nodes[2].nEdges=bot.nodes[3].nEdges=0; RouteEdge(2,3,BOT_ROUTE_WALK); RouteEdge(3,4,BOT_ROUTE_WALK);
    bot.routePos=1; self.position.x=1.5f;
    assert(Bot_StraightWalk(&self,10)>2.5f && RouteStep(&self,1.5f,1));
    /* A lift landing ends it too. */
    nav.liftForNode[3]=1; assert(fabsf(Bot_StraightWalk(&self,10)-0.5f)<0.0005f); nav.liftForNode[3]=0;
    TacticsUse(1); bot.boostedAt=0;
    assert(!RouteStep(&self,0.1f,0) && bot.boostedAt==0 && fabsf(bot.axes[INPUT_FUNC_TURN])<0.01f);
    testPlainActive=0;
    BT(TURN_RATE)=turnRate;
    puts("PASS route follower runs open straights, walks into jumps, corners and lift landings, and turns the body only for the diagonal");
}

static void WaterNode(int index,flex_t x,SithSector *sector,int item)
{
    BotNode *node=&bot.nodes[index];
    memset(node,0,sizeof(*node));
    node->pos=(rdVector3){x,0,sector->flags ? -0.3f : 0}; node->sector=sector; node->item=item; node->visited=-120;
}

static void WaterItem(SithThing *items,int index,const char *name,int node)
{
    memset(&items[index],0,sizeof(items[index]));
    items[index].type=SITH_THING_ITEM; items[index].idx=index; items[index].guid=100+index;
    items[index].sector=bot.nodes[node].sector; items[index].position=bot.nodes[node].pos;
    strcpy(items[index].aName,name);
}

static void test_tactic_water(void)
{
    static SithWorld world; static SithThing items[3]; static SithSector land,pool;
    static flex_t distance[BOT_NODES]; static int parent[BOT_NODES];
    SithThing self={0}; SithPlayer own={0};
    memset(&land,0,sizeof(land)); memset(&pool,0,sizeof(pool)); pool.flags=SITH_SECTOR_UNDERWATER;
    jkBot_Configure("Water_Test","ky.3do"); bot.elite=1; bot.now=5; jkPlayer_maxPlayers=0;
    self.type=SITH_THING_PLAYER; self.sector=&land; self.actorParams.pPlayer=&own; self.actorParams.health=100;
    bot.world=sithWorld_g_pCurrentWorld=&world; world.aThings=items; world.numThings=0; world.numThingsLoaded=1;
    bot.graphDone=1; bot.nNodes=4;
    WaterNode(0,0,&land,-1); WaterNode(1,5,&land,-1); WaterNode(2,0.6f,&pool,0); WaterNode(3,1.3f,&pool,-1);
    bot.nodes[0].nEdges=2;
    bot.nodes[0].edges[0]=(BotEdge){1,5.0f,BOT_ROUTE_WALK};
    bot.nodes[0].edges[1]=(BotEdge){2,2.6f,BOT_ROUTE_WATER_ENTRY};
    bot.nodes[2].nEdges=1; bot.nodes[2].edges[0]=(BotEdge){3,2.7f,BOT_ROUTE_SWIM};
    WaterItem(items,0,"powercell",2);
    own.aItems[SITHBIN_REPEATER].amount=1; own.aItems[SITHBIN_REPEATER].state=SITHINVENTORY_ITEM_AVAILABLE;
    own.aItems[SITHBIN_POWER].amount=25; /* low on shots, but not out */
    /* Before: a cheap power cell and plain curiosity both pull the bot under. */
    TacticsUse(1);
    Bot_PathDistances(&self,0,distance,parent); assert(fabsf(distance[2]-2.6f)<0.0005f);
    assert(Bot_GearValue(&self,0)==5.0f);
    bot.goal=-1; Bot_Plan(&self); assert(bot.goal==2 && bot.routeCount==1);
    bot.nodes[2].item=-1; bot.goal=-1; Bot_Plan(&self);
    assert(bot.goal==2 && "legacy exploration dives");
    bot.nodes[2].item=0;
    /* Now: neither is worth the water, including a dive already chosen. */
    TacticsUse(0);
    Bot_PathDistances(&self,0,distance,parent); assert(fabsf(distance[2]-6.6f)<0.0005f);
    assert(Bot_GearValue(&self,0)==0 && Bot_GoalPickup(&self,&bot.nodes[2])==0);
    bot.goal=2; bot.goalSetAt=bot.now; Bot_Plan(&self);
    assert(bot.goal==1 && "a cheap dive in progress is let go");
    bot.nodes[2].item=-1; bot.goal=2; bot.goalSetAt=bot.now; Bot_Plan(&self);
    assert(bot.goal==1 && "the bot no longer dives just to look");
    bot.nodes[2].item=0;
    /* Out of shots, the same cell is ammunition for the only real gun held. */
    own.aItems[SITHBIN_POWER].amount=0;
    assert(Bot_Starved(&self) && Bot_GearValue(&self,0)==12.0f);
    own.aItems[SITHBIN_POWER].amount=25; assert(!Bot_Starved(&self));
    /* A missing concussion rifle on the bottom is still worth the swim. */
    world.numThings=1; world.numThingsLoaded=2; WaterItem(items,1,"concrifle",3); bot.nodes[3].item=1;
    assert(Bot_GearValue(&self,1)==18.0f && Bot_GoalPickup(&self,&bot.nodes[3])==18.0f);
    bot.goal=-1; Bot_Plan(&self);
    assert(bot.goal==3 && bot.routeCount==2 && bot.route[0]==2 && bot.route[1]==3);
    BT(DIVE_MIN_VALUE)=20; bot.goal=-1; Bot_Plan(&self);
    assert(bot.goal==1 && "the threshold is the coach's to raise");
    BT(DIVE_MIN_VALUE)=6;
    /* Health in the water is taken when it is needed, and left when it is not. */
    world.numThings=2; world.numThingsLoaded=3; WaterItem(items,2,"healthpack",2);
    self.actorParams.health=35; assert(Bot_GearValue(&self,2)==16.0f);
    self.actorParams.health=90; assert(Bot_GearValue(&self,2)==0);
    self.actorParams.health=100;
    /* Seconds underwater before heading for air. */
    self.sector=&pool; nav.waterSince=1; bot.now=9.5f;
    assert(Bot_NeedsAir(&self)); BT(DIVE_SECONDS)=12; assert(!Bot_NeedsAir(&self));
    puts("PASS water policy drops cheap and exploratory dives, prices the entry, and still dives for the concussion rifle and needed health");
}

static int ConfineRun(SithThing *self,flex_t seconds,flex_t speed)
{
    int strikes=bot.confine.strikes;
    flex_t last=bot.confine.lastStrike;
    for (flex_t t=0;t<seconds;t+=0.05f) {
        bot.now+=0.05f;
        if (speed>0) self->position.x+=speed*0.05f;
        else self->position.y=0.12f*sinf(bot.now*3.0f);
        Bot_Confinement(self);
        if (bot.confine.lastStrike!=last) return 1;
    }
    assert(bot.confine.strikes==strikes);
    return 0;
}

static void test_tactic_swim(void)
{
    static SithWorld world; static SithThing items[1]; static SithSector land,pool;
    static flex_t distance[BOT_NODES]; static int parent[BOT_NODES];
    SithThing self={0}; SithPlayer own={0};
    memset(&land,0,sizeof(land)); memset(&pool,0,sizeof(pool)); pool.flags=SITH_SECTOR_UNDERWATER;
    jkBot_Configure("Swim_Test","ky.3do"); bot.elite=1; bot.now=5; jkPlayer_maxPlayers=0;
    self.type=SITH_THING_PLAYER; self.sector=&land; self.actorParams.pPlayer=&own; self.actorParams.health=100;
    self.moveSize=self.collideSize=0.065f; self.orient.lvec=(rdVector3){1,0,0}; self.orient.rvec=(rdVector3){0,-1,0};
    bot.world=sithWorld_g_pCurrentWorld=&world; world.aThings=items; world.numThings=0; world.numThingsLoaded=1;
    bot.graphDone=1; bot.nNodes=4; bot.frameDt=0.02f;
    WaterNode(0,0,&land,-1); WaterNode(1,5,&land,-1); WaterNode(2,0.6f,&pool,-1); WaterNode(3,1.3f,&pool,-1);
    bot.nodes[0].nEdges=1; bot.nodes[0].edges[0]=(BotEdge){2,2.6f,BOT_ROUTE_SWIM};
    TacticsUse(0);
    /* Any way from a bank into water is priced, whatever the edge is called;
       a way in that wasted a dive is priced out until the memory lapses. */
    Bot_PathDistances(&self,0,distance,parent); assert(fabsf(distance[2]-6.6f)<0.0005f);
    /* swim_cost: the stroke is slow, so a leg under water costs three times its length. */
    bot.nodes[2].nEdges=1; bot.nodes[2].edges[0]=(BotEdge){3,0.7f,BOT_ROUTE_SWIM};
    Bot_PathDistances(&self,0,distance,parent); assert(fabsf(distance[3]-(6.6f+0.7f+1.4f))<0.0005f);
    BT(SWIM_COST)=1; Bot_PathDistances(&self,0,distance,parent); assert(fabsf(distance[3]-7.3f)<0.0005f);
    BT(SWIM_COST)=3; bot.nodes[2].nEdges=0;
    assert(!Bot_CrossingFailed(&land,&pool));
    Bot_RememberCrossing(&land,&pool); assert(Bot_CrossingFailed(&land,&pool) && !Bot_CrossingFailed(&pool,&land));
    Bot_PathDistances(&self,0,distance,parent); assert(fabsf(distance[2]-56.6f)<0.0005f);
    bot.now+=46; assert(!Bot_CrossingFailed(&land,&pool));
    Bot_PathDistances(&self,0,distance,parent); assert(fabsf(distance[2]-6.6f)<0.0005f);
    /* Turning back for air sets the entry and the destination aside once. */
    self.sector=&pool; nav.waterSince=bot.now-9; bot.entryFrom=1; bot.entryTo=3; bot.goal=3; bot.airReturn=0;
    assert(Bot_NeedsAir(&self));
    Bot_CheckAirReturn(&self);
    assert(bot.airReturn==1 && bot.goal==-1 && Bot_CrossingFailed(&land,&pool));
    assert(fabsf(bot.nodes[3].avoidUntil-(bot.now+45))<0.001f);
    bot.goal=1; Bot_CheckAirReturn(&self); assert(bot.goal==1 && "one verdict per swim");
    self.sector=&land; bot.tele.wasWet=1; bot.crossing=1; Bot_CheckAirReturn(&self);
    assert(!bot.airReturn && !bot.entryFrom && !bot.entryTo && !bot.crossing);
    bot.crossing=1; bot.crossingAt=bot.now; bot.tele.wasWet=0; Bot_CheckAirReturn(&self); assert(bot.crossing);
    bot.now+=2.5f; Bot_CheckAirReturn(&self); assert(!bot.crossing && "an entry never taken does not keep the allowance");
    /* A swim judged to reach another bank may use most of the engine's
       twenty seconds; a dive of unknown outcome still turns back early. */
    self.sector=&pool; nav.waterSince=bot.now-9.5f; bot.crossing=0;
    assert(Bot_Breath()==8.0f && Bot_NeedsAir(&self));
    bot.crossing=1; assert(Bot_Breath()==17.0f && !Bot_NeedsAir(&self));
    self.actorParams.endurance=9000; assert(!Bot_NeedsAir(&self));
    self.actorParams.endurance=17500; assert(Bot_NeedsAir(&self));
    self.actorParams.endurance=0; nav.waterSince=bot.now-17.5f; assert(Bot_NeedsAir(&self));
    /* air_health: being hurt is not being out of breath; a hurt bot routes to
       health by the plan, and the surface heals nothing. */
    nav.waterSince=bot.now-9.5f; self.actorParams.health=25;
    assert(!Bot_NeedsAir(&self) && "hurt but breathing: keep going");
    BT(AIR_HEALTH)=30; assert(Bot_NeedsAir(&self) && "the old rule is the coach's to restore");
    BT(AIR_HEALTH)=0; self.actorParams.health=100;
    BT(CROSSING_SECONDS)=0; assert(Bot_Breath()==8.0f && Bot_NeedsAir(&self)); BT(CROSSING_SECONDS)=17;
    bot.crossing=0; self.actorParams.endurance=9000; assert(Bot_NeedsAir(&self)); self.actorParams.endurance=0;
    /* Steep legs are swum by looking along them and pushing forward. */
    rdVector3 below={0,0,-1.5f},shallow={1.0f,0,-0.3f},above={0,0,1.5f};
    nav.waterSince=bot.now; self.position=(rdVector3){0,0,0};
    memset(bot.axes,0,sizeof(bot.axes)); memset(bot.keys,0,sizeof(bot.keys)); bot.tele.pitched=0;
    assert(Bot_NavDirectMove(&self,below,1));
    assert(bot.axes[INPUT_FUNC_PITCH]==-0.8f && bot.axes[INPUT_FUNC_FORWARD]==0 && bot.keys[INPUT_FUNC_DUCK]);
    self.actorParams.headPYR.x=-60; memset(bot.axes,0,sizeof(bot.axes));
    assert(Bot_NavDirectMove(&self,below,1));
    assert(bot.axes[INPUT_FUNC_FORWARD]==1 && bot.keys[INPUT_FUNC_DUCK] && bot.tele.pitched>0);
    assert(fabsf(bot.axes[INPUT_FUNC_PITCH]-(-15.0f*4.0f/90.0f))<0.0005f && "settles at seventy-five degrees");
    memset(bot.axes,0,sizeof(bot.axes)); assert(Bot_NavDirectMove(&self,above,1));
    assert(bot.axes[INPUT_FUNC_FORWARD]==0 && bot.axes[INPUT_FUNC_PITCH]==0.8f && "looking the wrong way: turn first");
    self.actorParams.headPYR.x=60; memset(bot.axes,0,sizeof(bot.axes)); assert(Bot_NavDirectMove(&self,above,1));
    assert(bot.axes[INPUT_FUNC_FORWARD]==1);
    memset(bot.axes,0,sizeof(bot.axes)); assert(Bot_NavDirectMove(&self,shallow,1));
    assert(bot.axes[INPUT_FUNC_PITCH]==0 && "a shallow leg keeps the ordinary stroke");
    self.physicsParams.flags|=SITH_PF_ONWATERSURFACE; self.actorParams.headPYR.x=-60;
    memset(bot.axes,0,sizeof(bot.axes)); assert(Bot_NavDirectMove(&self,below,1));
    assert(bot.axes[INPUT_FUNC_PITCH]==0 && bot.axes[INPUT_FUNC_FORWARD]==0 && "the surface does not tilt thrust");
    self.physicsParams.flags&=~SITH_PF_ONWATERSURFACE;
    TacticsUse(1); memset(bot.axes,0,sizeof(bot.axes)); memset(bot.keys,0,sizeof(bot.keys));
    assert(Bot_NavDirectMove(&self,below,1));
    assert(bot.axes[INPUT_FUNC_PITCH]==0 && bot.axes[INPUT_FUNC_FORWARD]==0 && bot.keys[INPUT_FUNC_DUCK] && "legacy sinks on the key alone");
    Bot_RememberCrossing(&land,&pool); assert(!Bot_CrossingFailed(&land,&pool) && "legacy keeps no dive memory");
    TacticsUse(0); self.actorParams.headPYR.x=0; bot.crossing=0; bot.goal=-1;
    puts("PASS swim: priced and remembered entries, one air-return verdict, crossings on the real air supply, pitched steep legs, surface and legacy unchanged");
}

static void test_tactic_runjump(void)
{
    static SithWorld world; static SithThing items[1]; static SithSector land;
    static flex_t distance[BOT_NODES]; static int parent[BOT_NODES];
    SithThing self={0}; SithPlayer own={0};
    memset(&land,0,sizeof(land));
    jkBot_Configure("Jump_Test","ky.3do"); bot.elite=1; bot.now=5; jkPlayer_maxPlayers=0;
    self.type=SITH_THING_PLAYER; self.sector=&land; self.actorParams.pPlayer=&own; self.actorParams.health=100;
    self.moveSize=self.collideSize=0.065f; self.orient.lvec=(rdVector3){1,0,0}; self.orient.rvec=(rdVector3){0,-1,0};
    /* The stock player and world. */
    self.actorParams.maxThrust=2.0f; self.actorParams.jumpSpeed=1.5f;
    self.physicsParams.surfDrag=3.0f; self.physicsParams.airDrag=0.5f;
    bot.world=sithWorld_g_pCurrentWorld=&world; world.gravity=4.0f; world.aThings=items; world.numThings=0; world.numThingsLoaded=1;
    bot.physicsStep=1.0f/150.0f; bot.frameDt=1.0f/30.0f; bot.forceEnabled=1;
    TacticsUse(0);
    flex_t speed,seconds,reach,sink,hold; int force;
    /* Sprinting from rest: thrust over drag, doubled by the run key. */
    RunJump_Sprint(&self,2.0f,6.0f,&speed,&seconds); assert(fabsf(speed-4.0f/3.0f)<0.01f);
    flex_t sped=2.0f+RunJump_Boost(4);
    assert(RunJump_Boost(0)==0 && RunJump_Boost(2)==1.5f && RunJump_Boost(4)==2.5f);
    RunJump_Sprint(&self,sped,0.30f,&speed,&seconds);
    assert(speed>1.70f && speed<1.84f && seconds>0.27f && seconds<0.33f && "a third of a unit already gives half of full speed");
    flex_t longer; RunJump_Sprint(&self,sped,1.0f,&longer,&seconds); assert(longer>speed+0.6f && longer<2.0f*sped/3.0f);
    /* Flight keeps the launch speed, less air drag; a higher ledge has to be cleared first. */
    assert(RunJump_Flight(&self,2.0f,2.65f,2.0f,0,&reach,&sink,&seconds));
    assert(seconds>1.1f && seconds<1.3f && reach>1.9f && reach<2.4f && sink>2.0f && sink<2.4f);
    assert(!RunJump_Flight(&self,2.0f,2.65f,2.0f,1.0f,&reach,&sink,&seconds) && "too low for the ledge");
    assert(RunJump_Flight(&self,2.0f,3.85f,2.0f,1.0f,&reach,&sink,&seconds) && sink<2.95f);
    /* The hold is solved for the gap: the alcove jump on Canyon Oasis wants
       more hold than rank three has, and rank two cannot make it at all. */
    flex_t alcove=(2.0f+RunJump_Boost(2))*BOT_DIAGONAL_GAIN;
    assert(RunJump_Lift(&self,2.13f,alcove,2.10f,1.0f,4,&force,&hold,&seconds) && force==1 && hold>1.05f && hold<1.35f);
    assert(!RunJump_Lift(&self,2.13f,alcove,2.10f,1.0f,3,&force,&hold,&seconds) || fabsf(hold-1.05f)<0.001f);
    assert(!RunJump_Lift(&self,2.13f,alcove,2.10f,1.0f,2,&force,&hold,&seconds));
    assert(RunJump_Lift(&self,2.33f,3.5f,2.40f,0,4,&force,&hold,&seconds) && force==1 && hold>=0.15f && hold<0.6f);
    assert(RunJump_Lift(&self,2.33f,3.5f,2.40f,0,1,&force,&hold,&seconds) && hold<=0.35f && "a level gap needs only rank one");
    assert(!RunJump_Lift(&self,3.6f,4.5f,1.4f,0,4,&force,&hold,&seconds) && "too fast for a short gap");
    assert(!RunJump_Lift(&self,1.33f,2.0f,4.5f,0,4,&force,&hold,&seconds) && "no landing that far that does not hurt");
    assert(RunJump_Lift(&self,4.0f/3.0f,2.0f,1.0f,0,0,&force,&hold,&seconds) && force==0 && "an ordinary running jump");
    assert(!RunJump_Lift(&self,4.0f/3.0f,2.0f,2.0f,0,0,&force,&hold,&seconds));
    /* The planner uses an edge only with the powers it was solved for, the
       mana for them, good health, and no recent miss. */
    bot.graphDone=1; bot.nNodes=2;
    WaterNode(0,0,&land,-1); WaterNode(1,2.4f,&land,-1);
    bot.nodes[0].nEdges=1; bot.nodes[0].edges[0]=(BotEdge){1,7.4f,BOT_ROUTE_RUNJUMP};
    memset(nav.runEdges,0,sizeof(nav.runEdges)); nav.runCount=1;
    nav.runEdges[0]=(BotRunJump){.from=0,.to=1,.speedRank=4,.jumpRank=4,.speed=2.3f,.hold=0.3f,.runway=0.45f,.sprint=0.33f,.sped=1,.force=1};
    own.aItems[SITHBIN_F_SPEED].amount=4; own.aItems[SITHBIN_F_JUMP].amount=4; own.aItems[SITHBIN_FORCEMANA].amount=400;
    assert(Bot_RunJumpPlan(&self,0,1)==&nav.runEdges[0] && !Bot_RunJumpPlan(&self,1,0));
    assert(Bot_RunJumpUsable(&self,0,1));
    Bot_PathDistances(&self,0,distance,parent); assert(fabsf(distance[1]-7.4f)<0.0005f);
    own.aItems[SITHBIN_FORCEMANA].amount=10; assert(!Bot_RunJumpUsable(&self,0,1));
    Bot_PathDistances(&self,0,distance,parent); assert(distance[1]>1e19f && "no mana, no jump");
    own.aItems[SITHBIN_FORCEMANA].amount=400;
    own.aItems[SITHBIN_F_SPEED].amount=3; assert(!Bot_RunJumpUsable(&self,0,1) && "solved for another Speed rank");
    own.aItems[SITHBIN_F_SPEED].amount=4; own.aItems[SITHBIN_F_JUMP].amount=3; assert(!Bot_RunJumpUsable(&self,0,1));
    own.aItems[SITHBIN_F_JUMP].amount=4; self.actorParams.health=35; assert(!Bot_RunJumpUsable(&self,0,1));
    self.actorParams.health=100; nav.runEdges[0].failedUntil=bot.now+60; assert(!Bot_RunJumpUsable(&self,0,1));
    bot.now+=61; assert(Bot_RunJumpUsable(&self,0,1));
    bot.forceEnabled=0; assert(!Bot_RunJumpUsable(&self,0,1)); bot.forceEnabled=1;
    /* A plan is solved for one speed. Without Force Speed running either
       kind fits and the one needing no mana is preferred; with it running
       only a plan solved with it is used. */
    nav.runEdges[1]=(BotRunJump){.from=0,.to=1,.speedRank=4,.jumpRank=4,.speed=1.5f,.runway=0.6f,.sprint=1.0f,.dive=1}; nav.runCount=2;
    assert(Bot_RunJumpPlan(&self,0,1)==&nav.runEdges[1]);
    self.actorParams.extraSpeed=2.5f; assert(Bot_RunJumpPlan(&self,0,1)==&nav.runEdges[0]);
    nav.runEdges[0].from=5;
    assert(!Bot_RunJumpPlan(&self,0,1) && !Bot_RunJumpUsable(&self,0,1) && "nothing solved for this speed");
    self.actorParams.extraSpeed=0; assert(Bot_RunJumpUsable(&self,0,1));
    own.aItems[SITHBIN_FORCEMANA].amount=0; assert(Bot_RunJumpUsable(&self,0,1) && "a plain run-off costs no mana");
    own.aItems[SITHBIN_FORCEMANA].amount=400; nav.runEdges[0].from=0;
    TacticsUse(1); assert(!Bot_RunJumpUsable(&self,0,1) && "legacy has no running jumps");
    Bot_PathDistances(&self,0,distance,parent); assert(distance[1]>1e19f);
    TacticsUse(0); nav.runCount=0; bot.forceEnabled=0;
    puts("PASS running jump: sprint speed from rest, drag-limited flight, solved Force Jump hold, rank and landing-speed limits, plan per Force Speed state, planner gate and legacy off");
}

static void test_tactic_use(void)
{
    SithThing self; SithPlayer own;
    testPlainActive=1; plainEdge=0.15f; plainWall=1e9f; plainGround.flags=0;
    jkBot_Configure("Use_Test","ky.3do"); TacticsUse(0); bot.now=5;
    PlainSelf(&self,&own);
    /* Every press plays the stock use animation. Blocked by a ledge with
       nothing in front to use: no press. */
    bot.nextUse=0; PlainMove(&self,0,0,0);
    assert(!bot.keys[INPUT_FUNC_ACTIVATE] && fabsf(bot.axes[INPUT_FUNC_SLIDE])>0.1f && "steers aside without using");
    /* A switch on the wall in reach: press, then not again for 0.8 s. */
    plainEdge=1e9f; plainWall=0.12f; plainGround.flags=SITH_SURFACE_COG_LINKED;
    assert(Bot_UseTarget(&self));
    PlainMove(&self,0,0,0); assert(bot.keys[INPUT_FUNC_ACTIVATE]);
    bot.now+=0.5f; PlainMove(&self,0,0,0); assert(!bot.keys[INPUT_FUNC_ACTIVATE]);
    /* A plain wall: nothing to use. */
    plainGround.flags=0; bot.now+=1.0f; assert(!Bot_UseTarget(&self));
    PlainMove(&self,0,0,0); assert(!bot.keys[INPUT_FUNC_ACTIVATE]);
    /* Legacy presses whenever blocked. */
    TacticsUse(1); plainWall=1e9f; plainEdge=0.15f; bot.nextUse=0;
    PlainMove(&self,0,0,0); assert(bot.keys[INPUT_FUNC_ACTIVATE]);
    TacticsUse(0); plainEdge=plainWall=1e9f; plainGround.flags=0; testPlainActive=0;
    puts("PASS use only with a switch or usable thing in reach; a blocked path alone presses nothing; legacy presses blind");
}

static void test_tactic_confinement(void)
{
    static SithSector land,pool;
    SithThing self={0}; SithPlayer own={0};
    memset(&land,0,sizeof(land)); memset(&pool,0,sizeof(pool)); pool.flags=SITH_SECTOR_UNDERWATER;
    jkBot_Configure("Confine_Test","ky.3do"); TacticsUse(0); bot.now=10;
    self.type=SITH_THING_PLAYER; self.sector=&land; self.actorParams.pPlayer=&own; self.actorParams.health=100;
    bot.world=NULL; bot.graphDone=1; bot.nNodes=3;
    for (int i=0;i<3;i++) { memset(&bot.nodes[i],0,sizeof(bot.nodes[i])); bot.nodes[i].sector=&land; bot.nodes[i].item=-1; }
    bot.nodes[1].pos.x=0.5f; bot.nodes[2].pos.x=3.0f;
    bot.goal=1; bot.route[0]=1; bot.routeCount=1; bot.routePos=0;
    /* Jittering in place toward a goal: confined after one window. */
    flex_t started=bot.now;
    assert(ConfineRun(&self,8,0) && bot.confine.strikes==1);
    assert(bot.now-started>5.5f && bot.now-started<6.5f);
    assert(bot.goal==-1 && bot.routeCount==0 && bot.nextPlan==0);
    assert(fabsf(bot.nodes[1].avoidUntil-(bot.now+12))<0.01f && bot.nodes[0].avoidUntil<=bot.now && bot.nodes[2].avoidUntil<=bot.now);
    /* A routine avoid may not shorten the escape's. */
    flex_t held=bot.nodes[1].avoidUntil;
    Bot_AvoidNode(&bot.nodes[1],5); assert(bot.nodes[1].avoidUntil==held);
    Bot_AvoidNode(&bot.nodes[2],5); assert(fabsf(bot.nodes[2].avoidUntil-(bot.now+5))<0.01f);
    bot.nodes[2].avoidUntil=0;
    /* Again within 45 seconds: twice as long, and the neighbourhood with it. */
    bot.goal=0; bot.route[0]=0; bot.routeCount=1; bot.routePos=0;
    assert(ConfineRun(&self,8,0) && bot.confine.strikes==2);
    assert(fabsf(bot.nodes[0].avoidUntil-(bot.now+24))<0.01f && fabsf(bot.nodes[1].avoidUntil-(bot.now+24))<0.01f);
    assert(bot.nodes[2].avoidUntil<=bot.now && "a place across the room stays available");
    bot.goal=2; bot.route[0]=2; bot.routeCount=1; bot.routePos=0;
    assert(ConfineRun(&self,8,0) && bot.confine.strikes==3);
    assert(fabsf(bot.nodes[2].avoidUntil-(bot.now+48))<0.01f);
    /* Not confined: travelling, waiting, fighting on dry ground, or idle. */
    self.position=(rdVector3){0,0,0}; bot.goal=2; bot.route[0]=2; bot.routeCount=1; bot.routePos=0;
    assert(!ConfineRun(&self,20,1.0f));
    self.position=(rdVector3){0,0,0};
    nav.waitUntil=bot.now+100; assert(!ConfineRun(&self,20,0)); nav.waitUntil=0;
    nav.liftWaitAt=bot.now; assert(!ConfineRun(&self,20,0)); nav.liftWaitAt=0;
    bot.targetSlot=0; assert(!ConfineRun(&self,20,0)); bot.targetSlot=-1;
    bot.goal=-1; assert(!ConfineRun(&self,20,0)); bot.goal=2;
    BT(CONFINE_SECONDS)=0; assert(!ConfineRun(&self,20,0)); BT(CONFINE_SECONDS)=6;
    /* A glimpse of an opponent only pauses the count; a real fight clears it. */
    int caught=0;
    for (int i=0;i<600 && !caught;i++) {
        bot.targetSlot=(i/10)%2 ? 0 : -1;
        caught=ConfineRun(&self,0.05f,0);
    }
    assert(caught); bot.targetSlot=-1;
    bot.goal=2; bot.route[0]=2; bot.routeCount=1; bot.routePos=0;
    assert(!ConfineRun(&self,4,0));
    bot.targetSlot=0; assert(!ConfineRun(&self,2.5f,0)); bot.targetSlot=-1;
    assert(!ConfineRun(&self,4,0) && "the window starts again after a fight");
    assert(!ConfineRun(&self,60,1.0f)); self.position=(rdVector3){0,0,0};
    /* More than 45 quiet seconds later the escalation starts over. */
    assert(ConfineRun(&self,8,0) && bot.confine.strikes==1);
    /* In water a fight is no excuse, and the escape heads for air. */
    self.sector=&pool; bot.targetSlot=0; nav.diveEscape=BOT_DIVE_NONE;
    bot.goal=2; bot.route[0]=2; bot.routeCount=1; bot.routePos=0;
    nav.waterExitUntil=bot.now+3; nav.waterExitTo=1; bot.nodes[1].avoidUntil=0;
    assert(ConfineRun(&self,8,0) && bot.confine.strikes==2 && nav.diveEscape==BOT_DIVE_AIR);
    assert(nav.waterExitUntil==0 && bot.nodes[1].avoidUntil>bot.now+20 && "the failing exit is set aside");
    /* The legacy column leaves the check off and routine avoids as plain assignments. */
    TacticsUse(1); bot.targetSlot=-1; self.sector=&land; bot.goal=2;
    assert(!ConfineRun(&self,20,0));
    bot.nodes[1].avoidUntil=bot.now+60; Bot_AvoidNode(&bot.nodes[1],5);
    assert(fabsf(bot.nodes[1].avoidUntil-(bot.now+5))<0.01f);
    puts("PASS confinement window, doubling and widening escapes, legitimate holds, quiet reset, wet escape to air and legacy off");
}

/* Ordnance: a laid charge or a resting grenade is a hazard the planner
   steers around and the bot steps away from; a charge in hand is laid as a
   proximity mine on a guarded item spot just taken. */
static void test_tactic_ordnance(void)
{
    static SithWorld world; static SithThing things[3]; static SithThing blast;
    SithThing self; SithPlayer own;
    int seq=SITHBIN_SEQUENCER_CHARGE, select=INPUT_FUNC_SELECT1+SITHBIN_SEQUENCER_CHARGE-1;
    testPlainActive=1; plainEdge=plainWall=1e9f; plainGround.flags=0;
    jkBot_Configure("Mine_Test","ky.3do"); TacticsUse(0); bot.now=5; jkPlayer_maxPlayers=0;
    PlainSelf(&self,&own); sithPlayer_g_pLocalPlayerThing=&self;
    memset(things,0,sizeof(things)); memset(&blast,0,sizeof(blast));
    blast.type=SITH_THING_EXPLOSION; blast.explosionParams.range=0.6f;
    bot.world=sithWorld_g_pCurrentWorld=&world; world.aThings=things; world.numThings=0; world.numThingsLoaded=1;
    bot.graphDone=1; bot.nNodes=3;
    for (int i=0;i<3;i++) {
        memset(&bot.nodes[i],0,sizeof(bot.nodes[i]));
        bot.nodes[i].pos=(rdVector3){i*1.0f,0,BOT_FOOT_HEIGHT}; bot.nodes[i].sector=&plainLand; bot.nodes[i].item=-1;
    }
    /* A charge someone laid at node 1: a mine (sixty seconds of life). */
    SithThing *mine=&things[0];
    mine->type=SITH_THING_WEAPON; mine->sector=&plainLand; mine->position=bot.nodes[1].pos;
    mine->weaponParams.pExplosionTemplate=&blast; mine->msecLifeLeft=59000; mine->collideSize=0.01f;
    BotHazard h; assert(Bot_HazardOf(mine,&h) && h.mine && h.trigger==0.30f && !h.own);
    mine->physicsParams.vel.x=2; assert(!Bot_HazardOf(mine,&h) && "in flight is the dodge's business");
    mine->physicsParams.vel.x=0;
    nav.nextHazardScan=0; Bot_ScanHazards(&self);
    assert(nav.nHazards==1 && bot.nodes[1].avoidUntil>bot.now && bot.nodes[0].avoidUntil<=bot.now);
    assert(Bot_EdgeHazard(bot.nodes[0].pos,bot.nodes[2].pos) && "a leg across the mine");
    assert(!Bot_EdgeHazard(bot.nodes[0].pos,(rdVector3){0,2,BOT_FOOT_HEIGHT}));
    /* Standing beside it: step clear. Far from it: nothing to do. */
    self.position=(rdVector3){0.75f,0,BOT_FOOT_HEIGHT}; memset(bot.axes,0,sizeof(bot.axes));
    assert(Bot_EscapeHazard(&self) && bot.axes[INPUT_FUNC_FORWARD]<-0.1f && "backs away along -x");
    self.position=bot.nodes[0].pos; assert(!Bot_EscapeHazard(&self));
    /* A thermal on its fuse is avoided by its blast, for the fuse. */
    mine->msecLifeLeft=2000; assert(Bot_HazardOf(mine,&h) && !h.mine && fabsf(h.fuse-2)<0.001f);
    TacticsUse(1); nav.nextHazardScan=0; Bot_ScanHazards(&self); assert(nav.nHazards==0 && "legacy ignores them");
    TacticsUse(0); mine->type=SITH_THING_FREE; nav.nextHazardScan=0; Bot_ScanHazards(&self); assert(!nav.nHazards);
    for (int i=0;i<3;i++) bot.nodes[i].avoidUntil=0;
    puts("PASS laid mines and fused grenades: hazards for plans, legs and footing; flight and the legacy table excluded");

    /* Taking a shield that respawns, with charges in hand: lay a mine there. */
    SithThing *shield=&things[1];
    shield->type=SITH_THING_ITEM; shield->sector=&plainLand; shield->guid=77; strcpy(shield->aName,"shieldrecharge");
    shield->itemParams.secRespawnInterval=30; shield->position=self.position;
    world.numThings=1; world.numThingsLoaded=2;
    own.aItems[seq].amount=2; own.aItems[seq].state=SITHINVENTORY_ITEM_AVAILABLE; own.curWeaponID=SITHBIN_BRYARPISTOL;
    memset(bot.keys,0,sizeof(bot.keys));
    assert(!Bot_MineTick(&self,NULL) && nav.watchItem==2);
    shield->flags|=SITH_TF_DISABLED;               /* picked up */
    assert(Bot_MineTick(&self,NULL) && nav.minePhase==1 && bot.keys[select]);
    assert(Bot_SelectWeapon(&self,2)==SITHBIN_BRYARPISTOL && "laying owns the selection");
    memcpy(bot.previous,bot.keys,sizeof(bot.keys)); memset(bot.keys,0,sizeof(bot.keys));
    own.curWeaponID=seq; bot.now+=0.3f; assert(Bot_MineTick(&self,NULL) && nav.minePhase==2);
    bot.now+=0.2f; assert(Bot_MineTick(&self,NULL)); assert(nav.minePhase==2);
    bot.now+=0.3f; assert(Bot_MineTick(&self,NULL) && nav.minePhase==3 && bot.keys[INPUT_FUNC_FIRE2] && !bot.keys[INPUT_FUNC_FIRE1]);
    own.aItems[seq].amount=1; bot.now+=0.1f;
    assert(!Bot_MineTick(&self,NULL) && !nav.minePhase && bot.tele.mines==1 && Bot_OwnMines()==1);
    puts("PASS a charge in hand is laid as a mine on a guarded item spot just taken: select, raise, secondary, counted");

    /* Not in a fight, not without a fresh pickup, not in the legacy table. */
    shield->flags=0; nav.watchItem=0; Bot_MineTick(&self,NULL); shield->flags|=SITH_TF_DISABLED;
    SithThing enemy={0}; testLOS=1;
    assert(!Bot_MineTick(&self,&enemy) && !nav.minePhase && "a visible enemy comes first");
    bot.now+=2; assert(!Bot_MineTick(&self,NULL) && !nav.minePhase && "the spot is stale");
    TacticsUse(1); shield->flags=0; nav.watchItem=0; Bot_MineTick(&self,NULL); assert(!nav.watchItem);
    TacticsUse(0); memset(nav.ownMines,0,sizeof(nav.ownMines)); nav.minePhase=0; nav.watchItem=0;
    bot.world=sithWorld_g_pCurrentWorld=NULL; sithPlayer_g_pLocalPlayerThing=NULL; testPlainActive=0;
    puts("PASS no mine in a fight, from a stale spot, or with the legacy table");
}

/* Thermals: the throw is flown as the engine flies it, held for the range
   and released along the arc that lands by the target. */
static void test_tactic_thermal(void)
{
    static SithWorld world; static SithThing grenade, blast;
    SithThing self, target; SithPlayer own, foe; jkPlayerInfo remote={0}; rdModel3 gun={0};
    int det=SITHBIN_THERMAL_DETONATOR;
    testPlainActive=1; plainEdge=plainWall=1e9f; plainGround.flags=0; plainSolidFloor=1;
    jkBot_Configure("Thermal_Test","ky.3do"); TacticsUse(0); bot.now=5; bot.fistsPeace=0; bot.elite=1;
    PlainSelf(&self,&own); PlainSelf(&target,&foe); sithPlayer_g_pLocalPlayerThing=&self;
    memset(&world,0,sizeof(world)); world.gravity=4.0f; bot.world=sithWorld_g_pCurrentWorld=&world;
    memset(&blast,0,sizeof(blast)); blast.type=SITH_THING_EXPLOSION; blast.explosionParams.range=0.45f;
    memset(&grenade,0,sizeof(grenade)); grenade.type=SITH_THING_WEAPON; grenade.moveSize=0.0149f;
    grenade.weaponParams.flags=SITH_WF_FACEHITEXPLODE|SITH_WF_THINGHITEXPLODE; grenade.weaponParams.pExplosionTemplate=&blast;
    grenade.physicsParams.vel=(rdVector3){0,2.0f,1.5f}; grenade.physicsParams.airDrag=0.8f;
    grenade.physicsParams.flags=SITH_PF_USEGRAVITY; testGrenade=&grenade;
    /* The solver flies it: a 1.6 s hold reaches two units on the flat. */
    BotArc arc=Bot_ThermalArc(&self,(rdVector3){2,0,0.02f},1.6f);
    assert(arc.ok && arc.miss<0.27f && fabsf(arc.impact.x-2)<0.27f && arc.flight>0.5f && arc.flight<1.5f);
    arc=Bot_ThermalArc(&self,(rdVector3){3,0,0.02f},0.7f); assert(!arc.ok && "the shortest hold falls short");
    arc=Bot_ThermalArc(&self,(rdVector3){0.4f,0,0.02f},1.0f); assert(!arc.ok && "never at its own feet");
    puts("PASS thermal arcs are flown as the engine flies them: the hold sets the reach, never at the thrower's feet");

    /* A target standing still at 2.2 units, in view. */
    target.position=(rdVector3){2.2f,0,BOT_FOOT_HEIGHT}; target.playerInfo=&remote; remote.rd_thing.model3=&gun;
    strcpy(gun.filename,"strg.3do"); target.guid=55; target.signature=3;
    jkPlayer_maxPlayers=2; jkPlayer_playerInfos[1].flags=1; jkPlayer_playerInfos[1].playerNetId=55;
    jkPlayer_playerInfos[1].pLocalPlayer=&target; testLOS=1;
    own.aItems[det].amount=2; own.aItems[det].state=SITHINVENTORY_ITEM_AVAILABLE; own.curWeaponID=SITHBIN_BRYARPISTOL;
    memset(bot.keys,0,sizeof(bot.keys)); memset(bot.previous,0,sizeof(bot.previous));
    TacticsUse(1); assert(!Bot_ThermalTick(&self,&target) && "legacy never throws");
    TacticsUse(0);
    target.physicsParams.vel.y=1.2f; assert(!Bot_ThermalWorth(&self,&target) && "a fast target in the open: guns");
    target.physicsParams.vel.y=0; assert(Bot_ThermalWorth(&self,&target));
    assert(Bot_ThermalTick(&self,&target) && nav.thermalPhase==1 && bot.keys[INPUT_FUNC_SELECT1+det-1]);
    assert(Bot_SelectWeapon(&self,2)==SITHBIN_BRYARPISTOL && "the throw owns the selection");
    own.curWeaponID=det; memset(bot.keys,0,sizeof(bot.keys));
    bot.now+=0.1f; assert(Bot_ThermalTick(&self,&target) && nav.thermalPhase==1);
    bot.now+=0.5f; assert(Bot_ThermalTick(&self,&target) && nav.thermalPhase==2 && bot.keys[INPUT_FUNC_FIRE1]);
    flex_t hold=nav.thermalHold; assert(hold>=0.7f && hold<2.0f);
    /* Held for the planned time; turned onto the arc; then released. */
    bot.now+=hold*0.5f; assert(Bot_ThermalTick(&self,&target) && bot.keys[INPUT_FUNC_FIRE1]);
    self.actorParams.headPYR.x=nav.thermalArc.pitch; bot.now+=hold*0.5f+0.01f;
    assert(Bot_ThermalTick(&self,&target) && !bot.keys[INPUT_FUNC_FIRE1] && nav.thermalPhase==3);
    assert(Bot_Distance(nav.thermalArc.impact,target.position)<0.45f);
    own.aItems[det].amount=1; bot.now+=0.1f;
    assert(!Bot_ThermalTick(&self,&target) && !nav.thermalPhase && bot.tele.thermals==1);
    /* Five seconds before the next, and none at close quarters. */
    own.curWeaponID=SITHBIN_BRYARPISTOL; bot.now+=1; assert(!Bot_ThermalTick(&self,&target));
    bot.now+=5; target.position.x=1.0f; assert(!Bot_ThermalTick(&self,&target) && !nav.thermalPhase);
    puts("PASS a thermal is thrown at a still target in reach: select, hold for the range, turn onto the arc, release");
    testGrenade=NULL; plainSolidFloor=0; testPlainActive=0; jkPlayer_maxPlayers=0;
    memset(&jkPlayer_playerInfos[1],0,sizeof(jkPlayer_playerInfos[1]));
    bot.world=sithWorld_g_pCurrentWorld=NULL; sithPlayer_g_pLocalPlayerThing=NULL;
}

static void test_bot_tactics(void)
{
    /* Earlier groups leave peers that pointed into their own stack frames. */
    jkPlayer_maxPlayers=0; memset(jkPlayer_playerInfos,0,sizeof(jkPlayer_playerInfos));
    test_tactic_table();
    test_tactic_thrust();
    test_tactic_run();
    test_tactic_route_run();
    test_tactic_water();
    test_tactic_swim();
    test_tactic_runjump();
    test_tactic_use();
    test_tactic_ordnance();
    test_tactic_thermal();
    test_tactic_confinement();
}
