/* Exclusive fixture input before the real player handlers. No native planner runs here. */
#include <poll.h>
#include <sys/socket.h>
#include <errno.h>
#include <limits.h>
static struct {
    int fd, hold, source, axes[4], buttons;
    FILE *trace;
} independent;

static void motor_failure(const char *reason)
{
    fprintf(stderr, "INDEPENDENT_ERROR %s\n", reason);
    exit(3); /* An infrastructure failure has no physical terminal. */
}

static void independent_begin(const BotNode *wet)
{
    /* Record the unrotated reference independently of the actor orientation. */
    assert(getenv("LILY_INDEPENDENT_ORIGIN"));
    FILE *origin = fopen(getenv("LILY_INDEPENDENT_ORIGIN"), "w");
    assert(origin);
    fprintf(origin, "{\"wet_sector\":%d,\"wet_position\":[%.9g,%.9g,%.9g]}\n",
            wet->sector->id, wet->pos.x, wet->pos.y, wet->pos.z);
    assert(fclose(origin) == 0);
    const char *fd = getenv("LILY_MODEL_FD");
    independent.fd = fd ? atoi(fd) : -1;
    independent.hold = atoi(getenv("LILY_HOLD_TICKS") ? getenv("LILY_HOLD_TICKS") : "1");
    independent.source = -1;
    assert(independent.hold >= 1 && independent.hold <= 90 && !lily.enabled);
    assert(!lily.neutral && !lily.active.seq && !lily.queued.seq && !lily.motorBoundary);
    assert(getenv("LILY_INDEPENDENT_TRACE") && !motorTrace);
    independent.trace = fopen(getenv("LILY_INDEPENDENT_TRACE"), "w");
    assert(independent.trace);
}

static unsigned independent_buttons(int presses)
{
    unsigned mask = 0;
    for (int i=0; i<5; ++i)
        if (presses ? bot.presses[lilyButtons[i]] : bot.keys[lilyButtons[i]])
            mask |= 1u << i;
    return mask;
}

#include "recovery.inc"

static void ready_before(short events, double deadline)
{
    struct pollfd fd = {.fd=independent.fd, .events=events};
    for (;;) {
        double remaining = deadline - Companion_Clock();
        if (remaining <= 0) motor_failure("ipc_timeout");
        int result = poll(&fd, 1, (int)ceil(remaining*1000.0));
        if (result < 0 && errno == EINTR) continue;
        if (!result || Companion_Clock() >= deadline) motor_failure("ipc_timeout");
        if (result < 0 || !(fd.revents & events)) motor_failure("ipc_closed");
        return;
    }
}

static void independent_decision(const char *observation, size_t length, unsigned tick)
{
    /* SOCK_SEQPACKET makes both writes atomic. A short/extra/empty reply is invalid. */
    double deadline = Companion_Clock() + 1.0;
    ready_before(POLLOUT, deadline);
    if (send(independent.fd, observation, length, MSG_NOSIGNAL | MSG_DONTWAIT) != (ssize_t)length)
        motor_failure("ipc_send");
    ready_before(POLLIN, deadline);
    unsigned char reply[9];
    ssize_t got = recv(independent.fd, reply, sizeof(reply), MSG_DONTWAIT | MSG_TRUNC);
    if (got == 0) motor_failure("ipc_closed");
    if (got != sizeof(reply)) motor_failure("invalid_reply_size");
    if (Companion_Clock() >= deadline) motor_failure("ipc_timeout");
    if (Companion_Word(reply) != tick) motor_failure("wrong_reply_tick");
    for (int i=0; i<4; i++) {
        int axis = (int)(int8_t)reply[4+i];
        if (axis < -100 || axis > 100) motor_failure("invalid_axis");
        independent.axes[i] = axis;
    }
    if (reply[8] > 3) motor_failure("invalid_buttons");
    independent.buttons = reply[8];
    independent.source = tick;
}

static void independent_tick(SithThing *me, const BotNode *dry, int tick, int step, float dt)
{
    char observation[2048];
    int length = snprintf(observation,sizeof(observation),
        "{\"event\":\"observation\",\"tick\":%d,\"step\":%d,\"sector\":%d,\"physics_flags\":%u,"
        "\"goal\":{\"sector\":%d,\"position\":[%.9g,%.9g,%.9g]},"
        "\"state\":{\"health\":%.9g,\"shields\":%.9g,\"mana\":%.9g},"
        "\"sense\":{\"position\":[%.9g,%.9g,%.9g],\"velocity\":[%.9g,%.9g,%.9g],"
        "\"facing\":[%.9g,%.9g,%.9g],\"up\":[%.9g,%.9g,%.9g],\"head_pitch\":%.9g,"
        "\"supported\":%s,\"medium\":\"%s\",\"breath_used_ms\":%u,\"tick_ms\":%.9g,"
        "\"on_water_surface\":%s,\"buttons\":%u}}\n",
        tick,step,me->sector->id,(unsigned)me->physicsParams.flags,dry->sector->id,
        dry->pos.x,dry->pos.y,dry->pos.z,me->actorParams.health,
        sithInventory_GetInventory(me,SITHBIN_SHIELDS),sithInventory_GetInventory(me,SITHBIN_FORCEMANA),
        me->position.x,me->position.y,me->position.z,
        me->physicsParams.vel.x,me->physicsParams.vel.y,me->physicsParams.vel.z,
        me->orient.lvec.x,me->orient.lvec.y,me->orient.lvec.z,me->orient.uvec.x,me->orient.uvec.y,me->orient.uvec.z,
        me->actorParams.headPYR.x,(me->attach_flags&SITH_ATTACH_SURFACE)?"true":"false",
        me->sector->flags&SITH_SECTOR_UNDERWATER?"water":"air",me->actorParams.endurance,dt*1000,
        me->physicsParams.flags&SITH_PF_ONWATERSURFACE?"true":"false",independent_buttons(0));
    if (length <= 0 || (size_t)length >= sizeof(observation)) motor_failure("observation_size");
    fputs(observation,independent.trace);
    if (recovery.tick && tick == recovery.tick) recovery_handoff(me, step);
    if (recovery.native) {
        jkBot_Tick(dt);
        independent.source = tick;
    } else {
        if (tick % independent.hold == 0) independent_decision(observation, length, tick);
        memcpy(bot.previous,bot.keys,sizeof(bot.keys));
        memset(bot.axes,0,sizeof(bot.axes));
        memset(bot.keys,0,sizeof(bot.keys));
        memset(bot.presses,0,sizeof(bot.presses));
        bot.frameDt=dt;
        bot.now+=dt;
        if (recovery.tick) recovery_observe(me);
        for (int i=0; i<4; i++) bot.axes[lilyAxes[i]]=independent.axes[i]/100.0f;
        for (int i=0; i<2; i++) {
            int key=lilyButtons[i];
            bot.keys[key]=!!(independent.buttons & (1u<<i));
            bot.presses[key]=bot.keys[key] && !bot.previous[key];
        }
        bankOwner="model";
    }
    fprintf(independent.trace,
        "{\"event\":\"input\",\"tick\":%d,\"step\":%d,\"owner\":\"%s\",\"source_tick\":%d,"
        "\"axes\":[%.9g,%.9g,%.9g,%.9g],\"buttons\":%u,\"presses\":%u}\n",
        tick,step,bankOwner,independent.source,bot.axes[lilyAxes[0]],bot.axes[lilyAxes[1]],
        bot.axes[lilyAxes[2]],bot.axes[lilyAxes[3]],independent_buttons(0),independent_buttons(1));
}
