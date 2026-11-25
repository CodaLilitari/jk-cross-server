/* Actual engine sphere/face collision regression for a narrow angled portal.
 * Two synthetic convex sectors preserve the C3 corridor's measured dimensions.
 * No retail map data, game session, live state writes, or rendering is needed. */
#include <assert.h>
#include <stdarg.h>
#ifndef JKBOT_TEST_NEW_DEFAULTS
#define JKBOT_TACTICS_BASELINE_LEGACY 1
#endif
#include "AI/jkBot.c"
#ifdef NDEBUG
#error Assertions must remain enabled for the portal regression
#endif
/* Use stock world collision and sphere intersections. Mesh fixtures require
 * model data and are outside the scope of this test. */
#define sithIntersect_CheckSphereThingIntersection TestUnusedThingIntersection
#include "Engine/sithIntersect.c"
#undef sithIntersect_CheckSphereThingIntersection
#include "Engine/sithCollision.c"

uint32_t jkPlayer_maxPlayers;
int32_t sithNet_MultiModeFlags;
SithPlayer jkPlayer_playerInfos[JKPLAYER_NUM_INFOS];
SithThing *sithPlayer_g_pLocalPlayerThing;
SithWorld *sithWorld_g_pCurrentWorld;
int sithCollision_aNumSearchedSectors[4];
SithCollideResult sithCollision_collisionHandlers[144];
sithCollisionSearchResult sithCollision_aCollisions[4];
int sithCollision_aNumStackCollisions[4];
int sithCollision_searchStackIdx=-1;
sithCollisionSectorEntry sithCollision_apSearchedSectors[4];
static void test_assert(const char *condition,const char *file,int line)
{ fprintf(stderr,"Engine assertion: %s at %s:%d\n",condition,file,line); abort(); }
static HostServices test_host={.assert=test_assert};
HostServices *pSithHS=&test_host;
int jk_printf(const char *fmt,...)
{ va_list ap; va_start(ap,fmt); int result=vfprintf(stderr,fmt,ap); va_end(ap); return result; }
int sithIntersect_CheckSphereThingIntersection(SithThing *thing,const rdVector3 *start,
    const rdVector3 *direction,flex_t distance,flex_t radius,SithThing *other,int flags,
    flex_t *hit,rdMesh **mesh,rdFace **face,rdVector3 *normal)
{
    assert(!thing && other->collide==SITH_COLLIDE_SPHERE);
    *mesh=NULL; *face=NULL;
    if (!sithIntersect_CheckSphereIntersection(start,direction,distance,radius,
            &other->position,other->collideSize,hit,0,flags)) return 0;
    *normal=Bot_Sub(*start,other->position);
    rdVector_ScaleAdd3Acc(normal,direction,*hit);
    rdVector_Normalize3Acc(normal);
    return SITHCOLLISION_THING;
}
flex_t sithInventory_GetInventory(SithThing *thing,int bin)
{ return thing->actorParams.pPlayer ? thing->actorParams.pPlayer->aItems[bin].amount : 0; }

static SithWorld test_world;
#ifndef BOT_PORTAL_COLLISION_FIXTURE_ONLY
int sithInventory_GetCurrentWeapon(SithThing *thing)
{ return thing->actorParams.pPlayer ? thing->actorParams.pPlayer->curWeaponID : 0; }
int sithInventory_IsInventoryActivated(SithThing *thing,int bin)
{ return thing->actorParams.pPlayer && (thing->actorParams.pPlayer->aItems[bin].state&SITHINVENTORY_ITEM_ACTIVATED); }
int sithInventory_IsInventoryAvailable(SithThing *thing,int bin)
{ return thing->actorParams.pPlayer && (thing->actorParams.pPlayer->aItems[bin].state&SITHINVENTORY_ITEM_AVAILABLE); }

static SithSector test_sectors[3];
static SithSurface test_surfaces[24];
static SithSurfaceAdjoin test_adjoins[4];
static rdVector3 test_vertices[96];
static int32_t test_indices[24][4];

static void test_face(int index,int sector,rdVector3 normal,int a,int b,int c,int d)
{
    SithSurface *surface=&test_surfaces[index];
    surface->pSector=&test_sectors[sector];
    surface->flags=SITH_SURFACE_HAS_COLLISION|(normal.z>0.5f ? SITH_SURFACE_FLOOR : 0);
    surface->surfaceInfo.face.normal=normal;
    surface->surfaceInfo.face.numVertices=4;
    surface->surfaceInfo.face.vertexPosIdx=test_indices[index];
    test_indices[index][0]=a; test_indices[index][1]=b; test_indices[index][2]=c; test_indices[index][3]=d;
}

