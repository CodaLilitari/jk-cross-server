/* Real RenderThing behavior; graphics submission is the controlled boundary. */
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include "Engine/sithRender.c"
static int observerPass=1,sighted,palette,extra,submitted;
int jkObserver_IsRenderPass(void) { return observerPass; }
int g_debugmodeFlags,jkPlayer_currentTickIdx=91;
rdCamera camera,*rdCamera_g_pCurCamera=&camera;
sithRender_weapRendFunc_t sithRender_pExtraThingRenderFunc;
void sithCog_ThingSendMessage(SithThing*t,SithThing*s,int32_t m)
{(void)t;(void)s;assert(m==SITH_MESSAGE_SIGHTED);sighted++;}
void sithPlayer_AddDyamicAdd(int r,int g,int b){(void)r;(void)g;(void)b;palette++;}
flex_t stdMath_Dist3D1(flex_t x,flex_t y,flex_t z){return fabsf(x)+fabsf(y)+fabsf(z);}
int rdThing_Draw(rdThing*t,rdMatrix34*m){(void)t;assert(m->scale.x==4);submitted++;return 1;}
void rdVector_Zero3(rdVector3*v){v->x=v->y=v->z=0;}
static void extra_draw(SithThing*t){(void)t;extra++;}
int main(void)
{
    SithThing thing={0}; __typeof__(*thing.actor) actor={0};
    thing.flags=SITH_TF_CAPTURED|SITH_TF_RENDERWEAPON;
    thing.controlType=SITH_CT_AI;thing.actor=&actor;actor.flags=SITHAI_MODE_SLEEPING;
    thing.position=(rdVector3){4,5,6};thing.orient.scale=(rdVector3){7,8,9};
    thing.renderFrame=12;sithRender_pExtraThingRenderFunc=extra_draw;
    assert(sithRender_RenderThing(&thing)==1);
    assert(sighted==0 && extra==0 && submitted==1);
    assert(actor.flags==SITHAI_MODE_SLEEPING);
    assert(thing.flags==(SITH_TF_CAPTURED|SITH_TF_RENDERWEAPON));
    assert(thing.renderFrame==12);
    assert(thing.orient.scale.x==7 && thing.orient.scale.y==8 && thing.orient.scale.z==9);
    puts("PASS observer draw preserves sighting, AI, visibility, extra hooks and transform");
    thing.type=SITH_THING_EXPLOSION;
    thing.explosionParams.flags=SITHEXPLOSION_FLAG_FLASH_BLINDS_THINGS;
    thing.explosionParams.flashR=255;
    assert(sithRender_RenderThing(&thing)==1);
    assert(palette==0 && thing.explosionParams.flags==SITHEXPLOSION_FLAG_FLASH_BLINDS_THINGS);
    puts("PASS observer does not consume explosion flashes or alter player palette effects");
    observerPass=0;thing.type=SITH_THING_ACTOR;
    assert(sithRender_RenderThing(&thing)==1);
    assert(sighted==1 && extra==1 && actor.flags==0);
    assert(thing.renderFrame==91 && (thing.flags&SITH_TF_INCAMFOV));
    puts("PASS ordinary renderer retains its pre-existing gameplay effects");
    return 0;
}
