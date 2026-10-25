/* Bounded central strip through stock C1 sector117, surface1274. Its floor
 * vertices rise from y=.500002,z=0 to y=.200000,z=.300000; the authored
 * normal is (0,.707104,.707109). This is a controlled geometric fixture,
 * not a simulation of the whole CTF map or a traversal result. */
static int testSlopeActive, testSlopeGap, testSlopeStep, testSlopeDrop;
static flex_t testSlopeCeiling=0.9f, testSlopeWall;
static SithSector testSlopeSector;
static SithSurface testSlopeSurface;

static flex_t TestSlopeHeight(flex_t y)
{
    if (testSlopeDrop) return y<0.45f ? -0.2f*testSlopeDrop : 0;
    flex_t height=Bot_Clamp((0.500002f-y)*(0.3f/0.300002f),0,0.3f);
    if (testSlopeStep && y<0.45f) height+=0.35f;
    return height;
}
static int TestSlopeSphere(const rdVector3 *p, flex_t radius, SithSector *sector)
{
    if (sector!=&testSlopeSector || p->x-radius<-3.9f || p->x+radius>-2.9f ||
        p->y-radius<0.05f || p->y+radius>0.7f || p->z+radius>testSlopeCeiling) return 0;
    if (testSlopeDrop && p->y<0.45f) {
        /* Distance to the solid upper ledge, including its exposed corner. */
        flex_t dy=0.45f-p->y, dz=Bot_Max(0,p->z);
        if (sqrtf(dy*dy+dz*dz)<radius) return 0;
    }
    flex_t normalZ=!testSlopeDrop && p->y>0.2f && p->y<0.500002f ? 0.707109f : 1.0f;
    return (p->z-TestSlopeHeight(p->y))*normalZ>=radius;
}
static SithSector *TestSlopeSectorAt(const rdVector3 *p)
{ return TestSlopeSphere(p,0,&testSlopeSector) ? &testSlopeSector : NULL; }
static int TestSlopeCollision(const rdVector3 *from, const rdVector3 *direction,
                             flex_t distance, flex_t radius, SithCollision *hit)
{
    memset(hit,0,sizeof(*hit)); hit->type=SITHCOLLISION_WORLD;
    hit->surface=&testSlopeSurface; testSlopeSurface.pSector=&testSlopeSector;
    testSlopeSurface.flags=SITH_SURFACE_HAS_COLLISION|SITH_SURFACE_FLOOR;
    if (radius==0 && direction->z<-0.99f) {
        if (testSlopeGap && from->y<0.43f) return 0;
        flex_t floor=TestSlopeHeight(from->y);
        if (from->z<floor || from->z-distance>floor) return 0;
        hit->distance=from->z-floor;
        hit->hitNorm=!testSlopeDrop && from->y>0.2f && from->y<0.500002f ?
            (rdVector3){0,0.707104f,0.707109f} : (rdVector3){0,0,1};
        return 1;
    }
    /* Sample the bounded swept body against floor, ceiling and an optional
       blocking wall; the plane comparison uses perpendicular separation. */
    int steps=(int)ceilf(distance/0.005f);
    for (int i=0;i<=steps;i++) {
        flex_t along=steps ? distance*i/steps : 0;
        rdVector3 p={from->x+direction->x*along,from->y+direction->y*along,
                     from->z+direction->z*along};
        if (!TestSlopeSphere(&p,radius,&testSlopeSector) ||
            (testSlopeWall && p.y-radius<=testSlopeWall)) {
            hit->distance=along; return 1;
        }
    }
    return 0;
}
static void test_bot_slope_steering(void)
{
    SithWorld world={0}; SithThing self={0};
    jkBot_Configure("Bot_Slope","ky.3do");
    world.aSectors=&testSlopeSector; world.numSectors=1; bot.world=&world;
    testSlopeSector=(SithSector){0}; testSlopeActive=1;
    testSlopeGap=testSlopeStep=testSlopeDrop=0; testSlopeCeiling=0.9f; testSlopeWall=0;
    corridorMode=fixtureMode=0;
    self.type=SITH_THING_PLAYER; self.collideSize=0.065f; self.sector=&testSlopeSector;
    self.position=(rdVector3){-3.400004f,0.500002f,BOT_FOOT_HEIGHT};
    rdVector3 horizontal=self.position, down={0,0,-1}, blocked, floor;
    SithSector *sector=NULL;
    horizontal.y-=0.2f;
    assert(!Bot_Clear(&self,self.sector,self.position,horizontal,self.collideSize*0.85f,0));
    horizontal.z+=0.02f;
    assert(!Bot_Floor(horizontal,self.sector,0.43f,&floor,&sector));
    assert(Bot_SafeDirection(&self,down,0,0.3f,&blocked)==0); /* No horizontal input. */
    assert(Bot_SafeDirection(&self,(rdVector3){0,-1,0},0,0.3f,&blocked));
    for (int i=1;i<=5;i++) {
        self.position.y=0.500002f-i*0.05f;
        self.position.z=TestSlopeHeight(self.position.y)+BOT_FOOT_HEIGHT;
        assert(Bot_SafeDirection(&self,(rdVector3){0,-1,0},0,self.position.y-0.2f,&blocked));
    }
    self.position=(rdVector3){-3.400004f,0.500002f,BOT_FOOT_HEIGHT};
    self.physicsParams.vel=(rdVector3){0,-1.2f,0};
    assert(Bot_SafeDirection(&self,(rdVector3){0,-1,0},0,0.4f,&blocked));
    self.physicsParams.vel=(rdVector3){0,0,0};
    testSlopeCeiling=0.20f;
    assert(!Bot_SafeDirection(&self,(rdVector3){0,-1,0},0,0.3f,&blocked));
    testSlopeCeiling=0.9f; testSlopeWall=0.4f;
    assert(!Bot_SafeDirection(&self,(rdVector3){0,-1,0},0,0.3f,&blocked));
    testSlopeWall=0; testSlopeGap=1;
    assert(!Bot_SafeDirection(&self,(rdVector3){0,-1,0},0,0.3f,&blocked));
    testSlopeGap=0; testSlopeStep=1;
    assert(!Bot_SafeDirection(&self,(rdVector3){0,-1,0},0,0.3f,&blocked));
    testSlopeStep=0;
    testSlopeDrop=1;
    assert(Bot_SafeDirection(&self,(rdVector3){0,-1,0},0,0.3f,&blocked));
    testSlopeDrop=2;
    assert(!Bot_SafeDirection(&self,(rdVector3){0,-1,0},0,0.3f,&blocked));
    assert(Bot_SafeDirection(&self,(rdVector3){0,-1,0},1,0.3f,&blocked));
    testSlopeDrop=0;
    self.position=(rdVector3){-3.400004f,0.2f,0.3f+BOT_FOOT_HEIGHT};
    assert(Bot_SafeDirection(&self,(rdVector3){0,1,0},0,0.3f,&blocked));
    assert(queryDepth==0); testSlopeActive=0;
    jkBot_Configure("Bot_Reset","ky.3do");
    puts("PASS authored C1 ramp follows supported ground; ceiling, wall, void and excessive rise rejected");
}