static void test_geometry(void)
{
    /* Counterclockwise floor polygons share an angled portal at a 90-degree
       corridor bend. A .14 inward normal offset leaves the narrow branch. */
    const rdVector3 footprints[2][4]={
        {{2.05f,2.574999f,1.95f},{2.25f,2.324999f,1.95f},{3.25f,2.324999f,1.95f},{3.25f,2.574999f,1.95f}},
        {{2.05f,0.75f,1.95f},{2.25f,0.75f,1.95f},{2.25f,2.324999f,1.95f},{2.05f,2.574999f,1.95f}}
    };
    memset(&test_world,0,sizeof(test_world)); memset(test_sectors,0,sizeof(test_sectors));
    memset(test_surfaces,0,sizeof(test_surfaces)); memset(test_adjoins,0,sizeof(test_adjoins));
    memset(&bot,0,sizeof(bot)); memset(&nav,0,sizeof(nav));
    test_world.aSectors=test_sectors; test_world.numSectors=2;
    test_world.surfaces=test_surfaces; test_world.numSurfaces=12;
    test_world.aVertices=test_vertices; test_world.numVertices=16; test_world.gravity=4;
    test_world.numThings=-1;
    bot.world=sithWorld_g_pCurrentWorld=&test_world;
    for (int i=0;i<2;i++) {
        SithSector *sector=&test_sectors[i]; sector->id=i;
        sector->surfaces=&test_surfaces[i*6]; sector->numSurfaces=6;
        sector->boundingbox_onecorner=(rdVector3){2.05f,i ? 0.75f : 2.324999f,1.95f};
        sector->boundingbox_othercorner=(rdVector3){i ? 2.25f : 3.25f,2.574999f,2.475f};
        for (int j=0;j<4;j++) {
            test_vertices[i*8+j]=footprints[i][j];
            test_vertices[i*8+j+4]=footprints[i][j]; test_vertices[i*8+j+4].z=2.475f;
        }
        int base=i*8, face=i*6;
        test_face(face,i,(rdVector3){0,0,1},base,base+1,base+2,base+3);
        test_face(face+1,i,(rdVector3){0,0,-1},base+7,base+6,base+5,base+4);
        for (int j=0;j<4;j++) {
            int next=(j+1)%4; rdVector3 edge=Bot_Sub(footprints[i][next],footprints[i][j]);
            flex_t length=Bot_Horizontal(edge);
            test_face(face+2+j,i,(rdVector3){-edge.y/length,edge.x/length,0},
                base+j,base+j+4,base+next+4,base+next);
        }
    }
    for (int i=0;i<2;i++) {
        SithSurfaceAdjoin *adjoin=&test_adjoins[i];
        adjoin->flags=SITHSURF_ADJOIN_ALLOW_MOVEMENT|SITHSURF_ADJOIN_VISIBLE;
        adjoin->sector=&test_sectors[1-i]; adjoin->mirror=&test_adjoins[1-i];
        adjoin->surface=&test_surfaces[i ? 10 : 2];
        adjoin->surface->flags=0; adjoin->surface->pAdjoin=adjoin;
        test_sectors[i].adjoins=adjoin;
    }
}

static int test_box_face(int sector,rdVector3 normal,rdVector3 a,rdVector3 b,
                         rdVector3 c,rdVector3 d)
{
    int face=test_world.numSurfaces++, vertex=test_world.numVertices;
    assert(face<24 && vertex+4<=96);
    test_vertices[vertex]=a; test_vertices[vertex+1]=b;
    test_vertices[vertex+2]=c; test_vertices[vertex+3]=d;
    test_world.numVertices+=4;
    test_face(face,sector,normal,vertex,vertex+1,vertex+2,vertex+3);
    test_sectors[sector].numSurfaces++;
    return face;
}

static int test_end_face(int sector,flex_t x,int right,flex_t low,flex_t high)
{
    flex_t y=right ? -0.30f : 0.30f;
    return test_box_face(sector,(rdVector3){right ? -1 : 1,0,0},
        (rdVector3){x,y,low},(rdVector3){x,y,high},
        (rdVector3){x,-y,high},(rdVector3){x,-y,low});
}

static void test_low_threshold(flex_t step,flex_t ceiling)
{
    /* Three synthetic rooms: a short raised threshold is narrower than the
       ordinary floor sampling interval. Its paired portals are real engine
       adjoins, and the surrounding wall pieces close the rest of each end. */
    memset(&test_world,0,sizeof(test_world)); memset(test_sectors,0,sizeof(test_sectors));
    memset(test_surfaces,0,sizeof(test_surfaces)); memset(test_adjoins,0,sizeof(test_adjoins));
    memset(&bot,0,sizeof(bot)); memset(&nav,0,sizeof(nav));
    test_world.aSectors=test_sectors; test_world.numSectors=3;
    test_world.surfaces=test_surfaces; test_world.aVertices=test_vertices;
    test_world.gravity=4; test_world.numThings=-1;
    bot.world=sithWorld_g_pCurrentWorld=&test_world;
    const flex_t x0[]={0,1,1.044f}, x1[]={1,1.044f,2};
    int portal[4];
    for (int i=0;i<3;i++) {
        SithSector *sector=&test_sectors[i]; sector->id=i;
        flex_t low=i==1 ? step : 0, high=i==1 ? ceiling : 0.5f;
        sector->surfaces=&test_surfaces[test_world.numSurfaces];
        sector->boundingbox_onecorner=(rdVector3){x0[i],-0.3f,low};
        sector->boundingbox_othercorner=(rdVector3){x1[i],0.3f,high};
        test_box_face(i,(rdVector3){0,0,1},(rdVector3){x0[i],-.3f,low},
            (rdVector3){x1[i],-.3f,low},(rdVector3){x1[i],.3f,low},(rdVector3){x0[i],.3f,low});
        test_box_face(i,(rdVector3){0,0,-1},(rdVector3){x0[i],.3f,high},
            (rdVector3){x1[i],.3f,high},(rdVector3){x1[i],-.3f,high},(rdVector3){x0[i],-.3f,high});
        test_box_face(i,(rdVector3){0,1,0},(rdVector3){x0[i],-.3f,low},
            (rdVector3){x0[i],-.3f,high},(rdVector3){x1[i],-.3f,high},(rdVector3){x1[i],-.3f,low});
        test_box_face(i,(rdVector3){0,-1,0},(rdVector3){x1[i],.3f,low},
            (rdVector3){x1[i],.3f,high},(rdVector3){x0[i],.3f,high},(rdVector3){x0[i],.3f,low});
        for (int right=0;right<2;right++) {
            flex_t x=right ? x1[i] : x0[i];
            if ((i==0 && !right) || (i==2 && right)) {
                test_end_face(i,x,right,low,high); continue;
            }
            int face=test_end_face(i,x,right,step,ceiling);
            portal[i==0 ? 0 : i==2 ? 3 : right ? 2 : 1]=face;
            if (i!=1) {
                if (step>low) test_end_face(i,x,right,low,step);
                if (ceiling<high) test_end_face(i,x,right,ceiling,high);
            }
        }
    }
    for (int i=0;i<4;i++) {
        SithSurfaceAdjoin *adjoin=&test_adjoins[i];
        SithSurface *surface=&test_surfaces[portal[i]];
        adjoin->surface=surface; adjoin->mirror=&test_adjoins[i^1];
        adjoin->sector=&test_sectors[i==0 || i==3 ? 1 : i==1 ? 0 : 2];
        adjoin->flags=SITHSURF_ADJOIN_ALLOW_MOVEMENT|SITHSURF_ADJOIN_VISIBLE;
        surface->flags=0; surface->pAdjoin=adjoin;
        adjoin->next=surface->pSector->adjoins; surface->pSector->adjoins=adjoin;
    }
}

