/* Actual engine sphere/face collision regression for a narrow angled portal.
 * Two synthetic convex sectors preserve the C3 corridor's measured dimensions.
 * No retail map data, game session, live state writes, or rendering is needed. */
#include <assert.h>
#include <stdarg.h>
#include "AI/jkBot.c"
#ifdef NDEBUG
#error Assertions must remain enabled for the portal regression
#endif
/* This fixture has no things. Keep its world-surface collision path real,
 * while making any accidental thing-intersection dependency fail explicitly. */
#define sithIntersect_CheckSphereThingIntersection TestUnusedThingIntersection
#include "Engine/sithIntersect.c"
#undef sithIntersect_CheckSphereThingIntersection
#include "Engine/sithCollision.c"

uint32_t jkPlayer_maxPlayers;
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
    (void)thing; (void)start; (void)direction; (void)distance; (void)radius; (void)other;
    (void)flags; (void)hit; (void)mesh; (void)face; (void)normal;
    fputs("Unexpected thing collision in world-only fixture\n",stderr); abort();
}
flex_t sithInventory_GetInventory(SithThing *thing,int bin)
{ return thing->actorParams.pPlayer ? thing->actorParams.pPlayer->aItems[bin].amount : 0; }

static SithWorld test_world;
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
    return 0;
}
