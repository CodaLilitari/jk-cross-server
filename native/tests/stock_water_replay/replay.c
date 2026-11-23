#define BOT_PORTAL_COLLISION_FIXTURE_ONLY
#include "../test_bot_portal_collision.c"
#undef BOT_PORTAL_COLLISION_FIXTURE_ONLY
int sithInventory_IsInventoryActivated(SithThing *p,int b){return p->actorParams.pPlayer && (p->actorParams.pPlayer->aItems[b].state&SITHINVENTORY_ITEM_ACTIVATED);}
#include "replay_loop.inc"
static void vec(FILE *f,rdVector3 *v){float x,y,z;assert(fscanf(f,"%f%f%f",&x,&y,&z)==3);*v=(rdVector3){x,y,z};}
static int integer(FILE *f){int n;assert(fscanf(f,"%d",&n)==1);return n;}
int main(int argc,char **argv){
    assert(argc==7);FILE *f=fopen(argv[1],"r");assert(f); SithWorld *w=&test_world;
    bot.world=sithWorld_g_pCurrentWorld=w;w->gravity=4;strcpy(w->map_jkl_fname,"private");
    w->numVertices=integer(f);w->aVertices=calloc(w->numVertices,sizeof(*w->aVertices));
    for(int i=0;i<w->numVertices;i++)vec(f,&w->aVertices[i]);
    int na=integer(f);w->adjoins=calloc(na,sizeof(*w->adjoins));
    for(int i=0;i<na;i++){SithSurfaceAdjoin *a=w->adjoins+i;a->flags=integer(f);int m=integer(f);assert(m>=0&&m<na);a->mirror=w->adjoins+m;}
    w->numSurfaces=integer(f);w->surfaces=calloc(w->numSurfaces,sizeof(*w->surfaces));
    for(int i=0;i<w->numSurfaces;i++){
        SithSurface *s=w->surfaces+i; s->flags=integer(f);int a=integer(f);if(a>=0){s->pAdjoin=w->adjoins+a;s->pAdjoin->surface=s;}
        rdFace *p=&s->surfaceInfo.face;p->numVertices=integer(f);p->vertexPosIdx=calloc(p->numVertices,sizeof(int32_t));
        for(int j=0;j<p->numVertices;j++){int vi=integer(f);assert(vi>=0&&vi<w->numVertices);p->vertexPosIdx[j]=vi;}vec(f,&p->normal);
    }
    w->numSectors=integer(f);w->aSectors=calloc(w->numSectors,sizeof(*w->aSectors));
    for(int i=0;i<w->numSectors;i++){
        SithSector *s=w->aSectors+i;s->id=i;s->flags=integer(f);vec(f,&s->boundingbox_onecorner);vec(f,&s->boundingbox_othercorner);
        if(integer(f))s->flags|=SITH_SECTOR_HASCOLLIDEBOX;
        vec(f,&s->collidebox_onecorner);vec(f,&s->collidebox_othercorner);vec(f,&s->center);
        s->surfaces=w->surfaces+integer(f);s->numSurfaces=integer(f);
        for(int j=0;j<s->numSurfaces;j++){SithSurface *p=s->surfaces+j;p->pSector=s;if(p->pAdjoin){p->pAdjoin->mirror->sector=s;p->pAdjoin->next=s->adjoins;s->adjoins=p->pAdjoin;}}
    }
    w->numThingsLoaded=integer(f);w->numThings=w->numThingsLoaded-1;w->aThings=calloc(w->numThingsLoaded,sizeof(*w->aThings));
    SithPlayer *own=&jkPlayer_playerInfos[0]; memset(own,0,sizeof(*own));
    SithThing *me=NULL;int origin=atoi(argv[2]);
    for(int i=0;i<w->numThingsLoaded;i++){
        SithThing *t=w->aThings+i;t->type=integer(f);t->sector=w->aSectors+integer(f);vec(f,&t->position);assert(fscanf(f,"%31s",t->aName)==1);
        if(t->type==SITH_THING_ITEM){t->collide=SITH_COLLIDE_SPHERE;t->collideSize=.10f;}
        if(t->type!=SITH_THING_PLAYER)continue;
        t->actorParams.health=100;t->actorParams.jumpSpeed=1.5f;t->physicsParams.maxVelocity=1;t->moveSize=t->collideSize=.065f;
        if(!me&&t->sector->id==origin)me=t;
    }
    fclose(f);assert(me);jkBot_Configure("probe","ky.3do");bot.world=w;bot.forceEnabled=1;me->actorParams.pPlayer=own;own->aItems[SITHBIN_F_JUMP].amount=4;own->aItems[SITHBIN_FORCEMANA].amount=400;
    /* A normal identified seat makes the optional real companion transport live.
       These are fixture initialization fields, never modified by a controller. */
    own->playerNetId=1;own->flags=1;own->pLocalPlayer=me;jkPlayer_maxPlayers=1;playerThingIdx=0;
    me->guid=1;me->signature=1;Companion_NewWorld();
    sithPlayer_g_pLocalPlayerThing=me; me->actorParams.maxThrust=2; me->physicsParams.airDrag=.5f; Bot_BuildNodes(me);while(!bot.graphDone)Bot_BuildGraphStep();
    flex_t d[BOT_NODES];int parent[BOT_NODES],start=Bot_Nearest(me);assert(start>=0);Bot_PathDistances(me,start,d,parent);

    int startSector=atoi(argv[5]);
    if (startSector<0 || startSector>=w->numSectors || !(w->aSectors[startSector].flags&SITH_SECTOR_UNDERWATER)) {
        fprintf(stderr,"Start sector %d must be an underwater map sector\n",startSector);return 2;
    }
    for(int i=0;i<bot.nNodes;i++){BotNode *n=&bot.nodes[i]; if(n->sector->id!=(unsigned)atoi(argv[3]))continue;for(int j=0;j<n->nEdges;j++){
        BotEdge *e=&n->edges[j]; if(e->drop!=BOT_ROUTE_WATER_EXIT || bot.nodes[e->to].sector->id!=(unsigned)atoi(argv[4]))continue;
        int pass=play_exit(me,i,e->to,&w->aSectors[startSector],atof(argv[6]));
        fprintf(stderr,"STOCK FULL TICK landed=%d\n",pass);return !pass;
    }}return 2;}