static void test_grounded_portal_clearance(void)
{
    test_low_threshold(0.10f,0.25f);
    BotNode a={.pos={0.9f,0,BOT_FOOT_HEIGHT},.sector=&test_sectors[0]};
    BotNode b={.pos={1.5f,0,BOT_FOOT_HEIGHT},.sector=&test_sectors[2]};
    rdVector3 raisedA=a.pos,raisedB=b.pos; raisedA.z+=.065f; raisedB.z+=.065f;
    assert(!Bot_Clear(NULL,a.sector,a.pos,b.pos,.058f,1));
    assert(Bot_Clear(NULL,a.sector,raisedA,raisedB,.058f,1));
    /* A valid raised chord is not a valid standing route: at the threshold
       the required foot offset leaves only .030 units below the ceiling. */
    rdVector3 probe={1.022f,0,.20f},floor; SithSector *sector=NULL;
    assert(Bot_Floor(probe,&test_sectors[1],.4f,&floor,&sector));
    assert(sector==&test_sectors[1] && fabsf(floor.z-(.10f+BOT_FOOT_HEIGHT))<.00001f);
    assert(.25f-floor.z<.065f);
    int drop=-1;
    assert(!Bot_Walkable(&a,&b,&drop));
    bot.nodes[0]=a; bot.nodes[1]=b; bot.nNodes=2;
    assert(Bot_EdgeMode(0,1)<0 && Bot_EdgeMode(1,0)<0);
    puts("PASS narrow raised threshold rejects a false standing route despite clear raised chord");
    test_low_threshold(0,0.20f);
    assert(Bot_Walkable(&a,&b,&drop) && !drop);
    SithThing self={0}; sithPlayer_g_pLocalPlayerThing=&self;
    self.moveSize=.085f; self.collideSize=.040f;
    assert(!Bot_Walkable(&a,&b,&drop));
    self.moveSize=.065f; self.collideSize=.100f;
    assert(Bot_Walkable(&a,&b,&drop) && !drop);
    sithPlayer_g_pLocalPlayerThing=NULL;
    test_low_threshold(0.10f,0.40f);
    assert(Bot_Walkable(&a,&b,&drop) && !drop);
    assert(sithCollision_searchStackIdx==-1);
    puts("PASS ordinary low passage and supported step with headroom retain routes; query stack balanced");
}

static void test_swim_clearance(void)
{
    test_low_threshold(.10f,.21f);
    for (int i=0;i<3;i++) test_sectors[i].flags|=SITH_SECTOR_UNDERWATER;
    bot.nodes[0]=(BotNode){.pos={.9f,0,.155f},.sector=&test_sectors[0]};
    bot.nodes[1]=(BotNode){.pos={1.5f,0,.155f},.sector=&test_sectors[2]};
    bot.nNodes=2;
    SithThing self={0}; sithPlayer_g_pLocalPlayerThing=&self;
    self.moveSize=.045f;
    assert(Bot_EdgeMode(0,1)==BOT_ROUTE_SWIM);
    self.moveSize=.065f;
    assert(Bot_EdgeMode(0,1)<0 && Bot_EdgeMode(1,0)<0);
    sithPlayer_g_pLocalPlayerThing=NULL;
    puts("PASS swim portal requires clearance for the active player body");
}

/* A dry shelf above water, with a short dry shaft between the two.
   The diagonal from the shelf to the water hits the edge of the floor. */
static int test_horizontal_face(int sector,flex_t left,flex_t right,flex_t z,int upward)
{
    flex_t y=upward ? -0.3f : 0.3f;
    return test_box_face(sector,(rdVector3){0,0,upward ? 1 : -1},
        (rdVector3){left,y,z},(rdVector3){right,y,z},(rdVector3){right,-y,z},(rdVector3){left,-y,z});
}

/* A repeatable launch in this synthetic pool touches down at x ~= .1957.
   Moving only the graph anchor along the same heading keeps the flight fixed. */
