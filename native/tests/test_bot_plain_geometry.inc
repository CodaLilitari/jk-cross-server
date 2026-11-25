/* Open flat ground at z=0 for movement checks: the floor ends at plainEdge
   and a wall stands at plainWall, both measured along +x. A shelf, when set,
   raises the floor to plainShelfZ from plainShelf onward behind a sheer face. */
static int testPlainActive;
static flex_t plainEdge=1e9f, plainWall=1e9f, plainShelf=1e9f, plainShelfZ;
static int plainSolidFloor; /* slanted rays meet the floor too (thrown grenades) */
static SithSurface *plainWallSurface; /* what the wall at plainWall is, when it is a switch */
/* A force field across the ground at x=plainField: while it is on, nothing
   whose swept body touches the plane gets through; switched off, it is air. */
static flex_t plainField=1e9f; static int plainFieldOn;
/* A door lying flat as the floor under the origin: a slanted ray down onto
   the ground meets it rather than the world (dead_end). */
static SithThing *plainFloorThing;
/* A wall across the ground at x=plainSlotX with an opening from y=plainSlotLo
   to plainSlotHi: a door alcove's mouth (leg_axis). */
static flex_t plainSlotX=1e9f, plainSlotLo, plainSlotHi;
static SithSector plainLand, plainPool;
static SithSurface plainGround;

/* A pool variant for pickups in water: below plainPoolSurface every point
   is in plainPool, above it in plainLand, and a sphere fits the pool while
   it stays clear of the pool floor and of the surface. A ray down onto the
   surface from the air meets the water. */
static int plainPoolActive; static flex_t plainPoolFloor, plainPoolSurface=1e9f;
static SithSurface plainWaterTop;
static int TestPlainSphere(const rdVector3 *p,flex_t radius,SithSector *sector)
{
    if (plainPoolActive && p->z>plainPoolSurface) return sector==&plainLand && radius==0;
    if (plainPoolActive) return sector==&plainPool && p->z-radius>=plainPoolFloor+0.0005f &&
                                p->z+radius<=plainPoolSurface-0.0005f;
    return sector==&plainLand;
}
static SithSector *TestPlainSector(const rdVector3 *p)
{
    return plainPoolActive && p->z<=plainPoolSurface ? &plainPool : &plainLand;
}

static int TestPlainCollision(const rdVector3 *from,const rdVector3 *direction,
                              flex_t distance,flex_t radius,SithCollision *hit)
{
    rdVector3 end={from->x+direction->x*distance,from->y+direction->y*distance,
                   from->z+direction->z*distance};
    memset(hit,0,sizeof(*hit));
    hit->type=SITHCOLLISION_WORLD; hit->surface=&plainGround;
    plainGround.pSector=&plainLand;
    plainGround.flags|=SITH_SURFACE_HAS_COLLISION|SITH_SURFACE_FLOOR;
    if (direction->z<-0.99f) {
        if (plainPoolActive && from->z>plainPoolSurface && end.z<=plainPoolSurface) {
            plainWaterTop.flags=SITH_SURFACE_WATER; plainWaterTop.pSector=&plainLand;
            hit->surface=&plainWaterTop; hit->distance=from->z-plainPoolSurface; hit->hitNorm.z=1;
            return 1;
        }
        flex_t floor=from->x>=plainShelf ? plainShelfZ : 0;
        /* A shelf past the edge stands across a gap. */
        if ((from->x>=plainEdge && from->x<plainShelf) || from->z<floor || end.z>floor) return 0;
        hit->distance=from->z-floor; hit->hitNorm.z=1;
        return 1;
    }
    if (plainFieldOn && Bot_Min(from->x,end.x)-radius<plainField && Bot_Max(from->x,end.x)+radius>plainField) {
        hit->distance=0; hit->hitNorm.x=from->x<plainField ? -1 : 1;
        return 1;
    }
    if (plainSlotX<1e8f && Bot_Min(from->x,end.x)-radius<plainSlotX && Bot_Max(from->x,end.x)+radius>plainSlotX) {
        /* As the engine's own sweep: a body moving toward the wall is
           stopped where it first touches the wall's plane if that point
           lies within its radius of the solid part, corners included (on
           Bespin a slant onto an opening's line from against the wall
           beside it is stopped at the corner); a body already touching the
           plane is judged where it stands, and moving along the wall or
           away from it is free. Where the body is centred on the plane,
           the most of it lies across the plane: it must fit the opening
           there too. */
        flex_t dx=end.x-from->x, side=from->x<plainSlotX ? 1.0f : -1.0f;
        int toward=dx*side>1e-6f, crosses=toward && (plainSlotX-from->x)/dx<=1;
        flex_t edge=plainSlotX-side*radius;
        flex_t first=toward ? Bot_Clamp((edge-from->x)/dx,0,1) : 0;
        flex_t t=crosses ? (plainSlotX-from->x)/dx : 0;
        flex_t y=from->y+(end.y-from->y)*t, y0=from->y+(end.y-from->y)*first;
        if ((toward && (y0-radius<plainSlotLo || y0+radius>plainSlotHi)) ||
            (crosses && (y-radius<plainSlotLo || y+radius>plainSlotHi))) {
            /* Reported where the body's edge first reaches the wall. */
            hit->distance=distance*first; hit->hitNorm.x=-side;
            return 1;
        }
    }
    if (Bot_Max(from->x,end.x)+radius>plainWall) {
        hit->hitNorm.x=-1;
        if (plainWallSurface) hit->surface=plainWallSurface;
        return 1;
    }
    if (plainShelf<1e8f) {
        /* Sample the swept body against the shelf's face and top. */
        int steps=(int)ceilf(distance/0.005f);
        for (int i=0;i<=steps;i++) {
            flex_t along=steps ? distance*i/steps : 0;
            flex_t x=from->x+direction->x*along, z=from->z+direction->z*along;
            if (x+radius>plainShelf && z-radius<plainShelfZ) {
                hit->distance=along; hit->hitNorm.x=-1; return 1;
            }
        }
    }
    if (plainFloorThing && direction->z<-0.5f && end.z-radius<0 && from->z>=0) {
        hit->type=SITHCOLLISION_THING; hit->surface=NULL; hit->pThingCollided=plainFloorThing;
        hit->distance=from->z/-direction->z; hit->hitNorm.z=1;
        return 1;
    }
    if (plainSolidFloor && direction->z<0 && end.z-radius<0 && from->z-radius>=0) {
        hit->distance=(from->z-radius)/-direction->z; hit->hitNorm.z=1;
        return 1;
    }
    return 0;
}
