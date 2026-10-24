/* SPDX-License-Identifier: MIT
 * Original DirectPlay 3 TCP/IP transport adapter for JK Cross Server.
 * The game executables and DirectPlay runtime are external dependencies.
 */
#define COBJMACROS
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <windows.h>
#include <initguid.h>
#include <objbase.h>
#include <dplay.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "protocol.h"

#define MAX_FRAME 65536u
#define MAX_RAW 2052u
#define MAX_PEERS 32u
#define MAX_POOL 15u
#define VERSION "0.1.0"

static LPDIRECTPLAY3A dp;
static SOCKET broker = INVALID_SOCKET;
static HANDLE dp_event;
static volatile LONG stopping;
static DPID host_id, pool[MAX_POOL], remote_ids[MAX_PEERS];
static unsigned pool_count, remote_count, game_mode;
static uint32_t slot_ids[32];
static uint8_t stream[MAX_FRAME * 2u];
static size_t stream_used;
static unsigned long long incoming_packets, outgoing_packets;
static uint8_t provider_connection[65536];
static DWORD provider_connection_size;

static const GUID JK_GUID = {0xbf0613c0,0xde79,0x11d0,{0x99,0xc9,0x00,0xa0,0x24,0x76,0xad,0x4b}};
static const GUID MOTS_GUID = {0xa4ff3960,0x3b4f,0x11d1,{0x96,0xcb,0x44,0x45,0x53,0x54,0x00,0x00}};

static BOOL CALLBACK select_tcpip(LPCGUID guid,LPVOID connection,DWORD bytes,LPCDPNAME name,DWORD flags,LPVOID context) {
    (void)name;(void)flags;(void)context;
    if(IsEqualGUID(guid,&DPSPGUID_TCPIP) && bytes && bytes<=sizeof(provider_connection)) {
        memcpy(provider_connection,connection,bytes);provider_connection_size=bytes;return FALSE;
    }
    return TRUE;
}