static void test_supported_bank_walk(SithThing self,BotNode wet,BotNode dry,
                                     int anchorFloor,int landingFloor,int ceiling)
{
    self.position=(rdVector3){.4694f,0,-.075f};
    self.field_48=.025f;
    self.physicsParams.vel.z=0;
    self.physicsParams.flags|=SITH_PF_ONWATERSURFACE;
    flex_t speed=.3654f,flight;
    dry.pos.x=.057f; /* .139 units, within the previous allowance */
    assert(Bot_WaterLanding(&self,&wet,&dry,speed,0,&flight));
    dry.pos.x=.035f; /* .161 units on the same uninterrupted floor */
    assert(!Bot_WaterLanding(&self,&wet,&dry,speed,0,&flight));
    dry.pos.x=.037f; /* .159 units */
    assert(Bot_WaterLanding(&self,&wet,&dry,speed,0,&flight));

    BotNode touchdown=dry;
    touchdown.pos.x=.1957f;
    int drop=-1;
    assert(Bot_WalkableSpan(&touchdown,&dry,&drop,.001f) && !drop);
    test_surfaces[anchorFloor].flags|=SITH_SURFACE_WATER;
    assert(!Bot_WalkableSpan(&touchdown,&dry,&drop,.001f));
    assert(!Bot_WaterLanding(&self,&wet,&dry,speed,0,&flight));
    test_surfaces[anchorFloor].flags&=~SITH_SURFACE_WATER;

    /* The second half of the walk now drops .30 units to the floor. */
    int32_t *anchorVertex=test_surfaces[anchorFloor].surfaceInfo.face.vertexPosIdx;
    for (int i=0;i<4;i++) test_vertices[anchorVertex[i]].z=-.30f;
    assert(!Bot_WalkableSpan(&touchdown,&dry,&drop,.001f));
    assert(!Bot_WaterLanding(&self,&wet,&dry,speed,0,&flight));
    for (int i=0;i<4;i++) test_vertices[anchorVertex[i]].z=0;

    test_surfaces[landingFloor].flags|=SITH_SURFACE_WATER;
    assert(!Bot_WaterLanding(&self,&wet,&dry,speed,0,&flight));
    test_surfaces[landingFloor].flags&=~SITH_SURFACE_WATER;

    /* The apex is below .22, but the player's swept body clips the roof. */
    int32_t *roofVertex=test_surfaces[ceiling].surfaceInfo.face.vertexPosIdx;
    for (int i=0;i<4;i++) test_vertices[roofVertex[i]].z=.22f;
    assert(!Bot_WaterLanding(&self,&wet,&dry,speed,0,&flight));
    for (int i=0;i<4;i++) test_vertices[roofVertex[i]].z=.60f;
    assert(Bot_WaterLanding(&self,&wet,&dry,speed,0,&flight));
    assert(sithCollision_searchStackIdx==-1);
    puts("PASS bank walk accepts .159, rejects .161, unsafe touchdown or walk, lower floor and obstructed flight");
}

