/* Behavioral wire, projection, limits and independent delivery tests. */
#include <assert.h>
#include <stdio.h>
#include "Main/jkObserver.c"
static uint32_t now=1000;
uint32_t stdPlatform_GetTimeMsec(void) { return now; }

uint32_t stdComm_GNS_ObserverPeerGeneration(uint32_t peer) { (void)peer;return 0; }
SithSector *sithSector_FindSectorAtPos(SithWorld *world,rdVector3 *position) { (void)world;(void)position;return NULL; }

int main(void)
{
    int sockets[2];assert(socketpair(AF_UNIX,SOCK_STREAM,0,sockets)==0);
    char fd[32];snprintf(fd,sizeof(fd),"%d",sockets[0]);setenv("OPENJKDF2_SPECTATOR_GEOMETRY_FD",fd,1);
    ObserverGeometry_Startup(sockets[0]);assert(geometry.fd==-1);
    ObserverGeometry_Startup(-1);assert(geometry.fd==sockets[0]);
    geometry.enabled=1;geometry.leaseMs=now;observer.renderPass=1;
    D3DVERTEX v[3]={0};rdTri t={0};t.v1=0;t.v2=1;t.v3=2;
    v[0].x=0;v[0].y=0;v[0].z=0;v[0].color=0x00123456;
    v[1].x=640;v[1].y=360;v[1].z=0.5f;v[1].color=0x00abcdef;
    v[2].x=320;v[2].y=180;v[2].z=0.75f;
    ObserverGeometry_Begin(now);
    jkObserver_CaptureGeometry(v,3,&t,1,NULL,0);
    jkObserver_CaptureGeometry(v,3,NULL,0,&t,1);
    ObserverGeometry_End(now,7,8,9,1);
    assert(geometry.pendingBytes==64+6*20+6*4);
    uint8_t *p=geometry.pending;assert(!memcmp(p,"JKSG",4));
    assert(Observer_Read32(p+16)==7 && Observer_Read32(p+20)==8 && Observer_Read32(p+24)==9);
    assert(Observer_Read32(p+40)==6 && Observer_Read32(p+44)==6);
    assert(Observer_ReadFloat(p+64)==-1 && Observer_ReadFloat(p+68)==1 && Observer_ReadFloat(p+72)==-1 && Observer_ReadFloat(p+76)==1);
    assert(Observer_ReadFloat(p+84)==2 && Observer_ReadFloat(p+88)==-2 && Observer_ReadFloat(p+92)==-1 && Observer_ReadFloat(p+96)==2);
    assert(p[80]==0x12 && p[81]==0x34 && p[82]==0x56 && p[83]==255);
    for(int i=0;i<6;i++)assert(Observer_Read32(p+64+120+4*i)==(uint32_t)i);
    now+=123;ObserverGeometry_Flush(now);uint8_t received[512];assert(recv(sockets[1],received,sizeof(received),0)==208);
    assert(Observer_Read32(received+36)==123 && geometry.pendingBytes==0);
    puts("PASS hand-derived projection, RGB extraction, index rebasing and capture age");
    /* Missing diagnostics, unlimited cadence logging, or poisoned recovery must fail. */
    FILE *diagnostics=tmpfile();assert(diagnostics);
    int savedStderr=dup(STDERR_FILENO);assert(savedStderr>=0);
    fflush(stderr);assert(dup2(fileno(diagnostics),STDERR_FILENO)>=0);
    unsigned char imageState[sizeof(observer)];memcpy(imageState,&observer,sizeof(observer));
    for(int bad=0;bad<6;bad++) {
        ObserverGeometry_Begin(now);
        if(bad==0){v[0].z=1;jkObserver_CaptureGeometry(v,3,&t,1,NULL,0);v[0].z=0;}
        if(bad==1){v[0].x=NAN;jkObserver_CaptureGeometry(v,3,&t,1,NULL,0);v[0].x=0;}
        if(bad==2){t.v3=3;jkObserver_CaptureGeometry(v,3,&t,1,NULL,0);t.v3=2;}
        if(bad==3)jkObserver_CaptureGeometry(v,65537,&t,1,NULL,0);
        if(bad==4)jkObserver_CaptureGeometry(v,3,&t,65537,NULL,0);
        if(bad==5)jkObserver_CaptureGeometry(NULL,3,&t,1,NULL,0);
        ObserverGeometry_End(now,7,8,10,1);assert(!geometry.pendingBytes);
    }
    fflush(stderr);long firstBytes=lseek(fileno(diagnostics),0,SEEK_CUR);
    char messages[2048]={0};rewind(diagnostics);
    assert(fread(messages,1,sizeof(messages)-1,diagnostics)==(size_t)firstBytes);
    assert(fseek(diagnostics,0,SEEK_END)==0);
    /* Burst rejection is bounded independently for each finite reason. */
    for(int i=0;i<100;i++) {
        ObserverGeometry_Begin(now);jkObserver_CaptureGeometry(v,65537,&t,1,NULL,0);
        ObserverGeometry_End(now,7,8,10,1);
    }
    now+=4999;geometry.leaseMs=now;
    ObserverGeometry_Begin(now);jkObserver_CaptureGeometry(v,65537,&t,1,NULL,0);
    ObserverGeometry_End(now,7,8,10,1);fflush(stderr);
    long burstBytes=lseek(fileno(diagnostics),0,SEEK_CUR);
    now++;geometry.leaseMs=now;
    ObserverGeometry_Begin(now);jkObserver_CaptureGeometry(v,65537,&t,1,NULL,0);
    ObserverGeometry_End(now,7,8,10,1);fflush(stderr);
    long renewedBytes=lseek(fileno(diagnostics),0,SEEK_CUR);
    /* A good frame still emits exact JKSG bytes after a rejected frame. */
    ObserverGeometry_Begin(now);jkObserver_CaptureGeometry(v,3,&t,1,NULL,0);
    ObserverGeometry_End(now,7,8,10,1);ObserverGeometry_Flush(now);
    assert(recv(sockets[1],received,sizeof(received),MSG_DONTWAIT)==136);
    assert(!memcmp(received,"JKSG",4) && Observer_Read32(received+24)==10);
    assert(Observer_Read32(received+40)==3 && Observer_Read32(received+44)==3);
    fflush(stderr);long recoveredBytes=lseek(fileno(diagnostics),0,SEEK_CUR);
    assert(dup2(savedStderr,STDERR_FILENO)>=0);close(savedStderr);fclose(diagnostics);
    assert(strstr(messages,"size-limit") && "oversized capture needs a diagnostic reason");
    assert(strstr(messages,"nonfinite-projection") && strstr(messages,"invalid-index") && strstr(messages,"missing-data"));
    int lines=0;for(const char *p=messages;*p;p++)lines+=(*p=='\n');
    assert(lines==4 && burstBytes==firstBytes && renewedBytes>burstBytes);
    assert(recoveredBytes==renewedBytes && !memcmp(imageState,&observer,sizeof(observer)));
    puts("PASS malformed and oversized batches discard whole capture with distinct bounded diagnostic reasons");
    puts("PASS rejection logging is rate limited across 100 captures and renews after five seconds");
    puts("PASS valid capture recovers after rejection without changing image/control status or adding diagnostics");
    observer.capable=observer.context=observer.worldReady=1;observer.mode=1;observer.fd=123;
    uint8_t request[20]={0},reply[92];Observer_Write32(request,1);Observer_Write32(request+4,3);
    Observer_Write32(request+8,observer.worldEpoch);Observer_Write32(request+12,observer.controlEpoch);
    Observer_Write32(request+16,1);uint32_t control=observer.controlEpoch;
    assert(jkObserver_Request(request,20,reply,92)==92 && Observer_Read32(reply+4)==0);
    assert((Observer_Read32(reply+12)&16) && geometry.enabled && observer.controlEpoch==control);
    Observer_Write32(request+16,2);jkObserver_Request(request,20,reply,92);assert(Observer_Read32(reply+4)==1);
    Observer_Write32(request+16,1);Observer_Write32(request+12,control+1);
    jkObserver_Request(request,20,reply,92);assert(Observer_Read32(reply+4)==2);
    Observer_Write32(request+12,control);
    now+=5000;jkObserver_Poll();assert(!geometry.enabled);
    jkObserver_Request(request,20,reply,92);assert(Observer_Read32(reply+4)==0 && geometry.enabled);
    puts("PASS operation 3 validates epochs and boolean, advertises capability, renews lease without changing control epoch");

    int bufferSize=4096;assert(setsockopt(sockets[0],SOL_SOCKET,SO_SNDBUF,&bufferSize,sizeof(bufferSize))==0);
    ObserverGeometry_Begin(now);
    for(int i=0;i<300;i++)jkObserver_CaptureGeometry(v,3,&t,1,NULL,0);
    ObserverGeometry_End(now,7,8,11,1);size_t total=geometry.pendingBytes;
    ObserverGeometry_Flush(now);assert(geometry.pendingOffset>0 && geometry.pendingOffset<total);
    Observer_ControlChanged();assert(!geometry.enabled && geometry.pendingBytes==total);
    geometry.enabled=1;geometry.leaseMs=now;ObserverGeometry_Begin(now);assert(!geometry.capturing);
    uint8_t *wire=malloc(total);size_t have=0;
    for(int i=0;i<1000 && have<total;i++) {
        ssize_t got=recv(sockets[1],wire+have,total-have,MSG_DONTWAIT);
        if(got>0)have+=got;else assert(errno==EAGAIN||errno==EWOULDBLOCK);
        ObserverGeometry_Flush(now);
    }
    assert(have==total && !geometry.pendingBytes && Observer_Read32(wire+24)==11);free(wire);
    now+=5000;ObserverGeometry_Begin(now);assert(!geometry.enabled && !geometry.capturing);
    geometry.enabled=1;geometry.leaseMs=now;ObserverGeometry_Begin(now);
    ObserverGeometry_End(now,7,8,12,1);assert(geometry.pendingBytes==64);
    ObserverGeometry_Stop();assert(!geometry.pendingBytes);
    puts("PASS congestion skips capture; partial envelope finishes across epoch changes; lease expiry and disable discard unsent frames");
    geometry.enabled=1;geometry.leaseMs=now;
    ObserverGeometry_Begin(now);ObserverGeometry_End(now,7,8,13,1);assert(geometry.pendingBytes==64);
    observer.fd=123;observer.mode=1;observer.reason=0;observer.renderError=0;
    close(sockets[1]);ObserverGeometry_Flush(now);
    assert(geometry.fd==-1 && observer.fd==123 && observer.mode==1 && !observer.reason && !observer.renderError);
    puts("PASS geometry peer failure preserves image channel and observer control");
    ObserverGeometry_Shutdown();return 0;
}
