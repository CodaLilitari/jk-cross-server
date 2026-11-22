void exit_trace_unexpected_rotation(SithThing *self,rdMatrix34 *matrix);
#define sithCollision_RotateThing exit_trace_unexpected_rotation
#include "Engine/sithPhysics.c"
#undef sithCollision_RotateThing
#include "Gameplay/sithPlayerActions.c"
int sithMessage_g_outputstream;
int jkPlayer_currentTickIdx;
void exit_trace_unexpected_rotation(SithThing *self,rdMatrix34 *matrix){assert(!self->pAttachedThing);rdMatrix_PreMultiply34(&self->orient,matrix);}
sithPlayingSound *sithSoundClass_PlayModeRandom(SithThing *self,uint32_t mode){return NULL;}
void sithDSSThing_PlaySoundMode(SithThing *self,int16_t mode,int channel,flex32_t gain){abort();}

void sithThing_SyncThing(SithThing *self,int flags){abort();}

__typeof__(g_submodeFlags) g_submodeFlags;
__typeof__(playerThingIdx) playerThingIdx;
__typeof__(sithNet_MultiModeFlags) sithNet_MultiModeFlags;
flex_t sithTime_g_secGameTime;
SithPlayer *sithPlayer_g_pLocalPlayer;
void sithMulti_SendChat(const char *p,int a,int b){abort();}
int sithInventory_IsInventoryAvailable(SithThing *t,int bin){return 0;}
int sithInventory_GetCurrentWeapon(SithThing *t){return SITHBIN_FISTS;}
SithInventoryType *sithInventory_GetType(int b){static SithInventoryType inventory; return &inventory;}
int sithInventory_GetPowerKeybind(int i){return -1;}
SithThing *sithTemplate_GetTemplate(const char *s){return NULL;}



#define sithControl_GetKey jkBot_GetKey
#define sithControl_GetKeyAsAxis jkBot_GetAxis
#define sithControl_GetKeyAsAxisNormalized jkBot_GetAxis
#define sithControl_GetMouseLook(x) (0.0f)
#define sithControl_GetAxis(x) (0.0f)
#define sithControl_TurnSpeed(x) (x)
#define sithControl_NoteKeyYaw(x,y) ((void)0)
#define SITHCONTROL_MOUSE_AXIS_SECS 0.02f
static float sithControl_008d7f44=1;
int sithThing_MotsTick(int a,int b,flex_t c){return 1;}
void sithActor_SetHeadPYR(SithThing *p,const rdVector3 *head){p->actorParams.headPYR=*head;}
__typeof__(sithWeapon_controlOptions) sithWeapon_controlOptions=4;
__typeof__(g_debugmodeFlags) g_debugmodeFlags=0;
__typeof__(sithTime_g_fps) sithTime_g_fps=20;
#include "World/sithSurface.h"
#include "Engine/sithPuppet.h"