static void test_water_entry(void)
{
    test_low_threshold(0,0.5f);
    memset(test_surfaces,0,sizeof(test_surfaces)); memset(test_adjoins,0,sizeof(test_adjoins));
    memset(test_sectors,0,sizeof(test_sectors));
    test_world.numSurfaces=test_world.numVertices=0;
    int bottom[3],top[3],anchorFloor=-1,landingFloor=-1;
    for (int i=0;i<3;i++) {
        flex_t left=i ? .20f : -.40f,right=.65f,low=i==0 ? 0 : i==1 ? -.05f : -.65f;
        flex_t high=i==0 ? .6f : i==1 ? 0 : -.05f;
        SithSector *s=&test_sectors[i]; s->id=i;
        s->boundingbox_onecorner=(rdVector3){left,-.3f,low};
        s->boundingbox_othercorner=(rdVector3){right,.3f,high};
        s->surfaces=&test_surfaces[test_world.numSurfaces];
        test_end_face(i,left,0,low,high); test_end_face(i,right,1,low,high);
        test_box_face(i,(rdVector3){0,1,0},(rdVector3){left,-.3f,low},(rdVector3){left,-.3f,high},
            (rdVector3){right,-.3f,high},(rdVector3){right,-.3f,low});
        test_box_face(i,(rdVector3){0,-1,0},(rdVector3){right,.3f,low},(rdVector3){right,.3f,high},
            (rdVector3){left,.3f,high},(rdVector3){left,.3f,low});
        top[i]=test_horizontal_face(i,left,right,high,0);
        if (!i) {
            anchorFloor=test_horizontal_face(i,left,.10f,low,1);
            landingFloor=test_horizontal_face(i,.10f,.20f,low,1);
        }
        bottom[i]=test_horizontal_face(i,.20f,right,low,1);
    }
    test_sectors[2].flags=SITH_SECTOR_UNDERWATER;
    for (int i=0;i<4;i++) {
        int upper=i/2; SithSurface *p=&test_surfaces[(i%2) ? top[upper+1] : bottom[upper]];
        SithSurfaceAdjoin *a=&test_adjoins[i]; a->mirror=&test_adjoins[i^1];
        a->surface=p; a->sector=&test_sectors[(i%2) ? upper : upper+1];
        a->flags=SITHSURF_ADJOIN_ALLOW_MOVEMENT|SITHSURF_ADJOIN_VISIBLE;
        p->pAdjoin=a; p->flags=0; a->next=p->pSector->adjoins;p->pSector->adjoins=a;
    }
    BotNode dry={.pos={.08f,0,BOT_FOOT_HEIGHT},.sector=&test_sectors[0]};
    BotNode wet={.pos={.41f,0,-.2f},.sector=&test_sectors[2]};
    SithThing self={0}; self.position=dry.pos;self.sector=dry.sector;
    self.moveSize=self.collideSize=.065f; self.attach_flags=SITH_ATTACH_SURFACE;
    self.orient.lvec=(rdVector3){1,0,0};self.orient.rvec=(rdVector3){0,-1,0};
    sithPlayer_g_pLocalPlayerThing=&self;
    rdVector3 rim={.22f,0,.066f},supported;
    SithSector *rimSector=NULL;
    assert(!Bot_Floor(rim,dry.sector,.16f,&supported,&rimSector));
    assert(Bot_BankRimSupport(&self,rim,&dry,&supported));
    assert(fabsf(supported.z-BOT_FOOT_HEIGHT)<.00001f);
    /* Stock FindFloor stops at a standable sphere with no attachable face.
       A center-ray hit below the rim and a radius-only hit beside the actor
       must each prevent an apparent attachment to the shelf behind it. */
    SithThing blocker={.type=SITH_THING_COG,.flags=SITH_TF_STANDABLE,
        .collide=SITH_COLLIDE_SPHERE,.collideSize=.005f,.position={.22f,0,.008f}};
    dry.sector->pFirstThingInSector=&blocker;
    assert(!Bot_BankRimSupport(&self,rim,&dry,&supported));
    blocker.position=(rdVector3){.24f,0,.060f};
    assert(!Bot_BankRimSupport(&self,rim,&dry,&supported));
    dry.sector->pFirstThingInSector=NULL;
    assert(sithCollision_searchStackIdx==-1);
    rim.x=.30f;
    assert(!Bot_BankRimSupport(&self,rim,&dry,&supported));
    self.sector=wet.sector; self.position=wet.pos; self.attach_flags=0;
    self.actorParams.endurance=19000;
    assert(Bot_SeekSurface(&self) && nav.seekingSurface && bot.routeAim && bot.keys[INPUT_FUNC_JUMP]);
    test_adjoins[3].flags&=~SITHSURF_ADJOIN_ALLOW_MOVEMENT;
    assert(!Bot_SeekSurface(&self) && !nav.seekingSurface);
    test_adjoins[3].flags|=SITHSURF_ADJOIN_ALLOW_MOVEMENT;
    self.position=dry.pos; self.sector=dry.sector; self.attach_flags=SITH_ATTACH_SURFACE;
    self.actorParams.endurance=0; memset(bot.keys,0,sizeof(bot.keys));
    assert(!Bot_Clear(NULL,dry.sector,dry.pos,wet.pos,.045f,1));
    bot.nNodes=2;bot.nodes[0]=dry;bot.nodes[1]=wet;
    assert(Bot_EdgeMode(0,1)==BOT_ROUTE_WATER_ENTRY);
    assert(Bot_EnterWater(&self,&wet,BOT_ROUTE_WATER_ENTRY,0));
    assert(bot.axes[INPUT_FUNC_FORWARD]>0.5f && !bot.keys[INPUT_FUNC_JUMP] && !bot.keys[INPUT_FUNC_DUCK]);
    assert(Bot_Distance(self.position,dry.pos)==0);
    /* The planned first edge begins on the dry shelf ahead of the actor.
       Approaching its supported anchor is necessary from outside entry range. */
    self.position.x=-0.19f;
    BotNode actual=dry; actual.pos=self.position;
    assert(!Bot_WaterEntry(&actual,&wet));
    bot.goal=1; memset(bot.axes,0,sizeof(bot.axes));
    assert(Bot_EnterWater(&self,&wet,BOT_ROUTE_WATER_ENTRY,0));
    assert(bot.goal==1 && bot.axes[INPUT_FUNC_FORWARD]>0.5f && !bot.keys[INPUT_FUNC_JUMP]);
    assert(self.position.x==-0.19f);
    /* A valid anchor can be only 0.02 away while the actual start is just
       outside the 0.55 entry limit. Route arrival tolerance must not skip it. */
    bot.nodes[0].pos.x=-0.13f;
    self.position.x=-0.15f; actual.pos=self.position;
    assert(Bot_WaterEntry(&bot.nodes[0],&wet) && !Bot_WaterEntry(&actual,&wet));
    memset(bot.axes,0,sizeof(bot.axes));
    assert(Bot_EnterWater(&self,&wet,BOT_ROUTE_WATER_ENTRY,0));
    assert(bot.goal==1 && bot.axes[INPUT_FUNC_FORWARD]>0.5f);
    bot.nodes[0]=dry;
    /* Closing the passage must invalidate the anchor approach as well. */
    test_adjoins[2].flags&=~SITHSURF_ADJOIN_ALLOW_MOVEMENT;
    test_adjoins[3].flags&=~SITHSURF_ADJOIN_ALLOW_MOVEMENT;
    memset(bot.axes,0,sizeof(bot.axes));
    assert(Bot_EnterWater(&self,&wet,BOT_ROUTE_WATER_ENTRY,0));
    assert(bot.goal==-1 && !bot.axes[INPUT_FUNC_FORWARD]);
    test_adjoins[2].flags|=SITHSURF_ADJOIN_ALLOW_MOVEMENT;
    test_adjoins[3].flags|=SITHSURF_ADJOIN_ALLOW_MOVEMENT;
    self.position=dry.pos;
    /* The reverse edge needs real momentum before a fresh surface jump. */
    test_world.gravity=4; nav.jumpVelocity=1.5f; nav.maxRunSpeed=1;
    self.actorParams.maxThrust=2; self.actorParams.jumpSpeed=1.5f; self.physicsParams.mass=150;
    self.physicsParams.airDrag=0.5f; self.physicsParams.flags=SITH_PF_USETHRUST|SITH_PF_USEGRAVITY;
    rdVector3 swimStart; flex_t flight=0;
    /* In this opening the old 0.045-wide diagonal fits. A 0.065-radius
       player clips the rim. One direction has a physical jump; returning
       through this outside-corner approach has no verified entry. */
    bot.nodes[0].pos.x=.09f;
    bot.nodes[1].pos.x=.56f; bot.nodes[1].pos.z=-.10f;
    assert(Bot_Clear(NULL,dry.sector,bot.nodes[0].pos,bot.nodes[1].pos,.045f,1));
    assert(!Bot_WaterClear(dry.sector,bot.nodes[0].pos,bot.nodes[1].pos,self.moveSize));
    assert(Bot_EdgeMode(0,1)<0 && Bot_EdgeMode(1,0)==BOT_ROUTE_WATER_EXIT);
    bot.nodes[0].pos.x=.11f; bot.nodes[1].pos.z=-.12f;
    assert(Bot_Clear(NULL,dry.sector,bot.nodes[0].pos,bot.nodes[1].pos,.045f,1));
    assert(!Bot_WaterClear(dry.sector,bot.nodes[0].pos,bot.nodes[1].pos,self.moveSize));
    assert(Bot_EdgeMode(0,1)==BOT_ROUTE_WATER_ENTRY);
    bot.nodes[0]=dry; bot.nodes[1]=wet;
    assert(Bot_EdgeMode(1,0)==BOT_ROUTE_WATER_EXIT);
    assert(Bot_WaterExitArc(&wet,&dry,&swimStart,&flight));
    assert(flight>0.2f && flight<0.8f);
    bot.physicsStep=bot.frameDt=0.02f;
    test_supported_bank_walk(self,wet,dry,anchorFloor,landingFloor,top[0]);
    nav.waterExitFrom=1; nav.waterExitTo=0; nav.waterExitStart=swimStart;
    nav.waterExitUntil=4; nav.waterExitPhase=0;
    self.sector=wet.sector; self.attach_flags=0; self.position=swimStart;
    self.position.z-=0.12f; self.orient.lvec.x=-1;
    memset(bot.keys,0,sizeof(bot.keys)); Bot_ExitWaterMove(&self);
    assert(bot.keys[INPUT_FUNC_JUMP] && nav.waterExitPhase==0);
    self.position=swimStart; self.physicsParams.flags|=SITH_PF_ONWATERSURFACE; self.field_48=.025f;
    self.physicsParams.flags|=SITH_PF_CROUCHING;
    int storedFlags=self.physicsParams.flags;
    assert(Bot_StockWaterMotion(&self));
    assert(!Bot_WaterLanding(&self,&wet,&dry,0,0,&flight));
    bot.previous[INPUT_FUNC_JUMP]=0; memset(bot.keys,0,sizeof(bot.keys));
    Bot_ExitWaterMove(&self);
    assert(nav.waterExitPhase==3 && bot.keys[INPUT_FUNC_JUMP] && (int)self.physicsParams.flags==storedFlags);
    /* Ordinary dry controls release crouch after leaving the water. Only
       a return to the breathing surface should restart the bank run-up. */
    self.sector=dry.sector; self.position.z=swimStart.z+0.1f;
    self.physicsParams.flags&=~(SITH_PF_CROUCHING|SITH_PF_ONWATERSURFACE);
    memset(bot.keys,0,sizeof(bot.keys)); Bot_ExitWaterMove(&self);
    assert(nav.waterExitPhase==4 && !bot.keys[INPUT_FUNC_JUMP]);
    self.sector=wet.sector; self.position=swimStart; self.physicsParams.flags|=SITH_PF_ONWATERSURFACE;
    Bot_ExitWaterMove(&self); assert(nav.waterExitPhase==0);
    /* A fast continuous swim can breach into the dry air column without
       a jump. Keep its valid bank route while ordinary gravity returns it. */
    self.sector=dry.sector; self.position.z=swimStart.z+0.1f;
    self.physicsParams.flags&=~SITH_PF_ONWATERSURFACE;
    Bot_ExitWaterMove(&self); assert(nav.waterExitPhase==4 && !bot.keys[INPUT_FUNC_DUCK]);
    self.sector=wet.sector; self.position=swimStart; self.physicsParams.flags|=SITH_PF_ONWATERSURFACE;
    Bot_ExitWaterMove(&self); assert(nav.waterExitPhase==0);
    bot.previous[INPUT_FUNC_JUMP]=1; memset(bot.keys,0,sizeof(bot.keys));
    Bot_ExitWaterMove(&self);
    assert(!bot.keys[INPUT_FUNC_JUMP] && nav.waterExitPhase==1);
    bot.previous[INPUT_FUNC_JUMP]=0; Bot_ExitWaterMove(&self);
    assert(!bot.keys[INPUT_FUNC_JUMP] && bot.axes[INPUT_FUNC_FORWARD]>.9f);
    for (int tick=0;tick<45 && !bot.keys[INPUT_FUNC_JUMP];tick++) {
        /* Advance the fixture swimmer using stock surface thrust and drag. */
        self.physicsParams.vel.x=self.physicsParams.vel.x*(1-.02f*4*.5f)-.02f*.6f*2;
        self.position.x+=self.physicsParams.vel.x*.02f;
        Bot_ExitWaterMove(&self);
    }
    assert(bot.keys[INPUT_FUNC_JUMP] && nav.waterExitPhase==2 && nav.waterExitUntil>bot.now);
    self.sector=dry.sector; self.position=dry.pos; self.attach_flags=SITH_ATTACH_SURFACE;
    memset(bot.keys,0,sizeof(bot.keys)); Bot_ExitWaterMove(&self);
    assert(nav.waterExitUntil==0 && !bot.keys[INPUT_FUNC_JUMP]);
    self.sector=wet.sector; self.attach_flags=0;
    nav.waterExitUntil=1; bot.now=2; Bot_ExitWaterMove(&self);
    assert(!nav.waterExitUntil && bot.goal==-1 && bot.nodes[0].avoidUntil>bot.now);
    self.sector=dry.sector; self.position=dry.pos; self.attach_flags=SITH_ATTACH_SURFACE;
    bot.now=0; self.orient.lvec.x=1;
    BotNode unsupported=dry; unsupported.pos.z+=0.08f;
    assert(!Bot_WaterExitArc(&wet,&unsupported,&swimStart,&flight));
    self.actorParams.extraSpeed=2.5f;
    assert(Bot_StockWaterMotion(&self));
    Bot_WaterSteer(&self,self.orient.lvec);
    assert(fabsf(bot.axes[INPUT_FUNC_FORWARD]*(2+2.5f)-2)<.00001f);
    self.actorParams.extraSpeed=0; self.physicsParams.flags|=SITH_PF_FLY;
    assert(!Bot_StockWaterMotion(&self));
    self.physicsParams.flags&=~SITH_PF_FLY;
    self.actorParams.maxThrust=.02f;
    assert(!Bot_WaterExitArc(&wet,&dry,&swimStart,&flight));
    self.actorParams.maxThrust=2;
    BotNode tooClose=wet;tooClose.pos.x=.21f;
    assert(!Bot_WaterEntry(&dry,&tooClose));
    test_adjoins[2].flags&=~SITHSURF_ADJOIN_ALLOW_MOVEMENT;
    test_adjoins[3].flags&=~SITHSURF_ADJOIN_ALLOW_MOVEMENT;
    assert(Bot_EdgeMode(1,0)<0);
    memset(bot.axes,0,sizeof(bot.axes));
    assert(Bot_EdgeMode(0,1)<0);
    assert(Bot_EnterWater(&self,&wet,BOT_ROUTE_WATER_ENTRY,0) && bot.goal==-1 && !bot.axes[INPUT_FUNC_FORWARD]);
    test_adjoins[2].flags|=SITHSURF_ADJOIN_ALLOW_MOVEMENT|SITHSURF_ADJOIN_ALLOW_AI_ONLY;
    test_adjoins[3].flags|=SITHSURF_ADJOIN_ALLOW_MOVEMENT|SITHSURF_ADJOIN_ALLOW_AI_ONLY;
    assert(!Bot_WaterEntry(&dry,&wet));
    assert(!Bot_WaterExitArc(&wet,&dry,&swimStart,&flight));
    test_adjoins[2].flags&=~SITHSURF_ADJOIN_ALLOW_AI_ONLY;
    test_adjoins[3].flags&=~SITHSURF_ADJOIN_ALLOW_AI_ONLY;
    test_sectors[1].flags|=SITH_SECTOR_FALLDEATH;
    assert(!Bot_WaterExitArc(&wet,&dry,&swimStart,&flight));
    assert(!Bot_WaterEntry(&dry,&wet));
    test_sectors[1].flags=0;test_sectors[2].flags=0;
    assert(!Bot_WaterEntry(&dry,&wet));
    assert(sithCollision_searchStackIdx==-1);
    sithPlayer_g_pLocalPlayerThing=NULL;
    puts("PASS full-body water exit, momentum gate, fresh jump, dry landing and bounded timeout");
    puts("PASS dry ledge enters verified water through a thin shaft with ordinary inputs; closed, hazardous and narrow openings rejected");
}

