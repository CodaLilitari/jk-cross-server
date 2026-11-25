/* Stock ground movement under the bot's own inputs.
 *
 * The engine's attached-ground physics step (Engine/sithPhysics.c) and its
 * player movement control (sithControl_PlayerMovement, extracted unmodified
 * from Devices/sithControl.c) run here on flat synthetic ground. The inputs
 * are exactly what the bot publishes through jkBot_GetAxis and jkBot_GetKey.
 * No level, collision, networking or game session is involved, so this
 * establishes speeds, directions and stopping distances only.
 */
#include <assert.h>
#include <stdio.h>
#include "AI/jkBot.c"
#ifdef NDEBUG
#error Assertions must remain enabled for the stock ground check
#endif
static void ground_rotation(SithThing *self,rdMatrix34 *matrix) { (void)self; (void)matrix; abort(); }
#define sithCollision_RotateThing ground_rotation
#include "Engine/sithPhysics.c"
#undef sithCollision_RotateThing
#define sithControl_GetKey jkBot_GetKey
#define sithControl_GetKeyAsAxis jkBot_GetAxis
#define sithControl_GetKeyAsAxisNormalized jkBot_GetAxis
#define sithControl_GetAxis(x) (0.0f)
#include "Gameplay/sithPlayerActions.h"
static void sithControl_PlayerMovementMots(SithThing *self) { (void)self; abort(); }
#include "stock_functions.inc"

__typeof__(sithWeapon_controlOptions) sithWeapon_controlOptions=4; /* the bot client's own setting */
__typeof__(sithTime_g_fps) sithTime_g_fps=50;
int32_t Main_bMotsCompat;
int jkPlayer_currentTickIdx;
SithWorld *sithWorld_g_pCurrentWorld;
__typeof__(sithNet_isMulti) sithNet_isMulti=1; /* bots only play multiplayer */
__typeof__(sithNet_tickrate) sithNet_tickrate=16;
__typeof__(jkPlayer_bJankyPhysics) jkPlayer_bJankyPhysics;
__typeof__(jkPlayer_bUseOldPlayerPhysics) jkPlayer_bUseOldPlayerPhysics;
void stdPlatform_Memcpy32(void *to,const void *from,uint32_t length) { memcpy(to,from,length); }
int sithThing_DetachThing(SithThing *thing) { (void)thing; abort(); }
void sithPlayerActions_JumpWithVel(SithThing *thing,flex_t velocity) { (void)thing; (void)velocity; abort(); }

static SithWorld world;
static SithSector sector;
static SithSurface ground;
static SithThing self;
static SithPlayer own;

static void stand(flex_t yaw,flex_t extraSpeed)
{
    memset(&self,0,sizeof(self)); memset(&bot,0,sizeof(bot));
    world.gravity=4; sithWorld_g_pCurrentWorld=&world;
    ground.surfaceInfo.face.normal=(rdVector3){0,0,1};
    self.type=SITH_THING_PLAYER; self.sector=&sector; self.actorParams.pPlayer=&own;
    self.attach_flags=SITH_ATTACH_SURFACE; self.attachedSurface=&ground;
    self.attachedSufaceInfo=&ground.surfaceInfo;
    self.physicsParams.flags=0x4a4f; self.physicsParams.mass=150; self.physicsParams.height=0.18f;
    self.physicsParams.surfDrag=3; self.physicsParams.staticDrag=0.3f; self.physicsParams.airDrag=0.5f;
    self.physicsParams.maxVelocity=1; self.moveSize=self.collideSize=0.065f;
    self.actorParams.maxThrust=2; self.actorParams.extraSpeed=extraSpeed; self.actorParams.maxRotVelocity=200;
    self.position=(rdVector3){0,0,0.18f};
    self.orient.lvec=(rdVector3){cosf(yaw),sinf(yaw),0};
    self.orient.rvec=(rdVector3){sinf(yaw),-cosf(yaw),0};
    self.orient.uvec=(rdVector3){0,0,1};
}

/* One control update per frame, then the engine's fixed multiplayer physics
   steps for that frame. Only the horizontal motion is integrated: the real
   collision pass, absent here, is what holds an actor on its floor. */
static flex_t backlog;
static void step(flex_t dt)
{
    sithControl_PlayerMovement(&self);
    for (backlog+=dt;backlog>=(flex_t)DELTA_PHYSTICK_FPS;backlog-=(flex_t)DELTA_PHYSTICK_FPS) {
        sithPhysics_UpdateThing(&self,(flex_t)DELTA_PHYSTICK_FPS);
        self.position.x+=self.physicsParams.deltaVelocity.x;
        self.position.y+=self.physicsParams.deltaVelocity.y;
    }
    assert(self.attach_flags&SITH_ATTACH_SURFACE);
}

typedef struct Run { flex_t speed, heading, coast, runway, rise; } Run;

