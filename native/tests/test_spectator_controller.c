/* Exercise the real typed controller and nonblocking stream writer. */
#include <assert.h>
#include <stdio.h>
#include "Main/jkObserver.c"

static uint32_t now=1000, generation=5;
uint32_t stdPlatform_GetTimeMsec(void) { return now; }
void stdPlatform_Memcpy32(void *destination,const void *source,uint32_t length) { memcpy(destination,source,length); }
uint32_t stdComm_GNS_ObserverPeerGeneration(uint32_t peer) { return peer==71?generation:0; }
SithSector *sithSector_FindSectorAtPos(SithWorld *world,rdVector3 *position)
{ return position->x<100 ? world->aSectors:NULL; }
void rdCamera_FreeEntry(rdCamera *camera) { free(camera->pClipFrustum); camera->pClipFrustum=NULL; }

static uint8_t request[40],reply[92+31*76];
static void command(uint32_t op)
{
    memset(request,0,sizeof(request)); Observer_Write32(request,1);Observer_Write32(request+4,op);
    Observer_Write32(request+8,observer.worldEpoch);Observer_Write32(request+12,observer.controlEpoch);
}
static uint32_t send_command(size_t length)
{
    assert(jkObserver_Request(request,length,reply,sizeof(reply))>=92);
    if (Observer_Read32(request+4)!=0) assert(Observer_Read32(reply+56)==0);
    return Observer_Read32(reply+4);
}