static void test_pickup_contact_approach(void)
{
    test_low_threshold(.10f,.25f);
    SithThing player={.type=SITH_THING_PLAYER,.collide=SITH_COLLIDE_SPHERE,.moveSize=.065f,.collideSize=.065f,
        .position={.70f,0,BOT_FOOT_HEIGHT},.sector=&test_sectors[0]};
    SithThing item={.type=SITH_THING_ITEM,.collide=SITH_COLLIDE_SPHERE,.collideSize=.10f,
        .position={1.022f,0,.115f},.sector=&test_sectors[1],.guid=123};
    test_world.numThings=0; test_world.numThingsLoaded=1;test_world.aThings=&item;
    player.actorParams.health=100;
    sithPlayer_g_pLocalPlayerThing=&player;
    int start=Bot_AddRawNode(player.position,player.sector,-1);
    int exact=Bot_AddNode(item.position,item.sector,0,1.1f);
    assert(exact>=0 && start>=0);
    Bot_AddPickupContacts(&player,&item,0,exact);
    while (!bot.graphDone) Bot_BuildGraphStep();
    flex_t cost[BOT_NODES];int parent[BOT_NODES];Bot_PathDistances(&player,start,cost,parent);
    assert(cost[exact]>=1e19f);
    int contact=-1;
    for (int i=0;i<bot.nNodes;i++) if (bot.nodes[i].item==0 && cost[i]<1e19f && bot.nodes[i].sector==player.sector) contact=i;
    assert(contact>=0);
    BotNode *n=&bot.nodes[contact];rdVector3 stop=n->pos;stop.x-=.075f;
    assert(Bot_Distance(stop,n->pos)<.11f);
    player.position=stop;bot.goal=contact;bot.routeCount=1;bot.routePos=0;
    assert(Bot_PickupNeedsContact(&player,n));
    player.position=n->pos;
    assert(!Bot_PickupNeedsContact(&player,n) && sithCollision_HasLOS(&player,&item,0));
    rdVector3 toward=Bot_Sub(n->pos,stop);flex_t travel=Bot_Len(toward),hit;
    rdVector_InvScale3Acc(&toward,travel);
    assert(sithIntersect_CheckSphereIntersection(&stop,&toward,travel,player.moveSize,&item.position,item.collideSize,&hit,0,0));
    item.flags|=SITH_TF_DISABLED;player.position=stop;
    assert(!Bot_PickupNeedsContact(&player,n));
    item.flags=0;nav.itemGuid[0]=456;
    assert(!Bot_PickupNeedsContact(&player,n));
    test_adjoins[0].flags&=~SITHSURF_ADJOIN_VISIBLE;
    nav.itemGuid[0]=item.guid;
    assert(!sithCollision_HasLOS(&player,&item,0));
    bot.nNodes=0;Bot_AddPickupContacts(&player,&item,0,-1);
    for(int j=0;j<bot.nNodes;j++) assert(bot.nodes[j].sector!=&test_sectors[0]);
    test_adjoins[0].flags|=SITHSURF_ADJOIN_VISIBLE;
    test_adjoins[0].flags&=~SITHSURF_ADJOIN_ALLOW_MOVEMENT;
    assert(sithCollision_HasLOS(&player,&item,0));
    bot.nNodes=0;Bot_AddPickupContacts(&player,&item,0,-1);
    for(int j=0;j<bot.nNodes;j++) assert(bot.nodes[j].sector!=&test_sectors[0]);
    assert(sithCollision_searchStackIdx==-1);
    sithPlayer_g_pLocalPlayerThing=NULL;
    puts("PASS recessed pickup needs reachable stock sphere overlap and touch LOS; arrival, closed opening, expired identity and disabled pickup checked");
}

