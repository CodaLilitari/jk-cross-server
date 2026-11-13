/* Small C1 entrance fixture: lobby, short throat, corridor and trigger shaft.
 * This is a controlled geometry model, not an emulation of the whole map. */
static int testC1Active;
static SithSector testC1Sectors[4];
static SithSurface testC1Floors[4];
static const rdVector3 testC1Minimum[4]={
    {-1.2f,-7.199999f,0.9f},{-0.7f,-7.3f,0.9f},{-0.7f,-7.599999f,0.9f},{-0.9f,-8.2f,-0.6f}};
static const rdVector3 testC1Maximum[4]={
    {1.2f,-5.3f,1.3f},{-0.5f,-7.199999f,1.3f},{-0.5f,-7.3f,1.3f},{-0.3f,-7.599999f,1.4f}};

static int TestC1Sphere(const rdVector3 *p, flex_t radius, SithSector *sector)
{
    for (int i=0;i<4;i++) if (sector==&testC1Sectors[i]) {
        rdVector3 lo=testC1Minimum[i], hi=testC1Maximum[i];
        /* Match the engine's plane-distance comparison; subtracting radius
           from the coordinate instead rounds this boundary differently. */
        return p->x-lo.x>=radius && hi.x-p->x>=radius &&
            p->y-lo.y>=radius && hi.y-p->y>=radius && p->z-lo.z>=radius && hi.z-p->z>=radius;
    }
    return 0;
}

static SithSector *TestC1Sector(const rdVector3 *p)
{
    for (int i=0;i<4;i++) if (TestC1Sphere(p,0,&testC1Sectors[i])) return &testC1Sectors[i];
    return NULL;
}

static int TestC1ClearPoint(rdVector3 p, flex_t radius)
{
    /* Connected portal planes do not themselves obstruct a collision sweep. */
    const rdVector3 offsets[7]={{0,0,0},{1,0,0},{-1,0,0},{0,1,0},{0,-1,0},{0,0,1},{0,0,-1}};
    for (int i=0;i<7;i++) {
        rdVector3 q={p.x+offsets[i].x*radius,p.y+offsets[i].y*radius,p.z+offsets[i].z*radius};
        if (!TestC1Sector(&q)) return 0;
    }
    return 1;
}

static int TestC1Collision(SithSector *sector, const rdVector3 *from, const rdVector3 *direction,
                           flex_t distance, flex_t radius, SithCollision *hit)
{
    memset(hit,0,sizeof(*hit));
    int id=-1;
    for (int i=0;i<4;i++) if (sector==&testC1Sectors[i]) id=i;
    if (id<0) return 0;
    testC1Floors[id].pSector=sector;
    testC1Floors[id].flags=SITH_SURFACE_HAS_COLLISION|SITH_SURFACE_FLOOR;
    hit->type=SITHCOLLISION_WORLD; hit->surface=&testC1Floors[id];
    if (direction->z < -0.99f && radius==0 && id<3 && from->z>=0.9f && from->z-distance<=0.9f) {
        hit->distance=from->z-0.9f; hit->hitNorm.z=1; return 1;
    }
    int steps=(int)ceilf(distance/0.02f);
    for (int i=0;i<=steps;i++) {
        flex_t along=steps ? distance*i/steps : 0;
        rdVector3 p={from->x+direction->x*along,from->y+direction->y*along,from->z+direction->z*along};
        if (!TestC1ClearPoint(p,radius)) { hit->distance=along; return 1; }
    }
    return 0;
}
