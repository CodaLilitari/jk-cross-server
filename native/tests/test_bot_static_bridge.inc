/* A bounded two-sector pad/bridge model. The bridge mesh slightly overhangs
 * its owning sector, as stock boss15 does; this is not a whole-map emulator. */
static int testBridgeActive;
static SithSector testBridgeSectors[2];
static SithThing testBridgeThings[2];
static const flex_t testBridgeBoundary=8.099998f;

static int TestBridgeSphere(const rdVector3 *p, flex_t radius, SithSector *sector)
{
    if (p->z-27.0f<radius || 30.0f-p->z<radius) return 0;
    if (sector==&testBridgeSectors[0])
        return p->x-38.0f>=radius && 41.0f-p->x>=radius &&
            p->y-testBridgeBoundary>=radius && 11.0f-p->y>=radius;
    if (sector==&testBridgeSectors[1])
        return p->x-39.1f>=radius && 39.9f-p->x>=radius &&
            p->y-3.2f>=radius && testBridgeBoundary-p->y>=radius;
    return 0;
}

static SithSector *TestBridgeSector(const rdVector3 *p)
{
    for (int i=0;i<2;i++) if (TestBridgeSphere(p,0,&testBridgeSectors[i])) return &testBridgeSectors[i];
    return NULL;
}

static int TestBridgeCollision(SithSector *sector, const rdVector3 *from,
    const rdVector3 *direction, flex_t distance, flex_t radius, int flags, SithCollision *hit)
{
    /* A downward point query tests only things stored in its current sector
       unless the engine's adjacent-sector thing search is requested. */
    if (radius!=0 || direction->z>-0.99f || (flags&RAYCAST_1)) return 0;
    const flex_t loX[2]={38.2f,39.275197f}, hiX[2]={40.75f,39.674799f};
    const flex_t loY[2]={8.120383f,3.385086f}, hiY[2]={10.8f,8.120105f};
    const flex_t height[2]={28.598123f,28.599879f};
    for (int i=0;i<2;i++) {
        SithThing *thing=&testBridgeThings[i];
        if (thing->sector!=sector && !(flags&RAYCAST_800)) continue;
        if (thing->flags&(SITH_TF_DISABLED|SITH_TF_DESTROYED)) continue;
        if (from->x<loX[i] || from->x>hiX[i] || from->y<loY[i] || from->y>hiY[i] ||
            from->z<height[i] || from->z-distance>height[i]) continue;
        memset(hit,0,sizeof(*hit)); hit->type=SITHCOLLISION_THING;
        hit->pThingCollided=thing; hit->hitNorm.z=1; hit->distance=from->z-height[i];
        return 1;
    }
    return 0;
}
