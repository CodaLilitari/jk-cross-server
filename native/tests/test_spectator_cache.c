/* Rendering and simulation share these allocations: restoring shallow structs
 * alone would leave saber joints/animation cursors changed. */
#include <assert.h>
#include <stdio.h>
#include "Main/jkObserver.c"

flex_t sithMain_lastAspect;
int rdroid_curVertexColorMode;
int sithPlayer_bNoClippingRend;

int main(void)
{
    SithWorld world={0},beforeWorld;SithThing thing={0},beforeThing;SithSector sector={0},beforeSector;
    SithSurface surface={0};SithSurfaceAdjoin adjoin={0};rdVector3 transformed={1,2,3};int stamp=17,lightStamp=19;flex_t light=0.4f;
    rdModel3 model={0};rdMesh mesh={0};rdFace face={0};flex_t vertexLight=0.6f;
    rdPuppet puppet={0};rdMatrix34 joints[2]={0};rdVector3 hierarchy[2]={0};int amputated[2]={0,1};
    world.aThings=&thing;world.numThings=0;world.aSectors=&sector;world.numSectors=1;world.surfaces=&surface;world.numSurfaces=1;
    world.adjoins=&adjoin;world.numAdjoins=1;world.aTransformedVertices=&transformed;world.numVertices=1;
    world.alloc_unk98=&stamp;world.alloc_unk9c=&lightStamp;world.aVertDynamicLights=&light;world.pLocalPlayer=&thing;world.pCameraFocusThing=&thing;
    model.numHNodes=2;model.numGeos=1;model.aGeos[0].numMeshes=1;model.aGeos[0].aMeshes=&mesh;
    mesh.numVertices=1;mesh.vertices_unk=&vertexLight;mesh.numFaces=1;mesh.faces=&face;mesh.radius=2;
    thing.renderData.type=RD_THING_MODEL3;thing.renderData.model3=&model;thing.renderData.puppet=&puppet;
    thing.renderData.paJointMatrices=joints;thing.renderData.hierarchyNodes2=hierarchy;thing.renderData.paJointAmputationFlags=amputated;
    thing.flags=0x1234;thing.renderFrame=17;thing.orient.scale=(rdVector3){3,4,5};sector.renderTick=27;
    puppet.aTracks[0].playSpeed=-0.5f;puppet.aTracks[0].aCurKfNodeEntryNums[1]=4;joints[1].scale.z=9;hierarchy[0].z=12;
    sithWorld_g_pCurrentWorld=&world;rdroid_frameTrue=30;sithRender_lastRenderTick=40;
    beforeWorld=world;beforeThing=thing;beforeSector=sector;
    rdPuppet beforePuppet=puppet;rdMatrix34 beforeJoints[2];memcpy(beforeJoints,joints,sizeof(joints));
    assert(jkObserver_BeginReadOnlyRender() && jkObserver_IsRenderPass());
    assert(!jkObserver_BeginReadOnlyRender());
    world.pCameraFocusThing=NULL;thing.flags=0;thing.renderFrame=999;thing.orient.scale.x=55;sector.renderTick=888;
    puppet.aTracks[0].playSpeed=0;puppet.aTracks[0].aCurKfNodeEntryNums[1]=6;joints[1].scale.z=72;hierarchy[0].z=99;amputated[1]=0;
    stamp=lightStamp=999;transformed.x=100;light=0;vertexLight=1;mesh.radius=12;face.extraLight=1;rdroid_frameTrue=31;sithRender_lastRenderTick=41;
    jkObserver_EndReadOnlyRender();
    assert(!jkObserver_IsRenderPass() && memcmp(&world,&beforeWorld,sizeof(world))==0 && memcmp(&thing,&beforeThing,sizeof(thing))==0);
    assert(memcmp(&sector,&beforeSector,sizeof(sector))==0 && memcmp(&puppet,&beforePuppet,sizeof(puppet))==0 && memcmp(joints,beforeJoints,sizeof(joints))==0);
    assert(hierarchy[0].z==12 && amputated[1]==1 && stamp==17 && lightStamp==19 && transformed.x==1 && light==0.4f);
    assert(vertexLight==0.6f && mesh.radius==2 && face.extraLight==0 && rdroid_frameTrue==30 && sithRender_lastRenderTick==40);
    puts("PASS exact world/focus/visibility, animation cursors, saber matrices, mesh lighting and frame-counter restoration");
    world.numVertices=INT_MAX;assert(!jkObserver_BeginReadOnlyRender() && !jkObserver_IsRenderPass());
    world.numVertices=1;assert(jkObserver_BeginReadOnlyRender());jkObserver_EndReadOnlyRender();
    puts("PASS bounded snapshot rejects excessive worlds before drawing and remains reusable");
    free(observer.ranges);free(observer.snapshot);return 0;
}