#include "World/sithActor.h"
#define SITHTHING_SQUEEZE_RADIUS_FACTOR .7f
static void sithControl_PlayerMovementMots(SithThing *me){abort();}
#include "stock_functions.inc"
static int play_exit(SithThing *me,int from,int to,SithSector *startSector,float dt) {
    BotNode *wet=&bot.nodes[from], *dry=&bot.nodes[to];rdVector3 surface;flex_t duration;
    assert(Bot_WaterExitArc(wet,dry,&nav.waterExitStart,&duration));
    assert(Bot_WaterSurface(wet,me->moveSize,&surface));
    me->sector=startSector;me->position=wet->pos;me->physicsParams.flags=0x4a4f;me->physicsParams.mass=150;me->physicsParams.buoyancy=0;
    me->physicsParams.vel=(rdVector3){0};me->physicsParams.physicsRolloverFrames=0;
    rdVector3 dir=Bot_Sub(dry->pos,wet->pos);float h=Bot_Horizontal(dir);
    me->orient.lvec=(rdVector3){dir.x/h,dir.y/h,0};me->orient.rvec=(rdVector3){dir.y/h,-dir.x/h,0};me->orient.uvec=(rdVector3){0,0,1};
    sithPlayer_g_pLocalPlayer=me->actorParams.pPlayer;
    sithNet_isMulti=1;bot.enabled=bot.joined=1;bot.forceEnabled=0;bot.nextBehavior=1e4;
    bot.graphDone=1;me->actorParams.health=25;
    bot.progressPos=me->position;me->actorParams.maxRotVelocity=200;
    bot.now=1;Bot_ResetHearing();Bot_HearingListener();
    if(getenv("TRACE_X")) {
        me->position=(rdVector3){atof(getenv("TRACE_X")),atof(getenv("TRACE_Y")),atof(getenv("TRACE_Z"))};
        if (!sithIntersect_IsSphereInSector(&me->position,0,startSector)) {
            fprintf(stderr,"Observed position lies outside swimmer start sector %d\n",startSector->id);
            return 0;
        }
        bot.now=80;nav.waterSince=60;bot.stuckAt=bot.now;bot.progressPos=me->position;
        me->actorParams.health=78;
    }
    me->actorParams.flags|=SITH_AF_CANROTATEHEAD;
    me->actorParams.minHeadPitch=-80;me->actorParams.maxHeadPitch=80;
    me->physicsParams.maxRotationVelocity=200;
    if(getenv("TRACE_YAW")){
        rdVector3 angles={0,atof(getenv("TRACE_YAW")),0};rdMatrix34 rotate;
        rdMatrix_BuildRotate34(&rotate,&angles);rdMatrix_PreMultiply34(&me->orient,&rotate);
    }
    if(getenv("TRACE_PITCH")) me->actorParams.headPYR.x=atof(getenv("TRACE_PITCH"));
    if(getenv("TRACE_PF"))me->physicsParams.flags=strtoul(getenv("TRACE_PF"),NULL,16);
    if(getenv("TRACE_VZ"))me->physicsParams.vel.z=atof(getenv("TRACE_VZ"));
    if(getenv("TRACE_HEALTH"))me->actorParams.health=atof(getenv("TRACE_HEALTH"));
    if(getenv("TRACE_END"))me->actorParams.endurance=atoi(getenv("TRACE_END"));
    if(getenv("TRACE_AGE"))nav.waterSince=bot.now-atof(getenv("TRACE_AGE"));
    if(getenv("EXTRA"))me->actorParams.extraSpeed=atof(getenv("EXTRA"));
    sithCollision_initted=1;me->moveType=SITH_MT_PHYSICS;me->collide=SITH_COLLIDE_SPHERE;me->type=SITH_THING_PLAYER;
    me->idx=me-bot.world->aThings; me->sector->pFirstThingInSector=me;me->flags|=SITH_TF_WATER;
    me->physicsParams.height=BOT_FOOT_HEIGHT;
    me->physicsParams.surfDrag=3;me->physicsParams.staticDrag=.3;
    int drySteps=0,stepIndex=0;double residual=0;int firstBreath=-1;int kicks=0;
    for(int tick=0;tick*dt<60.0f;tick++) {

        int surf=!!(me->physicsParams.flags&SITH_PF_ONWATERSURFACE);
        ears.records[0].cue.kind=0;
        ears.records[0].last=bot.now;
        jkBot_Tick(dt);
        if(tick%10==0)fprintf(stderr,"TICK %d ph%d from%d to%d pos%f,%f,%f goal%d key%d axes %.2f %.2f heading %.2f\n",tick,nav.waterExitPhase,nav.waterExitFrom,nav.waterExitTo,me->position.x,me->position.y,me->position.z,bot.goal,bot.keys[INPUT_FUNC_JUMP],bot.axes[INPUT_FUNC_FORWARD],bot.axes[INPUT_FUNC_SLIDE],bot.axes[INPUT_FUNC_TURN]);
        if(getenv("TRACE_X") && tick%10==0){
            int n=bot.routePos<bot.routeCount?bot.route[bot.routePos]:-1;
            fprintf(stderr,"STEP t %.2f sector %d start %d next %d xyz(%.3f,%.3f,%.3f) avoid %.2f stalled %.2f jump %d duck %d vz%.3f\n",
             bot.now,me->sector->id,Bot_Nearest(me),n,n<0?0:bot.nodes[n].pos.x,n<0?0:bot.nodes[n].pos.y,n<0?0:bot.nodes[n].pos.z,
             n<0?0:bot.nodes[n].avoidUntil,bot.routeStallTime,bot.keys[INPUT_FUNC_JUMP],bot.keys[INPUT_FUNC_DUCK],me->physicsParams.vel.z);
        }
        sithTime_g_fps=1.0/dt;
        sithControl_PlayerLook(me,dt);
        if(bot.keys[INPUT_FUNC_JUMP] && surf && !bot.previous[INPUT_FUNC_JUMP]) kicks++;
        if(me->attach_flags)sithControl_PlayerMovement(me);else sithControl_FreeCam(me);
        double span=dt+residual;int count=lround(span*150.0);residual=span-count/150.0;
        for(int sub=0;sub<count;sub++){
        float step=1.0f/150;
        sithTime_g_frameTimeFlex=step;
        unsigned before=me->actorParams.endurance;
        sithActor_Update(me, ((++stepIndex % 3)==1)?6:7);
        if(before>0 && me->actorParams.endurance==0 && firstBreath<0){firstBreath=tick;fprintf(stderr,"BREATH elapsed %.3f health %.1f\n",stepIndex/150.,me->actorParams.health);}
        if(me->actorParams.health<=0){fprintf(stderr,"DROWN elapsed %.3f z %.3f\n",tick*dt,me->position.z);return 0;}
        int oldSector=me->sector->id;unsigned oldSurface=me->physicsParams.flags & SITH_PF_ONWATERSURFACE;
        sithPhysics_UpdateThing(me,step);
        sithThing_UpdateMove(me,step);
        if(oldSector!=me->sector->id || oldSurface!=(me->physicsParams.flags&SITH_PF_ONWATERSURFACE))
            fprintf(stderr,"TRANSITION sec %.3f sector %d->%d surf %d->%d vz %.4f pf %x z %.4f\n",stepIndex/150.,oldSector,me->sector->id,!!oldSurface,!!(me->physicsParams.flags&SITH_PF_ONWATERSURFACE),me->physicsParams.vel.z,me->physicsParams.flags,me->position.z);
        int grounded=me->sector==dry->sector && (me->attach_flags&SITH_ATTACH_SURFACE) && me->attachedSurface && me->attachedSurface->pSector==dry->sector;
        drySteps=grounded?drySteps+1:0;
        if(drySteps>=38){fprintf(stderr,"SUPPORTED_DRY elapsed %.3f stable %.3f sector %d kicks %d z %.3f health %.1f\n",stepIndex/150.,drySteps/150.,me->sector->id,kicks,me->position.z,me->actorParams.health);return 1;}

        }
    }
    return 0;
}
int32_t sithNet_isMulti=1,sithNet_tickrate=16,Main_bMotsCompat=0;
void stdPlatform_Memcpy32(void *dst,const void *src,uint32_t len){memcpy(dst,src,len);}
__typeof__(jkPlayer_bJankyPhysics) jkPlayer_bJankyPhysics;
__typeof__(jkPlayer_bUseOldPlayerPhysics) jkPlayer_bUseOldPlayerPhysics;
__typeof__(jkPlayer_bLedgeSqueeze) jkPlayer_bLedgeSqueeze;
__typeof__(jkPlayer_canonicalPhysTickrate) jkPlayer_canonicalPhysTickrate=.04;
__typeof__(sithPlayer_bNoClippingRend) sithPlayer_bNoClippingRend;
__typeof__(sithCollision_aThingSurfaceCollideResults) sithCollision_aThingSurfaceCollideResults;
__typeof__(sithCollision_collideHurtIdk) sithCollision_collideHurtIdk;
__typeof__(sithCollision_dword_8B4BE4) sithCollision_dword_8B4BE4;
__typeof__(sithTime_g_clockTime) sithTime_g_clockTime;
__typeof__(sithTime_g_frameTimeFlex) sithTime_g_frameTimeFlex;
int _memcmp(const void*a,const void*b,size_t n){return memcmp(a,b,n);}
int stdPlatform_Printf(const char*f,...){va_list a;va_start(a,f);int n=vfprintf(stderr,f,a);va_end(a);return n;}
void stdPlatform_Memzero32(void*p,uint32_t n){memset(p,0,n);}
void sithCog_SectorSendMessage(SithSector*s,SithThing*t,int32_t m){}
void sithCog_SurfaceSendMessage(SithSurface*s,SithThing*t,int32_t m){}
void sithCog_ThingSendMessage(SithThing*s,SithThing*t,int32_t m){}
void sithCog_SendMessage(sithCog*p,int32_t a,int32_t b,int32_t c,int32_t d,int32_t e,int32_t f){}
flex_t sithThing_DamageThing(SithThing*t,SithThing*d,flex_t v,int ty){assert(ty==SITH_DAMAGE_DROWN || ty==SITH_DAMAGE_FALL);t->actorParams.health-=v;return v;}
void sithSoundClass_PlayModeFirstEx(SithThing*t,int m,flex_t v){}
void sithPuppet_SetMoveMode(SithThing*t,int m){abort();}
int sithPuppet_PlayMode(SithThing*t,signed int m,rdPuppetTrackCallback_t c){abort();}
void sithSurface_DetachThing(SithSurface*s,rdVector3*v){abort();}
void sithThing_AttachThingToThingFace(SithThing*t,SithThing*o,rdFace*f,rdVector3*v,int b){abort();}
void sithThing_DestroyThing(SithThing*t){abort();}
