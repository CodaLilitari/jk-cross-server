// Compile the actual GNSServer Receive, Send and RetireNativeConnection bodies
// against bounded inert transport sinks. No network, assets or live state.
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <queue>
#include <set>
#include <string>
#include <vector>
#include "types_enums.h"
#include "Platform/Networking/GNS/TransportIdentities.h"

using HSteamNetConnection = uint32_t;
static constexpr HSteamNetConnection k_HSteamNetConnection_Invalid = 0;
static int sithNet_isServer = 1, sithNet_bSyncScores = 0, Main_bMotsCompat = 0;
#define sithDplayGNS_infoPrintf(...) ((void)0)
#define sithDplayGNS_verbosePrintf(...) ((void)0)

namespace jk_gateway {
struct Frame { uint32_t type=0,src=0,dst=0;std::vector<uint8_t> data; };
static uint32_t read32(const uint8_t *p) {
    return uint32_t(p[0]) | (uint32_t(p[1])<<8) | (uint32_t(p[2])<<16) | (uint32_t(p[3])<<24);
}
}
struct ISteamNetworkingMessage {
    HSteamNetConnection m_conn;
    int m_cbSize;
    void *m_pData;
    bool released=false;
    void Release() { assert(!released);released=true; }
};
struct InertInterface {
    std::queue<ISteamNetworkingMessage*> messages;
    int ReceiveMessagesOnPollGroup(int,ISteamNetworkingMessage **out,int count) {
        assert(count==1);
        if(messages.empty())return 0;
        *out=messages.front();messages.pop();return 1;
    }
};
struct InertBridge {
    std::vector<jk_gateway::Frame> frames;
    void sendFrame(uint32_t type,uint32_t src,uint32_t dst,const void *data=nullptr,size_t size=0) {
        jk_gateway::Frame frame;frame.type=type;frame.src=src;frame.dst=dst;
        if(size)frame.data.assign(static_cast<const uint8_t*>(data),static_cast<const uint8_t*>(data)+size);
        frames.push_back(std::move(frame));
    }
};
struct InertAdminConnections {
    std::vector<uint32_t> removed;
    void remove(uint32_t peer) { removed.push_back(peer); }
};

class GNSServer {
public:
    #include "probe_Client.inc"
    std::map<HSteamNetConnection,Client_t> m_mapClients;
    std::queue<int> m_DisconnectedPeers;
    std::queue<jk_gateway::Frame> m_gatewayIncoming;
    size_t m_gatewayIncomingBytes=0;
    std::set<uint32_t> m_externalPeers;
    jk_gateway::TransportIdentities m_identities;
    InertAdminConnections m_adminConnections;
    InertBridge m_gateway;
    InertInterface interface;
    InertInterface *m_pInterface=&interface;
    uint64_t availableIds=1;
    uint32_t id=1;
    int m_hPollGroup=0;
    uint8_t sendBuffer[4096]{};
    unsigned sends=0;
    uint32_t expectedCommittedSource=0;

    void SendBytesToClient(HSteamNetConnection connection,void*,uint32_t size) {
        assert(size>=12);
        const uint32_t peer=m_mapClients.at(connection).m_id;
        // This is the actual ordinary-game output sink. Commitment must occur
        // before reaching it, including forwarded peer traffic.
        assert(!m_identities.isPristineNative(peer));
        if(expectedCommittedSource)assert(!m_identities.isPristineNative(expectedCommittedSource));
        ++sends;
    }
    #include "probe_Receive.inc"
    #include "probe_Send.inc"
    #include "probe_SendBytesToAllClients.inc"
    #include "probe_RetireNativeConnection.inc"
};

struct Fixture {
    GNSServer server;
    unsigned nextSlot=1;
    Fixture() { assert(server.m_identities.setPool({1001,1002,1003})); }
    uint32_t connect(HSteamNetConnection connection) {
        const uint32_t peer=server.m_identities.acquireNative();assert(peer);
        GNSServer::Client_t client{};client.m_id=peer;client.m_slot=nextSlot++;
        server.availableIds|=uint64_t(1)<<client.m_slot;
        server.m_mapClients.emplace(connection,client);return peer;
    }
    void assert_spent(HSteamNetConnection connection,uint32_t peer) {
        assert(server.RetireNativeConnection(connection));
        assert(server.m_identities.isRetired(peer));
        assert(server.m_DisconnectedPeers.size()==1 && uint32_t(server.m_DisconnectedPeers.front())==peer);
        assert(server.m_gateway.frames.size()==1 && server.m_gateway.frames[0].type==113 && server.m_gateway.frames[0].src==peer);
    }
};
static std::vector<uint8_t> packet(uint32_t destination) {
    std::vector<uint8_t> bytes(12,0);
    // Untrusted claimed sender deliberately differs; actual transport owns ID.
    const uint32_t claimed=9001;std::memcpy(bytes.data(),&claimed,4);
    std::memcpy(bytes.data()+4,&destination,4);bytes[8]=127;bytes[10]=1;return bytes;
}
static int receive(GNSServer& server,int& source) {
    uint8_t output[64]{};int size=sizeof(output);
    return server.Receive(&source,output,&size);
}

