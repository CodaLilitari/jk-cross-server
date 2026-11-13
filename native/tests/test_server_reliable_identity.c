/* Actual sithMessage_ProcessMessages with bounded inert input/ACK fixtures.
 * Reproduces stale identity suppression; no network, assets or live state writes. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "Devices/sithComm.h"
#include "jk.h"

uint32_t jkPlayer_maxPlayers, sithTime_g_msecGameTime, sithComm_dword_847E84;
SithPlayer jkPlayer_playerInfos[JKPLAYER_NUM_INFOS];
SithMessage sithComm_netMsgTmp, sithComm_MsgTmpBuf2, sithComm_MsgTmpBuf[32];
sithCogMsg_Pair sithComm_aMsgPairs[128];
cogMsg_Handler sithMessage_aTypeFuncs[65];
int sithMessage_g_inputstream, sithMessage_bStopProcessMessages, sithComm_idk2, g_submodeFlags;
int32_t sithNet_isServer;
static SithMessage incoming;
static int queued, acknowledgements, welcomes, chats;
static uint16_t last_ack;

void* _memset(void *destination,int value,size_t size) {
    return memset(destination,value,size);
}

int stdComm_Recv(SithMessage *message) {
    if(!queued)return 0;
    *message=incoming;queued=0;return 1;
}
int stdComm_SendToPlayer(SithMessage *message,int destination) {
    assert(destination==(int)incoming.netMsg.idx);
    assert(message->netMsg.cogMsgId==DSS_RESET && !message->netMsg.msgId && message->netMsg.msg_size==2);
    last_ack=(uint16_t)message->pktData[0];++acknowledgements;return 1;
}
uint32_t sithPlayer_GetPlayerNum(int id) {
    for(uint32_t i=0;i<jkPlayer_maxPlayers;i++)if(jkPlayer_playerInfos[i].playerNetId==id)return i;
    return UINT32_MAX;
}
void sithMulti_QuitPlayer(int id) { (void)id;assert(!"Unexpected unregistered fixture sender"); }
static int received(SithMessage *message) {
    if(message->netMsg.cogMsgId==DSS_WELCOME)++welcomes;
    if(message->netMsg.cogMsgId==DSS_CHAT)++chats;
    return 1;
}
static void deliver(uint32_t peer,uint16_t message_id,uint16_t kind) {
    memset(&incoming,0,sizeof(incoming));incoming.netMsg.idx=peer;
    incoming.netMsg.msgId=message_id;incoming.netMsg.cogMsgId=kind;queued=1;
    ++sithTime_g_msecGameTime;
    assert(sithMessage_ProcessMessages()==1 && !queued);
    if(message_id)assert(last_ack==message_id);
}
int main(void) {
    const uint32_t old_peer=15163125,new_peer=15163134,other_peer=15163123;
    sithMessage_g_inputstream=1;sithNet_isServer=1;jkPlayer_maxPlayers=3;
    jkPlayer_playerInfos[0].playerNetId=1;
    jkPlayer_playerInfos[1].playerNetId=old_peer;jkPlayer_playerInfos[1].flags=4;
    jkPlayer_playerInfos[2].playerNetId=other_peer;jkPlayer_playerInfos[2].flags=7;
    sithMessage_aTypeFuncs[DSS_WELCOME]=received;sithMessage_aTypeFuncs[DSS_CHAT]=received;
    /* Same stale history measured on the owned failed browser fixture. */
    for(unsigned i=0;i<24;i++)sithComm_aMsgPairs[i]=(sithCogMsg_Pair){old_peer,i+1};
    sithComm_aMsgPairs[24]=(sithCogMsg_Pair){other_peer,9};sithComm_dword_847E84=25;
    deliver(old_peer,6,DSS_WELCOME);deliver(old_peer,10,DSS_CHAT);
    assert(acknowledgements==2 && welcomes==0 && chats==0);
    assert(sithComm_dword_847E84==25);
    puts("PASS reused identity's new WELCOME/chat are ACKed but suppressed by actual engine cache");

    jkPlayer_playerInfos[1].playerNetId=new_peer;
    deliver(new_peer,6,DSS_WELCOME);deliver(new_peer,10,DSS_CHAT);
    assert(acknowledgements==4 && welcomes==1 && chats==1);
    for(unsigned i=0;i<24;i++)assert(sithComm_aMsgPairs[i].idx==old_peer && sithComm_aMsgPairs[i].msgId==i+1);
    assert(sithComm_aMsgPairs[24].idx==other_peer && sithComm_aMsgPairs[24].msgId==9);
    puts("PASS fresh canonical identity dispatches identical message numbers without clearing other histories");

    deliver(new_peer,6,DSS_WELCOME);deliver(new_peer,10,DSS_CHAT);deliver(other_peer,9,DSS_CHAT);
    assert(acknowledgements==7 && welcomes==1 && chats==1);
    puts("PASS duplicate suppression remains intact for both the new incarnation and unrelated peers");

    deliver(new_peer,0,DSS_CHAT);deliver(new_peer,0,DSS_CHAT);
    assert(acknowledgements==7 && chats==3);
    puts("PASS ordinary unreliable delivery remains unchanged");
    return 0;
}
