/* SPDX-License-Identifier: MIT */
#include "protocol.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static void u32(uint8_t *p,uint32_t v){p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);p[2]=(uint8_t)(v>>16);p[3]=(uint8_t)(v>>24);}
static uint32_t r32(const uint8_t *p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static size_t roster(uint8_t *p,unsigned rows,int teams) {
    size_t a=14;unsigned i;memset(p,0,JKDP_MAX_RAW);p[0]=32;p[2]=0x91;p[3]=0x32;
    u32(p+4,teams?1u:0u);u32(p+8,1);p[12]=(uint8_t)rows;
    for(i=0;i<rows;i++) {
        u32(p+a,i==0?6u:7u);u32(p+a+4,i==0?1u:0x80001234u+i);
        snprintf((char*)p+a+8,16,"Player%u",i);
        p[a+24]=(uint8_t)(i?255:0);p[a+25]=1; /* S16 kills, including >255. */
        p[a+26]=0xff;p[a+27]=0x7f;p[a+28]=0;p[a+29]=0x80;
        p[a+30]=2;p[a+31]=0;p[a+32]=0xff;p[a+33]=0xff;a+=34;
    }
    if(teams){for(i=0;i<10;i++)p[a+i]=(uint8_t)(i+1);a+=10;}
    return a;
}

static void score_fields(uint32_t host) {
    /* Independent wire fixtures: native kills/deaths/suicides/team/score S16;
     * original JK team U8 followed by kills/deaths/suicides/score S16. The
     * NativeHuman row reproduces the live false-four-kills scoreboard. */
    static const struct {
        const char *name;
        uint8_t native[10];
        uint8_t retail[9];
    } cases[]={
        {"NativeHuman",{0,0, 4,0, 0,0, 0,0, 0,0},
                       {0, 0,0, 4,0, 0,0, 0,0}},
        {"Different",{0x34,0x12, 0x45,0x23, 0xfd,0xff, 2,0, 0xbf,0xfe},
                     {2, 0x34,0x12, 0x45,0x23, 0xfd,0xff, 0xbf,0xfe}},
        {"Limits",{0xff,0x7f, 0,0x80, 0xff,0xff, 0xff,0, 0,0x80},
                  {0xff, 0xff,0x7f, 0,0x80, 0xff,0xff, 0,0x80}}
    };
    uint8_t p[JKDP_MAX_RAW],expected[JKDP_MAX_RAW];size_t n,before;
    for(size_t i=0;i<sizeof(cases)/sizeof(cases[0]);i++) {
        n=roster(p,1,0);before=n;
        memset(p+22,0,16);memcpy(p+22,cases[i].name,strlen(cases[i].name));
        memcpy(p+38,cases[i].native,sizeof(cases[i].native));memcpy(expected,p,n);
        assert(jkdp_translate(p,&n,sizeof(p),host,1,0));assert(n==before-1);
        assert(!memcmp(p+38,cases[i].retail,sizeof(cases[i].retail)));
        assert(jkdp_translate(p,&n,sizeof(p),host,0,0));assert(n==before);
        u32(expected+14,5);assert(!memcmp(p,expected,n));
    }
    /* Only the team field narrows. Reverse conversion zero-extends U8 team;
     * the high bytes of all four signed score fields remain intact. */
    n=roster(p,1,0);p[44]=0xfe;p[45]=1;memcpy(expected,p,n);
    assert(jkdp_translate(p,&n,sizeof(p),host,1,0));assert(p[38]==0xfe);
    assert(p[39]==0 && p[40]==1); /* 256 kills is not narrowed to U8. */
    assert(jkdp_translate(p,&n,sizeof(p),host,0,0));
    expected[45]=0;u32(expected+14,5);assert(!memcmp(p,expected,n));
}

int main(void) {
    uint8_t p[JKDP_MAX_RAW],original[JKDP_MAX_RAW],expected[JKDP_MAX_RAW],retail_packet[JKDP_MAX_RAW];size_t n,before,retail_n,i;uint32_t host=0x809a1234u;
    score_fields(host);
    for(unsigned rows=1;rows<=32;rows++)for(int teams=0;teams<=1;teams++) {
        n=roster(p,rows,teams);before=n;memcpy(original,p,n);memcpy(expected,p,n);
        assert(jkdp_translate(p,&n,sizeof(p),host,1,0));assert(n==before-rows);
        assert(p[2]==0x91 && p[3]==0x32 && r32(p+8)==host && r32(p+14)==5 && r32(p+18)==host);
        assert(p[38]==2 && p[39]==0 && p[40]==1 && p[41]==0xff && p[42]==0x7f);
        retail_n=n;memcpy(retail_packet,p,n);
        assert(jkdp_translate(p,&n,sizeof(p),host,0,0));assert(n==before);
        u32(expected+14,5);assert(memcmp(p,expected,n)==0);
        for(i=0;i<before;i++) {size_t short_n=i;memcpy(p,original,before);
            assert(!jkdp_translate(p,&short_n,sizeof(p),host,1,0));assert(short_n==i);assert(!memcmp(p,original,before));}
        for(i=0;i<retail_n;i++) {size_t short_n=i;memcpy(p,retail_packet,retail_n);
            assert(!jkdp_translate(p,&short_n,sizeof(p),host,0,0));assert(short_n==i);assert(!memcmp(p,retail_packet,retail_n));}
    }
    n=roster(p,2,0);assert(jkdp_translate(p,&n,sizeof(p),host,1,0));
    before=n;memcpy(original,p,n);assert(!jkdp_translate(p,&n,before,host,0,0));assert(n==before && !memcmp(p,original,n));
    n=roster(p,1,0);p[12]=33;before=n;memcpy(original,p,n);assert(!jkdp_translate(p,&n,sizeof(p),host,1,0));assert(!memcmp(p,original,n));
    memset(p,0,sizeof(p));p[0]=7;u32(p+4,1);n=8;assert(jkdp_translate(p,&n,sizeof(p),host,1,0));assert(r32(p+4)==1); /* Object GUID is not a DPID. */
    for(unsigned polyline=0;polyline<=1;polyline++) {
        size_t prefix=40+polyline*72;memset(p,0,sizeof(p));p[0]=49;p[2]=0x97;p[3]=0x42;
        if(polyline)u32(p+24,0x3f800000);
        u32(p+prefix,1);u32(p+prefix+4,0xffff8000u);u32(p+prefix+8,0xffffffffu);
        n=prefix+12;memcpy(original,p,n);assert(jkdp_translate(p,&n,sizeof(p),host,1,0));assert(n==prefix+6);
        assert(p[prefix]==1 && p[prefix+3]==0x80 && p[prefix+4]==0xff && p[prefix+5]==0xff);
        assert(jkdp_translate(p,&n,sizeof(p),host,0,0));assert(n==prefix+12 && !memcmp(p,original,n));
        n--;before=n;assert(!jkdp_translate(p,&n,sizeof(p),host,1,0));assert(n==before);
    }
    memset(p,0,sizeof(p));p[0]=2;p[2]=0x31;p[3]=0x99;u32(p+4,0xffffffffu);u32(p+8,3);u32(p+12,4);memcpy(p+16,"hey",4);n=20;memcpy(original,p,n);
    assert(jkdp_translate(p,&n,sizeof(p),host,1,1));assert(n==22 && p[4]==1 && p[5]==0 && r32(p+6)==0xffffffffu);
    assert(jkdp_translate(p,&n,sizeof(p),host,0,1));assert(n==20 && !memcmp(p,original,n));
    u32(p+4,2);memcpy(original,p,n);assert(jkdp_translate(p,&n,sizeof(p),host,1,1));assert(r32(p+6)==2);
    assert(jkdp_translate(p,&n,sizeof(p),host,0,1));assert(!memcmp(p,original,n));
    puts("PASS: JK team-first roster, independent scoreboard fixtures, full S16 counts/scores, U8 team zero extension, bidirectional truncation, capacity, host aliases, saber-info, MotS chat and opaque-payload checks");return 0;
}