/* Hold one input until speed settles, then let go and coast to rest. */
static Run drive(flex_t yaw,flex_t extraSpeed,int exact,int run,int diagonal,flex_t dt)
{
    Run result={0};
    stand(yaw,extraSpeed); backlog=0;
    flex_t elapsed=0;
    for (int i=0;i<(int)(8.0f/dt);i++) {
        memset(bot.axes,0,sizeof(bot.axes)); memset(bot.keys,0,sizeof(bot.keys));
        if (exact) Bot_ThrustAxes(&self,(rdVector3){1,0,0},diagonal);
        else {
            bot.axes[INPUT_FUNC_FORWARD]=Bot_Clamp(cosf(yaw),-0.65f,1.0f);
            bot.axes[INPUT_FUNC_SLIDE]=Bot_Clamp(sinf(yaw),-1.0f,1.0f);
        }
        bot.keys[INPUT_FUNC_FAST]=run;
        assert(fabsf(bot.axes[INPUT_FUNC_FORWARD])<=1.0f && fabsf(bot.axes[INPUT_FUNC_SLIDE])<=1.0f);
        step(dt); elapsed+=dt;
        flex_t speed=Bot_Horizontal(self.physicsParams.vel);
        if (!result.rise && result.speed>0 && speed>=0.9f*result.speed) result.rise=elapsed;
        if (i==(int)(6.0f/dt)) result.speed=speed; /* settled value, used to time the rise on a second pass */
    }
    result.speed=Bot_Horizontal(self.physicsParams.vel);
    result.heading=atan2f(self.physicsParams.vel.y,self.physicsParams.vel.x)*BOT_DEG;
    result.runway=Bot_Runway(&self,run,diagonal);
    rdVector3 from=self.position;
    memset(bot.axes,0,sizeof(bot.axes)); memset(bot.keys,0,sizeof(bot.keys));
    for (int i=0;i<(int)(8.0f/dt) && Bot_Horizontal(self.physicsParams.vel)>0.0001f;i++) step(dt);
    assert(Bot_Horizontal(self.physicsParams.vel)<=0.0001f);
    result.coast=Bot_Horizontal(Bot_Sub(self.position,from));
    return result;
}

static void expect(const char *label,Run run,flex_t speed,flex_t heading)
{
    printf("STOCK_GROUND %-34s speed=%.4f heading=%+.2f coast=%.3f runway=%.3f\n",
        label,(double)run.speed,(double)run.heading,(double)run.coast,(double)run.runway);
    assert(fabsf(run.speed-speed)<0.002f*speed && "settled speed is thrust over surface drag");
    assert(fabsf(run.heading-heading)<0.05f);
    assert(run.runway>run.coast+0.2f && "the checked runway covers the coast with room to spare");
}

int main(void)
{
    const flex_t walk=2.0f/3.0f, angle=BOT_DIAGONAL_ANGLE;
    for (int rate=30;rate<=60;rate+=10) {
        flex_t dt=1.0f/rate;
        printf("STOCK_GROUND control at %d Hz, physics at %.0f Hz\n",rate,(double)TARGET_PHYSTICK_FPS);
        expect("walk, facing the path",drive(0,0,1,0,0,dt),walk,0);
        expect("run key, facing the path",drive(0,0,1,1,0,dt),2*walk,0);
        expect("run key and diagonal",drive(angle,0,1,1,1,dt),2*walk*BOT_DIAGONAL_GAIN,0);
        expect("diagonal alone",drive(angle,0,1,0,1,dt),walk*BOT_DIAGONAL_GAIN,0);
        expect("run and diagonal under Speed (+2)",drive(angle,2,1,1,1,dt),4*walk*BOT_DIAGONAL_GAIN,0);
        /* Exact thrust keeps the path whatever the body faces. */
        static const int yaws[]={20,45,60,90,120,170,-45,-135};
        for (unsigned i=0;i<sizeof(yaws)/sizeof(yaws[0]);i++) {
            flex_t yaw=yaws[i]/BOT_DEG, c=fabsf(cosf(yaw)), s=fabsf(sinf(yaw));
            flex_t gain=cosf(yaw)<0 ? 0.5f : 1.0f, k=1.0f;
            if (c>0.0001f) k=Bot_Min(k,gain/c);
            if (s>0.0001f) k=Bot_Min(k,BOT_STRAFE_GAIN/s);
            char label[64]; snprintf(label,sizeof(label),"run, body turned %+d degrees",yaws[i]);
            expect(label,drive(yaw,0,1,1,0,dt),2*walk*k,0);
        }
    }
    /* The earlier axes: body turned 45 degrees pushes 10 degrees off the path. */
    Run old=drive(45/BOT_DEG,0,0,0,0,1.0f/30);
    printf("STOCK_GROUND %-34s speed=%.4f heading=%+.2f\n","earlier axes, body turned 45",
        (double)old.speed,(double)old.heading);
    assert(fabsf(old.heading+10.01f)<0.1f || fabsf(old.heading-10.01f)<0.1f);
    assert(fabsf(old.speed-walk*sqrtf(0.5f+0.245f))<0.002f);
    puts("PASS stock ground physics: run doubles speed, the diagonal adds 22 percent, exact thrust holds the path, runway exceeds coast");
    return 0;
}
