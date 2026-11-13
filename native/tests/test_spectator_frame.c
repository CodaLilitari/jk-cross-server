/* Real observer frame lifecycle + horizon calculation, controlled GL boundary. */
#include <assert.h>
#include <stdio.h>
#include "Main/jkObserver.c"
#include "Engine/sithRenderSky.c"

static uint32_t now=1000;
static unsigned int captures;
flex_t sithMain_lastAspect;
int rdroid_curVertexColorMode,sithPlayer_bNoClippingRend;
uint32_t stdPlatform_GetTimeMsec(void) { return now; }
void stdPlatform_Memcpy32(void *destination,const void *source,uint32_t length) { memcpy(destination,source,length); }
uint32_t stdComm_GNS_ObserverPeerGeneration(uint32_t peer) { (void)peer;return 0; }
SithSector *sithSector_FindSectorAtPos(SithWorld *world,rdVector3 *position) { (void)position;return world->aSectors; }
int rdCamera_NewEntry(rdCamera *camera,flex_t fov,BOOL far,flex_t nearPlane,flex_t farPlane,flex_t aspect)
{
    (void)far;(void)nearPlane;(void)farPlane;
    camera->pClipFrustum=calloc(1,sizeof(*camera->pClipFrustum));camera->fov=fov;camera->aspectRatio=aspect;camera->focalLength=320;
    return camera->pClipFrustum!=NULL;
}
void rdCamera_FreeEntry(rdCamera *camera) { free(camera->pClipFrustum);camera->pClipFrustum=NULL; }
void rdCamera_SetAttenuation(rdCamera *camera,flex_t min,flex_t max) { camera->attenuationMin=min;camera->attenuationMax=max; }
int rdCamera_SetCanvas(rdCamera *camera,rdCanvas *canvas) { camera->pCanvas=canvas;return 1; }
int rdCamera_SetCurrent(rdCamera *camera) { rdCamera_g_pCurCamera=camera;return 1; }
void stdPalEffects_ResetEffect(stdPalEffect *effect) { memset(effect,0,sizeof(*effect));effect->fade=1; }
int rdSetColorEffects(stdPalEffect *effect) { rdroid_curColorEffects=*effect;return 1; }
int stdDisplay_VBufferFill(tVBuffer *buffer,int color,rdRect *rect) { (void)buffer;(void)color;(void)rect;return 1; }
void rdAdvanceFrame(void) { ++rdroid_frameTrue; }
void sithAdvanceRenderTick(void) { ++sithRender_lastRenderTick; }
void sithCamera_RenderScene(void) { sithRenderSky_Update(); }
void rdCache_Flush(void) {}
void std3D_DrawMenu(void) {}
void rdFinishFrame(void) {}
int std3D_ObserverReadback(uint8_t *pixels,int width,int height)
{ assert(width==640 && height==360);++captures;memset(pixels,0x5a,(size_t)width*height*4);return 1; }

int main(void)
{
    int sockets[2];assert(socketpair(AF_UNIX,SOCK_STREAM,0,sockets)==0);
    int bufferSize=4096;assert(setsockopt(sockets[0],SOL_SOCKET,SO_SNDBUF,&bufferSize,sizeof(bufferSize))==0);
    assert(fcntl(sockets[1],F_SETFL,O_NONBLOCK)==0);
    char fd[32];snprintf(fd,sizeof(fd),"%d",sockets[0]);setenv("OPENJKDF2_SPECTATOR_FD",fd,1);
    char *args[]={"engine","-headless","-dedicatedServer"};jkObserver_Startup(3,args);jkObserver_SetContextAvailable(1);
    SithThing host={0};SithSector sector={0};SithWorld world={0};SithCamera normalCamera={0};
    rdCanvas canvas={0};tVBuffer buffer={0};Video_pCanvas=&canvas;Video_pMenuBuffer=&buffer;
    world.aThings=&host;world.numThings=0;world.aSectors=&sector;world.numSectors=1;world.pLocalPlayer=world.pCameraFocusThing=&host;
    host.orient.rvec.x=host.orient.lvec.y=host.orient.uvec.z=1;
    sithWorld_g_pCurrentWorld=&world;sithCamera_g_pCurCamera=&normalCamera;rdCamera_g_pCurCamera=&normalCamera.rdCamera;
    jkObserver_WorldOpened();observer.mode=1;observer.angles=(rdVector3){12,34,15};
    sithSector_horizontalPixelsPerRev_idk=2;sithSector_horizontalDist=128;
    const uint32_t capturedAt=now;int frameStamp=rdroid_frameTrue;
    assert(jkObserver_RenderFrame()==1 && captures==1 && observer.pendingBytes>observer.pendingOffset && observer.pendingOffset>0);
    assert(sithSector_flt_8553B8==-68 && sithSector_flt_8553C4==-24);
    assert(fabsf(sithSector_flt_8553F4-sinf(15*(float)OBS_PI/180))<0.001f);
    assert(sithCamera_g_pCurCamera==&normalCamera && rdCamera_g_pCurCamera==&normalCamera.rdCamera);
    assert(rdroid_frameTrue==frameStamp+1 && world.pCameraFocusThing==&host);
    puts("PASS actual observer frame supplies yaw/pitch/roll to the engine horizon calculation and restores camera ownership");

    now+=3000;assert(jkObserver_RenderFrame()==1 && captures==1);
    uint8_t *received=malloc(OBS_HEADER+OBS_PIXELS);assert(received);size_t have=0;
    for(int i=0;i<1000 && have<OBS_HEADER+OBS_PIXELS;i++) {
        ssize_t count=recv(sockets[1],received+have,OBS_HEADER+OBS_PIXELS-have,MSG_DONTWAIT);
        if(count>0)have+=(size_t)count;else assert(errno==EAGAIN||errno==EWOULDBLOCK);
        Observer_Flush(now);
    }
    assert(have==OBS_HEADER+OBS_PIXELS && memcmp(received,"JKSV",4)==0 && Observer_Read32(received+24)==1);free(received);
    assert(observer.sentMs==capturedAt && observer.pendingBytes==0);
    uint8_t status[8]={1,0,0,0},reply[92];assert(jkObserver_Request(status,sizeof(status),reply,sizeof(reply))==92);
    assert((Observer_Read32(reply+20)&2) && Observer_Read32(reply+48)==3000);
    puts("PASS actual frame retains its capture timestamp through three seconds of backpressure and status reports age 3000 ms");

    observer.angles=(rdVector3){-17,83,-40};assert(jkObserver_RenderFrame()==1 && captures==2);
    assert(sithSector_flt_8553B8==-166 && sithSector_flt_8553C4==34);
    assert(fabsf(sithSector_flt_8553F4-sinf(-40*(float)OBS_PI/180))<0.001f);
    puts("PASS subsequent free-camera rotation refreshes horizon offsets and roll");
    jkObserver_Shutdown();close(sockets[1]);unsetenv("OPENJKDF2_SPECTATOR_FD");return 0;
}