static void pristine_discovery_close_has_no_game_loss() {
    Fixture fixture;auto& server=fixture.server;
    assert(fixture.connect(10)==1001 && fixture.connect(11)==1002);
    assert(server.m_identities.isPristineNative(1001));
    assert(server.RetireNativeConnection(10));
    assert(server.m_DisconnectedPeers.empty() && server.m_gateway.frames.empty());
    assert(!server.m_identities.isRetired(1001));
    assert(fixture.connect(12)==1001);
    assert(!server.RetireNativeConnection(10));
    assert(server.m_identities.isPristineNative(1001) && server.m_identities.isPristineNative(1002));
    puts("PASS actual native retirement releases pristine discovery without a queued game-loss event");
}
static void inbound_local_commits_before_delivery() {
    Fixture fixture;auto& server=fixture.server;assert(fixture.connect(10)==1001);
    auto bytes=packet(1);ISteamNetworkingMessage message{10,int(bytes.size()),bytes.data()};
    server.interface.messages.push(&message);int source=0;
    assert(receive(server,source)==0 && source==1001 && message.released);
    assert(!server.m_identities.isPristineNative(1001));
    fixture.assert_spent(10,1001);
    assert(fixture.connect(12)==1002);
    puts("PASS actual native receive commits its authenticated sender before host delivery");
}
static void inbound_forward_commits_before_both_sinks() {
    Fixture fixture;auto& server=fixture.server;
    assert(fixture.connect(10)==1001 && fixture.connect(11)==1002);
    server.expectedCommittedSource=1001;
    auto bytes=packet(1002);ISteamNetworkingMessage message{10,int(bytes.size()),bytes.data()};
    server.interface.messages.push(&message);int source=0;
    assert(receive(server,source)==-1 && message.released && server.sends==1);
    assert(!server.m_identities.isPristineNative(1001) && !server.m_identities.isPristineNative(1002));
    puts("PASS actual peer forwarding commits incoming and outgoing native identities before the send sink");
}
static void outbound_game_commits_before_send() {
    Fixture fixture;auto& server=fixture.server;
    assert(fixture.connect(10)==1001 && fixture.connect(11)==1002);
    uint8_t bytes[4]={127,0,1,0};
    assert(server.Send(1,1001,bytes,sizeof(bytes))==1 && server.sends==1);
    assert(!server.m_identities.isPristineNative(1001));
    assert(server.m_identities.isPristineNative(1002));
    fixture.assert_spent(10,1001);
    puts("PASS actual ordinary outbound game traffic commits only its native destination before transmission");
}
static void malformed_inbound_is_conservatively_spent() {
    Fixture fixture;auto& server=fixture.server;assert(fixture.connect(10)==1001);
    uint8_t bytes[3]{};ISteamNetworkingMessage message{10,sizeof(bytes),bytes};
    server.interface.messages.push(&message);int source=0;
    assert(receive(server,source)==-1 && message.released && server.sends==0);
    assert(!server.m_identities.isPristineNative(1001));
    fixture.assert_spent(10,1001);
    puts("PASS even malformed inbound native payload commits before its validation rejection");
}
static void delayed_old_handle_cannot_commit_released_reservation() {
    Fixture fixture;auto& server=fixture.server;assert(fixture.connect(10)==1001);
    assert(server.RetireNativeConnection(10));assert(fixture.connect(12)==1001);
    auto bytes=packet(1);ISteamNetworkingMessage old{10,int(bytes.size()),bytes.data()};
    server.interface.messages.push(&old);int source=0;
    assert(receive(server,source)==-1 && old.released);
    assert(server.m_identities.isPristineNative(1001));
    assert(server.m_DisconnectedPeers.empty() && server.m_gateway.frames.empty());
    ISteamNetworkingMessage current{12,int(bytes.size()),bytes.data()};server.interface.messages.push(&current);
    assert(receive(server,source)==0 && source==1001 && current.released);
    assert(!server.m_identities.isPristineNative(1001));
    puts("PASS actual receive drops a removed old handle without committing the newly reserved connection");
}
static void outbound_broadcast_commits_all_actual_recipients() {
    Fixture fixture;auto& server=fixture.server;
    assert(fixture.connect(10)==1001 && fixture.connect(11)==1002 && fixture.connect(12)==1003);
    uint8_t bytes[12]{};
    server.SendBytesToAllClients(bytes,sizeof(bytes),11);
    assert(server.sends==2);
    assert(!server.m_identities.isPristineNative(1001) && !server.m_identities.isPristineNative(1003));
    assert(server.m_identities.isPristineNative(1002));
    puts("PASS actual broadcast helper commits every destination except the explicitly excluded connection");
}
int main() {
    pristine_discovery_close_has_no_game_loss();
    inbound_local_commits_before_delivery();
    inbound_forward_commits_before_both_sinks();
    outbound_game_commits_before_send();
    malformed_inbound_is_conservatively_spent();
    delayed_old_handle_cannot_commit_released_reservation();
    outbound_broadcast_commits_all_actual_recipients();
    puts("PASS 7 actual-method native discovery traffic groups");
}
