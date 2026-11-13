/* Actual engine chat and host actions with inert delivery/roster fixtures.
 * No live network, game assets, COG changes or privileged commands. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "Dss/sithAdmin.h"
#include "Dss/sithMulti.h"
#include "Main/jkEpisode.h"
#include "jk.h"
#ifdef NDEBUG
#error Admin regressions require assertions
#endif

uint32_t jkPlayer_maxPlayers;
SithPlayer jkPlayer_playerInfos[JKPLAYER_NUM_INFOS];
int32_t Main_bDedicatedServer;
int stdComm_bIsServer, stdComm_dplayIdSelf, sith_bOpen, sithMain_bEndLevel;
int32_t sithNet_isServer, sithNet_isMulti, sithNet_serverNetId, sithNet_MultiModeFlags;
int32_t sithMulti_quitGameState;
uint32_t sithMulti_msecQuitGameTime, sithTime_g_msecGameTime;
SithWorld *sithWorld_g_pCurrentWorld;
jkEpisodeLoad jkEpisode_mLoad;
SithMessage sithComm_netMsgTmp;

static SithWorld world;
static SithThing things[32];
static jkEpisodeEntry entries[3];
static int formats, displays, alerts, observedChats, sentCount;
static uint32_t observedPeer, disconnectedPeer;
static char observedText[128];
static struct { SithMessage message; int destination, stream, reliable; } sent[64];

int jk_snwprintf(char16_t *out, size_t size, const char16_t *format, ...)
{ (void)format; ++formats; if (size) out[0] = 0; return 0; }
void sithConsole_PrintWString(const char16_t *text) { (void)text; ++displays; }
void sithConsole_AlertSound(void) { ++alerts; }
void stdComm_GNS_AdminChat(uint32_t peer, const char *text)
{
    ++observedChats; observedPeer = peer;
    assert(strlen(text) < sizeof(observedText)); strcpy(observedText, text);
}
int stdComm_GNS_AdminPeerConnected(uint32_t peer)
{ return peer >= 100 && peer <= 103 && peer != disconnectedPeer; }
int sithComm_SendMsgToPlayer(SithMessage *message, int destination, int stream, int reliable)
{
    assert(sentCount < (int)(sizeof(sent) / sizeof(sent[0])));
    sent[sentCount].message = *message; sent[sentCount].destination = destination;
    sent[sentCount].stream = stream; sent[sentCount].reliable = reliable; ++sentCount;
    return 1;
}
jkEpisodeEntry *jkEpisode_GetCurrentEpisodeEntry(jkEpisodeLoad *episode)
{ return &episode->paEntries[episode->currentEpisodeEntryIdx]; }

static void name_player(unsigned slot, const char *name)
{
    memset(jkPlayer_playerInfos[slot].player_name, 0, sizeof(jkPlayer_playerInfos[slot].player_name));
    for (unsigned i = 0; i < 31 && name[i]; ++i) jkPlayer_playerInfos[slot].player_name[i] = (unsigned char)name[i];
}
static void setup(void)
{
    memset(jkPlayer_playerInfos, 0, sizeof(jkPlayer_playerInfos));
    memset(things, 0, sizeof(things)); memset(entries, 0, sizeof(entries)); memset(sent, 0, sizeof(sent));
    jkPlayer_maxPlayers = 32;
    Main_bDedicatedServer = stdComm_bIsServer = sithNet_isServer = sithNet_isMulti = sith_bOpen = 1;
    sithNet_serverNetId = stdComm_dplayIdSelf = 1;
    sithMain_bEndLevel = sithMulti_quitGameState = sithNet_MultiModeFlags = 0;
    sithMulti_msecQuitGameTime = 0; sithTime_g_msecGameTime = 25000;
    sithWorld_g_pCurrentWorld = &world;
    formats = displays = alerts = observedChats = sentCount = 0;
    observedPeer = disconnectedPeer = 0; observedText[0] = 0;
    for (unsigned i = 0; i < 4; ++i) {
        jkPlayer_playerInfos[i].playerNetId = i ? 99 + i : 1;
        jkPlayer_playerInfos[i].flags = i ? 7 : 6;
        jkPlayer_playerInfos[i].pLocalPlayer = &things[i];
    }
    name_player(0, "Dedicated"); name_player(1, "Administrator");
    name_player(2, "Player One"); name_player(3, "Player Two");
    entries[0] = (jkEpisodeEntry){.lineNum=10, .level=1, .gotoA=20, .gotoB=20};
    entries[1] = (jkEpisodeEntry){.lineNum=20, .level=2, .gotoA=30, .gotoB=30};
    entries[2] = (jkEpisodeEntry){.lineNum=30, .level=3, .gotoA=10, .gotoB=10};
    strcpy(entries[0].fileName, "m2.jkl"); strcpy(entries[1].fileName, "m4.jkl"); strcpy(entries[2].fileName, "m5.jkl");
    jkEpisode_mLoad = (jkEpisodeLoad){.numSeq=3, .currentEpisodeEntryIdx=0, .paEntries=entries};
}
static SithMessage chat(uint32_t peer, int speaker, const char *text)
{
    SithMessage message; size_t size = strlen(text) + 1; assert(size <= 128);
    memset(&message, 0, sizeof(message));
    message.netMsg.cogMsgId = DSS_CHAT; message.netMsg.idx = peer;
    message.netMsg.msg_size = (uint32_t)(12 + size);
    message.pktData[1] = (uint32_t)speaker; message.pktData[2] = (uint32_t)size;
    memcpy((unsigned char *)message.pktData + 12, text, size); return message;
}
static int execute(uint32_t actor, uint32_t operation, const char *argument, uint32_t *kicked, char summary[128])
{
    int status = sithAdmin_Execute(actor, operation, argument, kicked, summary);
    assert(strlen(summary) <= 127 && sithAdmin_Printable(summary, strlen(summary))); return status;
}

int main(void)
{
    char text[128], summary[128]; int32_t speaker; uint32_t kicked;
    setup(); SithMessage message = chat(100, 2, "ordinary chat");
    assert(sithAdmin_DecodeChat(&message, text, &speaker) && speaker == 2 && !strcmp(text, "ordinary chat"));
    memset(text, 'A', 127); text[127] = 0; message = chat(100, 1, text);
    assert(sithAdmin_DecodeChat(&message, text, &speaker) && strlen(text) == 127);
    message.netMsg.msg_size = 12; assert(!sithAdmin_DecodeChat(&message, text, &speaker));
    message = chat(100, 1, "safe"); message.pktData[2] = 0;
    assert(!sithAdmin_DecodeChat(&message, text, &speaker)); message.pktData[2] = 0xffffffffu;
    assert(!sithAdmin_DecodeChat(&message, text, &speaker));
    message = chat(100, 1, "safe"); ((char *)message.pktData)[16] = 'x';
    assert(!sithAdmin_DecodeChat(&message, text, &speaker));
    message = chat(100, 1, "safe"); ((char *)message.pktData)[13] = 0;
    assert(!sithAdmin_DecodeChat(&message, text, &speaker));
    message = chat(100, 1, "line\nbreak"); assert(!sithAdmin_DecodeChat(&message, text, &speaker));
    puts("PASS bounded stock chat decoding rejects malformed lengths, terminators and control characters");

    setup(); assert(sithAdmin_IsCommand("  AdMiN prove example response"));
    assert(!sithAdmin_IsCommand("administrator") && !sithAdmin_IsCommand("ad"));
    message = chat(100, 0x7fffffff, "admin prove test_challenge test_response");
    assert(sithMulti_ProcessChat(&message) == 1);
    assert(observedChats == 1 && observedPeer == 100 && !strcmp(observedText, "admin prove test_challenge test_response"));
    assert(!formats && !displays && !alerts);
    message = chat(100, 2, "ordinary chat"); assert(sithMulti_ProcessChat(&message) == 1 && formats == 1 && displays == 1);
    message = chat(100, 32, "ordinary chat"); assert(!sithMulti_ProcessChat(&message) && formats == 1);
    sithNet_isServer = stdComm_bIsServer = Main_bDedicatedServer = 0;
    message = chat(100, 1, "admin status");
    assert(sithMulti_ProcessChat(&message) == 1 && observedChats == 1 && displays == 2);
    puts("PASS actual host chat hook uses transport sender and consumes proofs before any formatting or display");

    setup(); assert(sithAdmin_JoinedSlot(100) == 1);
    assert(sithAdmin_JoinedSlot(1) < 0 && sithAdmin_JoinedSlot(9999) < 0);
    jkPlayer_playerInfos[4] = jkPlayer_playerInfos[1]; assert(sithAdmin_JoinedSlot(100) < 0);
    memset(&jkPlayer_playerInfos[4], 0, sizeof(jkPlayer_playerInfos[4]));
    jkPlayer_playerInfos[1].flags = 6; assert(sithAdmin_JoinedSlot(100) < 0);
    jkPlayer_playerInfos[1].flags = 7; sith_bOpen = 0; assert(sithAdmin_JoinedSlot(100) < 0);
    sith_bOpen = 1; Main_bDedicatedServer = 0; assert(sithAdmin_JoinedSlot(100) < 0);
    puts("PASS joined actor resolution rejects the host, unknown peers, duplicate identities and loading/disconnected slots");

    setup(); assert(!execute(100, SITH_ADMIN_MESSAGE, "Private admin reply", &kicked, summary) && !kicked);
    assert(sentCount == 1 && sent[0].destination == 100 && sent[0].message.netMsg.cogMsgId == DSS_CHAT);
    assert(sent[0].reliable == 1 && sent[0].message.pktData[1] == 0xffffffffu);
    assert(!strcmp((char *)sent[0].message.pktData + 12, "Private admin reply"));
    assert(execute(100, SITH_ADMIN_MESSAGE, "", &kicked, summary));
    assert(execute(100, SITH_ADMIN_MESSAGE, "bad\nline", &kicked, summary));
    assert(execute(100, 99, "console", &kicked, summary));
    assert(execute(100, SITH_ADMIN_NEXT_LEVEL, "m5.jkl", &kicked, summary)); assert(sentCount == 1);
    puts("PASS typed private replies use bounded ordinary DSS_CHAT only to the verified actor");

    setup(); jkPlayer_playerInfos[3].player_name[0] = 0x2603;
    assert(!execute(100, SITH_ADMIN_PLAYERS, "", &kicked, summary) && sentCount == 4);
    for (int i = 0; i < sentCount; ++i) {
        const char *line = (const char *)sent[i].message.pktData + 12;
        assert(sent[i].destination == 100 && sent[i].message.netMsg.cogMsgId == DSS_CHAT);
        assert(line[0] == '#' && sithAdmin_Printable(line, strlen(line)));
    }
    assert(strstr((const char *)sent[0].message.pktData + 12, "[host]"));
    assert(strstr((const char *)sent[1].message.pktData + 12, "[you]"));
    puts("PASS roster listing is private, bounded, labels stable slots and sanitizes display-only names");

    setup(); assert(execute(100, SITH_ADMIN_KICK, "#0", &kicked, summary));
    assert(execute(100, SITH_ADMIN_KICK, "#1", &kicked, summary));
    assert(execute(100, SITH_ADMIN_KICK, "Dedicated", &kicked, summary));
    assert(execute(100, SITH_ADMIN_KICK, "#999999999999999999999", &kicked, summary));
    assert(execute(100, SITH_ADMIN_KICK, "#2 trailing", &kicked, summary));
    assert(execute(100, SITH_ADMIN_KICK, "Player", &kicked, summary));
    name_player(3, "Player One"); assert(execute(100, SITH_ADMIN_KICK, "Player One", &kicked, summary));
    name_player(3, "Player Two"); disconnectedPeer = 101;
    assert(execute(100, SITH_ADMIN_KICK, "#2", &kicked, summary)); disconnectedPeer = 0; assert(!sentCount);
    assert(!execute(100, SITH_ADMIN_KICK, "Player One", &kicked, summary) && kicked == 101);
    assert(sentCount == 1 && sent[0].destination == 101 && sent[0].message.netMsg.cogMsgId == DSS_QUIT);
    assert(sent[0].message.netMsg.msg_size == 4 && sent[0].message.pktData[0] == 101);
    assert(jkPlayer_playerInfos[2].playerNetId == 101); /* Transport then owns normal removal. */
    puts("PASS exact kick selectors reject host/self/ambiguity/stale transports and use the actual QuitPlayer packet path");

    setup(); sithNet_MultiModeFlags = MULTIMODEFLAG_SINGLE_LEVEL;
    assert(execute(100, SITH_ADMIN_NEXT_LEVEL, "", &kicked, summary));
    sithNet_MultiModeFlags = 0; sithMulti_quitGameState = 1;
    assert(execute(100, SITH_ADMIN_NEXT_LEVEL, "", &kicked, summary));
    sithMulti_quitGameState = 0; entries[0].gotoA = -1;
    assert(execute(100, SITH_ADMIN_NEXT_LEVEL, "", &kicked, summary));
    entries[0].gotoA = 20; entries[1].type = 1; assert(execute(100, SITH_ADMIN_NEXT_LEVEL, "", &kicked, summary));
    entries[1].type = 0; jkEpisode_mLoad.currentEpisodeEntryIdx = 5;
    assert(execute(100, SITH_ADMIN_NEXT_LEVEL, "", &kicked, summary)); assert(!sentCount && !sithMulti_quitGameState);
    puts("PASS next-level refuses single-level sessions, pending transitions and terminal/invalid/video episode links");

    setup(); assert(!execute(100, SITH_ADMIN_NEXT_LEVEL, "", &kicked, summary));
    assert(!kicked && sentCount == 3 && strstr(summary, "m4.jkl"));
    for (int i = 0; i < 3; ++i) {
        assert(sent[i].destination == -1 && sent[i].message.netMsg.cogMsgId == DSS_ENDLEVEL);
        assert(sent[i].message.netMsg.msg_size == 4 && sent[i].message.pktData[0] == 1 && sent[i].reliable == 1);
    }
    assert(sithMulti_quitGameState == 1 && sithMulti_msecQuitGameTime == 35000);
    assert(jkEpisode_mLoad.currentEpisodeEntryIdx == 0); /* Ordinary state machine advances later. */
    assert(execute(100, SITH_ADMIN_NEXT_LEVEL, "", &kicked, summary) && sentCount == 3);
    puts("PASS actual SendEndLevel broadcasts the stock packet three times and schedules the ordinary 10-second transition");

    setup(); jkPlayer_playerInfos[1].playerNetId = 103;
    assert(execute(100, SITH_ADMIN_KICK, "#2", &kicked, summary));
    assert(execute(100, SITH_ADMIN_MESSAGE, "obsolete reply", &kicked, summary)); assert(!sentCount && !kicked);
    puts("PASS every action rechecks the actor's currently joined engine identity");
    return 0;
}