static void test_dynamic_pack_contacts(void)
{
    test_low_threshold(.10f,.25f);
    SithThing self={.type=SITH_THING_PLAYER,.moveSize=.065f,.collideSize=.065f,
        .position={.4f,0,BOT_FOOT_HEIGHT},.sector=&test_sectors[0]};
    SithThing pack={.type=SITH_THING_ITEM,.collide=SITH_COLLIDE_SPHERE,.collideSize=.10f,
        .position={.65f,0,.036337f},.sector=self.sector,.idx=42};
    pack.itemParams.flags=SITH_ITEM_BACKPACK;
    BotNode contact={0}; assert(Bot_PackContact(&self,&pack,&contact));
    assert(contact.item==42 && contact.sector==self.sector && fabsf(contact.pos.z-BOT_FOOT_HEIGHT)<.001f);
    assert(Bot_Distance(contact.pos,pack.position)<self.moveSize+pack.collideSize);
    pack.position.z=.47f; assert(!Bot_PackContact(&self,&pack,&contact));
    pack.position.z=.20f; pack.sector->flags|=SITH_SECTOR_UNDERWATER;
    assert(Bot_PackContact(&self,&pack,&contact) && contact.sector==pack.sector);
    assert(contact.pos.z>pack.position.z && Bot_Distance(contact.pos,pack.position)<self.moveSize+pack.collideSize);
    pack.flags=SITH_TF_DESTROYED; assert(!Bot_PackContact(&self,&pack,&contact));
    pack.flags=0; pack.sector->flags|=SITH_SECTOR_FALLDEATH; assert(!Bot_PackContact(&self,&pack,&contact));
    assert(bot.nNodes==0 && sithCollision_searchStackIdx==-1);
    puts("PASS transient dry and submerged backpack contacts require a live item, legal body clearance and touch overlap without graph nodes");
}