static uint32_t read32(const void *v) {
    const uint8_t *p = (const uint8_t *)v;
    return (uint32_t)p[0] | ((uint32_t)p[1]<<8) | ((uint32_t)p[2]<<16) | ((uint32_t)p[3]<<24);
}
static void write32(void *v, uint32_t n) {
    uint8_t *p = (uint8_t *)v;
    p[0]=(uint8_t)n; p[1]=(uint8_t)(n>>8); p[2]=(uint8_t)(n>>16); p[3]=(uint8_t)(n>>24);
}
static uint32_t host_alias(uint32_t id,int to_retail) {
    return id==(to_retail?1u:host_id) ? (to_retail?host_id:1u) : id;
}
static void failure(const char *stage, HRESULT hr) {
    fprintf(stderr,"{\"event\":\"error\",\"stage\":\"%s\",\"hresult\":\"0x%08lx\"}\n", stage,(unsigned long)hr);
    fflush(stderr);
}
static void stage(const char *name) {
    printf("{\"event\":\"initializing\",\"stage\":\"%s\"}\n",name);fflush(stdout);
}
static BOOL WINAPI console_signal(DWORD event) {
    if(event==CTRL_C_EVENT || event==CTRL_BREAK_EVENT || event==CTRL_CLOSE_EVENT || event==CTRL_SHUTDOWN_EVENT) {
        InterlockedExchange(&stopping,1); return TRUE;
    }
    return FALSE;
}
static int owned_id(DPID id) {
    unsigned i;
    if(id==host_id) return 1;
    for(i=0;i<pool_count;i++) if(pool[i]==id) return 1;
    return 0;
}
static int remote_index(DPID id) {
    unsigned i;
    for(i=0;i<remote_count;i++) if(remote_ids[i]==id) return (int)i;
    return -1;
}
static int send_all(const uint8_t *p,size_t n) {
    while(n) {
        int k=send(broker,(const char *)p,(int)n,0);
        if(k==SOCKET_ERROR && WSAGetLastError()==WSAEWOULDBLOCK) {
            fd_set set; struct timeval timeout={2,0}; FD_ZERO(&set); FD_SET(broker,&set);
            if(select(0,NULL,&set,NULL,&timeout)<=0) return 0;
            continue;
        }
        if(k<=0) return 0;
        p+=k; n-=(size_t)k;
    }
    return 1;
}
static int send_frame(uint32_t type,uint32_t src,uint32_t dst,const void *payload,size_t bytes) {
    uint8_t frame[MAX_FRAME+4u];
    if(bytes>MAX_FRAME-12u) return 0;
    write32(frame,(uint32_t)(12u+bytes));write32(frame+4,type);write32(frame+8,src);write32(frame+12,dst);
    if(bytes) memcpy(frame+16,payload,bytes);
    return send_all(frame,16u+bytes);
}
static int read_exact(uint8_t *p,size_t n) {
    while(n) { int k=recv(broker,(char*)p,(int)n,0); if(k<=0) return 0; p+=k;n-=(size_t)k; }
    return 1;
}
static int startup_reply(uint32_t wanted,uint8_t *out,size_t *out_size) {
    unsigned attempts;
    for(attempts=0;attempts<8;attempts++) {
        uint8_t frame[MAX_FRAME],head[4];uint32_t n,type;
        if(!read_exact(head,4)) return 0;
        n=read32(head);if(n<12 || n>MAX_FRAME || !read_exact(frame,n)) return 0;
        type=read32(frame);
        if(type==wanted) { if(n-12>*out_size)return 0;memcpy(out,frame+12,n-12);*out_size=n-12;return 1; }
        if(type>=190) { fprintf(stderr,"{\"event\":\"broker_rejected\",\"type\":%lu}\n",(unsigned long)type);return 0; }
    }
    return 0;
}
static int connect_broker(const char *address,unsigned port,const char *token,uint8_t info[244]) {
    struct sockaddr_in a;DWORD timeout=15000;size_t n=244;
    broker=socket(AF_INET,SOCK_STREAM,IPPROTO_TCP);
    if(broker==INVALID_SOCKET)return 0;
    memset(&a,0,sizeof(a));a.sin_family=AF_INET;a.sin_port=htons((u_short)port);a.sin_addr.s_addr=inet_addr(address);
    /* The authenticated internal adapter interface deliberately stays local. */
    if((ntohl(a.sin_addr.s_addr)&0xff000000u)!=0x7f000000u)return 0;
    setsockopt(broker,SOL_SOCKET,SO_RCVTIMEO,(const char*)&timeout,sizeof(timeout));
    setsockopt(broker,SOL_SOCKET,SO_SNDTIMEO,(const char*)&timeout,sizeof(timeout));
    if(connect(broker,(struct sockaddr*)&a,sizeof(a))==SOCKET_ERROR)return 0;
    if(!send_frame(1,0,0,token,strlen(token)) || !send_frame(2,0,0,NULL,0))return 0;
    return startup_reply(102,info,&n) && n==244;
}
static int open_directplay(const uint8_t info[244],unsigned requested_pool) {
    DPSESSIONDESC2 sd;DPNAME name;HRESULT hr;
    const uint8_t *entry=info+4;uint32_t mode=read32(info);unsigned i;
    game_mode=mode;
    char title[96],episode[33],map[33],session[196],password[96];WCHAR titlew[33],passwordw[33];
    if(mode>1 || read32(entry+16)>16 || read32(entry+16)<2 || requested_pool>15) {
        failure("mixed_mode_requires_maxPlayers_2_to_16",E_INVALIDARG);return 0;
    }
    memcpy(titlew,entry+24,64);titlew[32]=0;memcpy(passwordw,entry+152,64);passwordw[32]=0;
    WideCharToMultiByte(CP_ACP,0,titlew,-1,title,sizeof(title),NULL,NULL);
    WideCharToMultiByte(CP_ACP,0,passwordw,-1,password,sizeof(password),NULL,NULL);
    memcpy(episode,entry+88,32);episode[32]=0;memcpy(map,entry+120,32);map[32]=0;
    snprintf(session,sizeof(session),"%s:%s:%s",title,episode,map);
    stage("CoCreateInstance_IDirectPlay3A");
    hr=CoCreateInstance(&CLSID_DirectPlay,NULL,CLSCTX_INPROC_SERVER,&IID_IDirectPlay3A,(void**)&dp);
    if(FAILED(hr)){failure("CoCreateInstance_IDirectPlay3A",hr);return 0;}
    stage("EnumConnections_TCPIP");
    hr=IDirectPlay3_EnumConnections(dp,NULL,select_tcpip,NULL,DPCONNECTION_DIRECTPLAY);
    if(FAILED(hr) || !provider_connection_size){failure("EnumConnections_TCPIP",FAILED(hr)?hr:E_FAIL);return 0;}
    stage("InitializeConnection_TCPIP");
    hr=IDirectPlay3_InitializeConnection(dp,provider_connection,0);
    if(FAILED(hr)){failure("InitializeConnection_TCPIP",hr);return 0;}
    memset(&sd,0,sizeof(sd));sd.dwSize=sizeof(sd);
    /* JK's 0x8000 dedicated-session flag belongs to OpenJKDF2, not DP5. */
    sd.dwFlags=DPSESSION_KEEPALIVE|DPSESSION_NODATAMESSAGES;
    sd.guidApplication=mode ? MOTS_GUID : JK_GUID;
    sd.dwMaxPlayers=32;sd.lpszSessionNameA=session;sd.lpszPasswordA=password[0]?password:NULL;
    sd.dwUser1=read32(entry+220);sd.dwUser2=read32(entry+228);
    sd.dwUser3=(read32(entry+224)&0xffffu)|(read32(entry+236)<<16);sd.dwUser4=read32(entry+232);
    stage("Open_session");
    hr=IDirectPlay3_Open(dp,&sd,DPOPEN_CREATE);
    if(FAILED(hr)){failure("Open_session",hr);return 0;}
    dp_event=CreateEvent(NULL,FALSE,FALSE,NULL);
    memset(&name,0,sizeof(name));name.dwSize=sizeof(name);name.lpszShortNameA="JK Cross Server";name.lpszLongNameA="Dedicated simulation host";
    stage("Create_server_player");
    hr=IDirectPlay3_CreatePlayer(dp,&host_id,&name,dp_event,NULL,0,0);
    if(FAILED(hr) || host_id<65){failure("Create_dedicated_host_player",FAILED(hr)?hr:E_UNEXPECTED);return 0;}
    for(i=0;i<requested_pool;i++) {
        char label[48];snprintf(label,sizeof(label),"Transport slot %u",i+1);name.lpszShortNameA=label;name.lpszLongNameA="Reserved native/browser transport slot";
        hr=IDirectPlay3_CreatePlayer(dp,&pool[i],&name,dp_event,NULL,0,0);
        if(FAILED(hr) || pool[i]<65){failure("Create_surrogate",FAILED(hr)?hr:E_UNEXPECTED);return 0;}
        pool_count++;
    }
    { uint8_t payload[MAX_POOL*4],response[4];size_t response_size=sizeof(response);
      for(i=0;i<pool_count;i++)write32(payload+i*4,pool[i]);
      if(!send_frame(8,0,0,payload,pool_count*4u) || !startup_reply(108,response,&response_size) || response_size!=4 || read32(response)!=pool_count) {
          failure("Register_ID_pool",E_FAIL);return 0;
      }
    }
    printf("{\"event\":\"ready\",\"version\":\"%s\",\"mode\":\"%s\",\"host_id\":%lu,\"canonical_host_id\":1,\"pool_count\":%u,\"physical_capacity\":32,\"human_capacity\":%lu,\"checksum_seed\":%lu}\n",VERSION,mode?"mots":"jk",(unsigned long)host_id,pool_count,(unsigned long)(read32(entry+16)-1),(unsigned long)sd.dwUser1);
    fflush(stdout);return 1;
}
static void add_remote(DPID id) {
    if(owned_id(id) || remote_index(id)>=0)return;
    if(id<65 || remote_count>=MAX_PEERS){failure("remote_capacity_or_id",E_FAIL);return;}
    remote_ids[remote_count++]=id;
    if(!send_frame(3,id,id,NULL,0))InterlockedExchange(&stopping,1);
    printf("{\"event\":\"retail_transport_join\",\"id\":%lu}\n",(unsigned long)id);fflush(stdout);
}
static void remove_remote(DPID id) {
    int k=remote_index(id);if(k<0)return;
    remote_ids[k]=remote_ids[--remote_count];
    if(!send_frame(4,id,0,NULL,0))InterlockedExchange(&stopping,1);
    printf("{\"event\":\"retail_transport_leave\",\"id\":%lu}\n",(unsigned long)id);fflush(stdout);
}
static void cache_roster(const uint8_t *raw,size_t bytes) {
    unsigned count,i;size_t at=14;
    if(bytes<14 || raw[0]!=32 || raw[1])return;
    count=(unsigned)raw[12]|((unsigned)raw[13]<<8);
    if(count>32)return;
    memset(slot_ids,0,sizeof(slot_ids));
    for(i=0;i<count;i++) {
        uint32_t flags;
        if(at+4>bytes)return;
        flags=read32(raw+at);at+=4;
        if(flags&4) {
            if(at+30>bytes)return;
            slot_ids[i]=read32(raw+at);at+=30;
        }
    }
}
/* Preserve original MotS private-recipient scoping. A physical DP copy is
 * projected only to its addressed native/browser surrogate, never widened to
 * broadcast. DirectPlay already delivers peer-to-peer retail copies itself. */