int main(void)
{
    char *args[]={"engine","-headless","-dedicatedServer"};
    unsetenv("OPENJKDF2_SPECTATOR_FD");jkObserver_Startup(3,args);assert(!jkObserver_IsCapable());
    int sockets[2];assert(socketpair(AF_UNIX,SOCK_STREAM,0,sockets)==0);
    char fd[32];snprintf(fd,sizeof(fd),"%d",sockets[0]);setenv("OPENJKDF2_SPECTATOR_FD",fd,1);
    jkObserver_Startup(3,args);assert(jkObserver_IsCapable());assert(fcntl(sockets[0],F_GETFL)&O_NONBLOCK);
    jkObserver_SetContextAvailable(1);
    SithWorld world={0};SithThing things[3]={0};SithSector sector={0};
    world.numThings=2;world.aThings=things;world.numSectors=1;world.aSectors=&sector;world.pLocalPlayer=&things[0];
    for(int i=0;i<3;i++) {
        things[i].type=SITH_THING_PLAYER;things[i].position=(rdVector3){(flex_t)i*10,2,3};
        things[i].orient.rvec.x=things[i].orient.lvec.y=things[i].orient.uvec.z=1;
    }
    SithThing host=things[0];sithWorld_g_pCurrentWorld=&world;jkPlayer_maxPlayers=3;
    jkPlayer_playerInfos[0].flags=1;jkPlayer_playerInfos[0].playerNetId=1;
    jkPlayer_playerInfos[1].flags=1;jkPlayer_playerInfos[1].playerNetId=71;jkPlayer_playerInfos[1].pLocalPlayer=&things[1];
    jkPlayer_playerInfos[1].player_name[0]='A';jkPlayer_playerInfos[1].player_name[1]=0x03a9;
    jkPlayer_playerInfos[2].flags=0;jkPlayer_playerInfos[2].playerNetId=72;
    jkObserver_WorldOpened();command(0);assert(send_command(8)==0);
    assert(Observer_Read32(reply+56)==1 && Observer_Read32(reply+92)==71 && Observer_Read32(reply+96)==5);
    assert(reply[104]=='A' && reply[106]==0xa9 && reply[107]==3);
    assert(Observer_Read32(reply+48)==UINT32_MAX && observer.mode==0);
    puts("PASS startup is opt-in, off, bounded, and roster excludes host/provisional peers");

    command(1);Observer_Write32(request+16,2);Observer_Write32(request+20,71);Observer_Write32(request+24,5);
    assert(send_command(28)==0 && observer.mode==2 && observer.position.x==10);
    uint32_t priorControl=observer.controlEpoch;
    jkPlayer_playerInfos[1].pLocalPlayer=&things[2];now+=20;jkObserver_Poll();assert(observer.position.x==20);
    generation=6;now+=20;jkObserver_Poll();assert(observer.mode==1 && observer.targetLost && observer.controlEpoch!=priorControl);
    assert(observer.position.x==20 && memcmp(&host,&things[0],sizeof(host))==0);
    assert(send_command(28)==2);
    puts("PASS follow reacquires respawn, rejects stale generation, and never moves host");

    command(2);Observer_Write32(request+16,1);Observer_WriteFloat(request+20,1.0f);Observer_WriteFloat(request+32,(float)(OBS_PI/2));
    assert(send_command(40)==0);assert(fabs(Observer_ReadFloat(reply+76)-OBS_PI/2)<0.0001);
    rdVector3 before=observer.position;now+=50;jkObserver_Poll();
    assert(fabs(observer.position.x-before.x)+fabs(observer.position.y-before.y)>0.1);
    assert(send_command(40)==1);
    command(2);Observer_Write32(request+16,2);Observer_WriteFloat(request+20,NAN);assert(send_command(40)==1);
    Observer_WriteFloat(request+20,0);Observer_WriteFloat(request+32,4.0f);assert(send_command(40)==1);
    now+=251;before=observer.position;jkObserver_Poll();assert(memcmp(&before,&observer.position,sizeof(before))==0);
    assert(memcmp(&host,&things[0],sizeof(host))==0);
    command(0);request[0]=2;assert(send_command(8)==1);
    command(0);assert(send_command(9)==1);
    puts("PASS finite bounded inputs, radian angles, replay/epoch checks, and 250 ms motion expiry");

    int bufferSize=4096;assert(setsockopt(sockets[0],SOL_SOCKET,SO_SNDBUF,&bufferSize,sizeof(bufferSize))==0);
    assert(fcntl(sockets[1],F_SETFL,O_NONBLOCK)==0);
    memset(observer.pending,0x5a,OBS_HEADER+OBS_PIXELS);memcpy(observer.pending,"JKSV",4);
    Observer_Write32(observer.pending+16,observer.worldEpoch);Observer_Write32(observer.pending+20,observer.controlEpoch);Observer_Write32(observer.pending+24,9);
    const uint32_t capturedAt=now;
    observer.lastAttemptMs=capturedAt;
    observer.pendingCapturedMs=capturedAt;
    observer.pendingBytes=OBS_HEADER+OBS_PIXELS;Observer_Flush(now);
    assert(observer.pendingOffset>0 && observer.pendingOffset<observer.pendingBytes);
    size_t partial=observer.pendingOffset;jkObserver_Disconnect();assert(observer.mode==0 && observer.pendingOffset==partial && observer.pendingBytes>0);
    Observer_Flush(now);assert(observer.pendingOffset==partial);
    now+=3000; /* Congestion must not make old pixels look newly captured. */
    uint8_t *received=malloc(OBS_HEADER+OBS_PIXELS);assert(received);size_t have=0;
    for(int i=0;i<1000 && have<OBS_HEADER+OBS_PIXELS;i++) {
        ssize_t count=recv(sockets[1],received+have,OBS_HEADER+OBS_PIXELS-have,MSG_DONTWAIT);
        if(count>0)have+=(size_t)count;else assert(errno==EAGAIN||errno==EWOULDBLOCK);
        Observer_Flush(now);
    }
    assert(have==OBS_HEADER+OBS_PIXELS && memcmp(received,observer.pending,have)==0 && !observer.pendingBytes);
    assert(observer.sentSequence==9 && observer.sentControl!=observer.controlEpoch);
    assert(observer.sentMs==capturedAt && now-observer.sentMs==3000);free(received);
    close(sockets[1]);observer.pendingBytes=100;observer.pendingOffset=0;Observer_Flush(now);
    assert(observer.fd==-1 && observer.mode==0 && observer.reason==5);
    puts("PASS saturated socket never blocks, partial frames finish, old epochs stay stale, closure disables camera");
    uint32_t oldWorld=observer.worldEpoch;jkObserver_WorldClosing();assert(!observer.worldReady && observer.worldEpoch!=oldWorld);
    jkObserver_Shutdown();unsetenv("OPENJKDF2_SPECTATOR_FD");return 0;
}