int main(void)
{
    test_geometry();
    SithThing self={0}; self.actorParams.health=100;
    self.sector=&test_sectors[0]; self.position=(rdVector3){2.3f,2.45f,1.95f+BOT_FOOT_HEIGHT};
    int start=Bot_AddRawNode(self.position,self.sector,-1);
    int finish=Bot_AddRawNode((rdVector3){2.15f,2.033333f,1.95f+BOT_FOOT_HEIGHT},&test_sectors[1],-1);
    assert(start==0 && finish==1);
    int drop=-1;
    assert(!Bot_Walkable(&bot.nodes[start],&bot.nodes[finish],&drop));
    SithSurface *portal=&test_surfaces[10]; rdVector3 center;
    assert(Bot_FaceCenter(portal,&center));
    rdVector3 rejected=center;
    rejected.x+=portal->surfaceInfo.face.normal.x*0.14f;
    rejected.y+=portal->surfaceInfo.face.normal.y*0.14f;
    assert(Bot_AddNode(rejected,portal->pSector,-1,5)==-1);
    int entry=Bot_AddPortalNode(portal);
    assert(entry==2 && bot.nodes[entry].sector==&test_sectors[1]);
    assert(fabsf(bot.nodes[entry].pos.x-2.118765f)<0.00001f);
    assert(Bot_Walkable(&bot.nodes[start],&bot.nodes[entry],&drop) && !drop);
    assert(Bot_Walkable(&bot.nodes[entry],&bot.nodes[finish],&drop) && !drop);
    puts("PASS actual collision rejects the corner cut and .14 anchor, validates .04 supported bend segments");
    while (!bot.graphDone) Bot_BuildGraphStep();
    flex_t distance[BOT_NODES]; int parent[BOT_NODES];
    Bot_PathDistances(&self,start,distance,parent);
    assert(distance[finish]<1e19f && parent[finish]==entry && parent[entry]==start);
    bot.nodes[start].nEdges=0; Bot_PathDistances(&self,start,distance,parent);
    assert(distance[finish]>=1e19f);
    puts("PASS actual graph builder and Dijkstra connect the bend through the validated fallback only");
    test_adjoins[1].flags&=~SITHSURF_ADJOIN_ALLOW_MOVEMENT;
    assert(Bot_AddPortalNode(portal)==-1);
    test_adjoins[1].flags|=SITHSURF_ADJOIN_ALLOW_MOVEMENT;
    test_adjoins[1].flags|=SITHSURF_ADJOIN_ALLOW_AI_ONLY;
    assert(Bot_AddPortalNode(portal)==-1);
    test_adjoins[1].flags&=~SITHSURF_ADJOIN_ALLOW_AI_ONLY;
    test_surfaces[6].flags=0;
    assert(Bot_AddPortalNode(portal)==-1);
    assert(sithCollision_searchStackIdx==-1);
    puts("PASS closed/AI-only portals and unsupported landings remain rejected; query stack balanced");
    test_grounded_portal_clearance();
    test_swim_clearance();
    test_water_entry();
    test_pickup_contact_approach();
    test_dynamic_pack_contacts();
    return 0;
}
#endif