static int project_mots_chat(DPID from,DPID to,const uint8_t *raw,size_t bytes) {
    unsigned count,i,sent=0;size_t list_end;uint32_t destination=host_alias(to,0);
    if(bytes<6)return -1;
    count=(unsigned)raw[4]|((unsigned)raw[5]<<8);
    list_end=6u+4u*count;
    if(!count || count>32 || list_end+8>bytes || read32(raw+list_end+4)!=bytes-list_end-8)return -1;
    if(count==1 && read32(raw+6)==0xffffffffu)return 0;
    for(i=0;i<count;i++) {
        uint32_t slot=read32(raw+6+i*4),target;uint8_t packet[MAX_RAW];size_t n=bytes-4u*(count-1u);
        if(slot==0xffffffffu)target=destination;
        else {
            if(slot>=32)return -1;
            target=slot_ids[slot];
            if(!target || (destination && target!=destination) || (target!=1 && !owned_id(target)))continue;
        }
        memcpy(packet,raw,4);packet[4]=1;packet[5]=0;write32(packet+6,slot);
        memcpy(packet+10,raw+list_end,bytes-list_end);
        if(!jkdp_translate(packet,&n,sizeof(packet),host_id,0,1))return -1;
        if(!send_frame(5,from,target,packet,n))return -1;
        sent++;
        if(slot==0xffffffffu)break;
    }
    /* Retail acknowledges reliable receipt before applying recipient filters.
     * Preserve that behavior for a private copy not addressed to this peer. */
    if(!sent && to && owned_id(to) && (raw[2] || raw[3])) {
        uint8_t ack[6]={40,0,0,0,raw[2],raw[3]};
        if(FAILED(IDirectPlay3_Send(dp,to,from,0,ack,sizeof(ack))))return -1;
    }
    return 1;
}
static int pump_directplay(void) {
    unsigned count;
    for(count=0;count<256 && !stopping;count++) {
        uint8_t raw[65536];DWORD n=sizeof(raw);DPID from=0,to=0;HRESULT hr=IDirectPlay3_Receive(dp,&from,&to,DPRECEIVE_ALL,raw,&n);
        if(hr==DPERR_NOMESSAGES)return 1;
        if(FAILED(hr)){failure("Receive",hr);return 0;}
        if(from==DPID_SYSMSG && n>=4) {
            uint32_t type=read32(raw);
            if(type==DPSYS_CREATEPLAYERORGROUP && n>=sizeof(DPMSG_CREATEPLAYERORGROUP)) {
                DPMSG_CREATEPLAYERORGROUP *m=(DPMSG_CREATEPLAYERORGROUP*)raw;
                if(m->dwPlayerType==DPPLAYERTYPE_PLAYER)add_remote(m->dpId);
            } else if(type==DPSYS_DESTROYPLAYERORGROUP && n>=sizeof(DPMSG_DESTROYPLAYERORGROUP)) {
                DPMSG_DESTROYPLAYERORGROUP *m=(DPMSG_DESTROYPLAYERORGROUP*)raw;
                if(m->dwPlayerType==DPPLAYERTYPE_PLAYER)remove_remote(m->dpId);
            } else if(type==DPSYS_SESSIONLOST) {failure("Session_lost",E_FAIL);return 0;}
            continue;
        }
        if(owned_id(from))continue;
        if(n<4 || n>MAX_RAW)continue;
        add_remote(from);
        if(remote_index(from)<0)continue;
        if(game_mode && raw[0]==2 && raw[1]==0) {
            int handled=project_mots_chat(from,to,raw,n);
            if(handled<0)continue;
            if(handled>0){incoming_packets++;continue;}
        }
        {size_t translated_size=n;
         if(!jkdp_translate(raw,&translated_size,sizeof(raw),host_id,0,game_mode))continue;
         n=(DWORD)translated_size;}
        if(!send_frame(5,from,host_alias(to,0),raw,n))return 0;
        incoming_packets++;
    }
    return 1;
}
static int on_frame(const uint8_t *frame,size_t n) {
    uint32_t type=read32(frame),from=read32(frame+4),to=read32(frame+8);const uint8_t *raw=frame+12;size_t bytes=n-12;
    if(type==105) {
        HRESULT hr;uint8_t translated[MAX_RAW];
        from=host_alias(from,1);to=host_alias(to,1);
        if(bytes<4 || bytes>MAX_RAW) {failure("outbound_source_or_size",E_INVALIDARG);return 0;}
        if(!owned_id(from)) {
            if(remote_index(from)>=0)return 1; /* Retail peer copy already delivered by DP. */
            failure("outbound_source_or_size",E_INVALIDARG);return 0;
        }
        if(to && remote_index(to)<0)return 1;
        memcpy(translated,raw,bytes);
        if(!jkdp_translate(translated,&bytes,sizeof(translated),host_id,1,game_mode)){failure("outbound_management_layout",E_INVALIDARG);return 0;}
        cache_roster(raw,n-12);
        hr=IDirectPlay3_Send(dp,from,to,0,translated,(DWORD)bytes);
        /* A peer can leave between the broker enqueue and the DP destroy
         * notification. Local source players stay alive for this whole loop,
         * so INVALIDPLAYER here identifies the stale remote destination. */
        if(hr==DPERR_INVALIDPLAYER && to && remote_index(to)>=0) {
            printf("{\"event\":\"retail_stale_destination\",\"id\":%lu}\n",(unsigned long)to);
            fflush(stdout);remove_remote(to);return 1;
        }
        if(FAILED(hr)){failure("Send",hr);return 0;}
        outgoing_packets++;
    } else if(type==103) {
        if(bytes<4 || read32(raw)!=0 || from!=to) {failure("canonical_retail_id_rejected",E_FAIL);return 0;}
    } else if(type>=190) {failure("broker_error",E_FAIL);return 0;}
    return 1;
}
static int pump_broker(void) {
    fd_set set;struct timeval wait={0,0};int k;size_t consumed=0;
    FD_ZERO(&set);FD_SET(broker,&set);
    k=select(0,&set,NULL,NULL,&wait);if(k<0)return 0;
    if(!k)return 1;
    if(stream_used==sizeof(stream))return 0;
    k=recv(broker,(char*)stream+stream_used,(int)(sizeof(stream)-stream_used),0);
    if(k<=0)return k==SOCKET_ERROR && WSAGetLastError()==WSAEWOULDBLOCK;
    stream_used+=(size_t)k;
    while(stream_used-consumed>=4) {
        uint32_t n=read32(stream+consumed);
        if(n<12 || n>MAX_FRAME)return 0;
        if(stream_used-consumed<4u+n)break;
        if(!on_frame(stream+consumed+4,n))return 0;
        consumed+=4u+n;
    }
    if(consumed){memmove(stream,stream+consumed,stream_used-consumed);stream_used-=consumed;}
    return 1;
}
int main(int argc,char **argv) {
    const char *address="127.0.0.1",*token=getenv("JK_GATEWAY_TOKEN");unsigned port=46001,requested_pool=15,i;int exit_code=1;WSADATA wsa;uint8_t info[244];DWORD last_report;
    const char *port_env=getenv("JK_GATEWAY_PORT");
    if(port_env && *port_env)port=(unsigned)strtoul(port_env,NULL,10);
    setvbuf(stdout,NULL,_IOLBF,0);setvbuf(stderr,NULL,_IOLBF,0);
    for(i=1;i<(unsigned)argc;i++) {
        if(!strcmp(argv[i],"--version")){puts("JK Cross Server DirectPlay gateway " VERSION);return 0;}
        if(!strcmp(argv[i],"--broker") && i+1<(unsigned)argc)address=argv[++i];
        else if(!strcmp(argv[i],"--port") && i+1<(unsigned)argc)port=(unsigned)strtoul(argv[++i],NULL,10);
        else if(!strcmp(argv[i],"--pool") && i+1<(unsigned)argc)requested_pool=(unsigned)strtoul(argv[++i],NULL,10);
        else {fprintf(stderr,"Usage: gateway.exe [--broker 127.0.0.1] [--port 46001] [--pool 1..15]\n");return 2;}
    }
    if(!token || strlen(token)<16 || strlen(token)>512 || !port || port>65535 || !requested_pool || requested_pool>MAX_POOL) {
        fprintf(stderr,"A 16..512-byte JK_GATEWAY_TOKEN and valid port/pool are required.\n");return 2;
    }
    if(WSAStartup(MAKEWORD(2,2),&wsa)!=0)return 1;
    CoInitialize(NULL);SetConsoleCtrlHandler(console_signal,TRUE);
    if(!connect_broker(address,port,token,info)){failure("Broker_connect_or_info",E_FAIL);goto cleanup;}
    if(!open_directplay(info,requested_pool))goto cleanup;
    {u_long nonblock=1;ioctlsocket(broker,FIONBIO,&nonblock);}
    last_report=GetTickCount();
    while(!stopping) {
        if(!pump_broker() || !pump_directplay())goto cleanup;
        if(GetTickCount()-last_report>=10000) {
            printf("{\"event\":\"stats\",\"retail_clients\":%u,\"received_packets\":%llu,\"sent_packets\":%llu}\n",remote_count,incoming_packets,outgoing_packets);
            if(!send_frame(7,0,0,NULL,0))goto cleanup;
            last_report=GetTickCount();
        }
        WaitForSingleObject(dp_event,2);
    }
    exit_code=0;
cleanup:
    if(dp){IDirectPlay3_Close(dp);IDirectPlay3_Release(dp);}
    if(dp_event)CloseHandle(dp_event);
    if(broker!=INVALID_SOCKET)closesocket(broker);
    CoUninitialize();WSACleanup();
    fprintf(stderr,"{\"event\":\"stopped\",\"exit_code\":%d}\n",exit_code);
    return exit_code;
}
