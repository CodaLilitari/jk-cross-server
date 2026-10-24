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
        p[a+24]=(uint8_t)(i?255:0);p[a+25]=0;
        p[a+26]=0xff;p[a+27]=0x7f;p[a+28]=0;p[a+29]=0x80;
        p[a+30]=2;p[a+31]=0;p[a+32]=0xff;p[a+33]=0xff;a+=34;
    }
    if(teams){for(i=0;i<10;i++)p[a+i]=(uint8_t)(i+1);a+=10;}
    return a;
}
int main(void) {
    uint8_t p[JKDP_MAX_RAW],original[JKDP_MAX_RAW],expected[JKDP_MAX_RAW];size_t n,before,i;uint32_t host=0x809a1234u;
    for(unsigned rows=1;rows<=32;rows++)for(int teams=0;teams<=1;teams++) {
        n=roster(p,rows,teams);before=n;memcpy(original,p,n);memcpy(expected,p,n);
        assert(jkdp_translate(p,&n,sizeof(p),host,1,0));assert(n==before-rows);
        assert(p[2]==0x91 && p[3]==0x32 && r32(p+8)==host && r32(p+14)==5 && r32(p+18)==host);
        assert(p[38]==0 && p[39]==0xff && p[40]==0x7f); /* U8 kills, next S16. */
        assert(jkdp_translate(p,&n,sizeof(p),host,0,0));assert(n==before);
        u32(expected+14,5);assert(memcmp(p,expected,n)==0);
        for(i=0;i<before;i++) {size_t short_n=i;memcpy(p,original,before);
            assert(!jkdp_translate(p,&short_n,sizeof(p),host,1,0));assert(short_n==i);assert(!memcmp(p,original,before));}
    }
    n=roster(p,2,0);p[39]=1;assert(jkdp_translate(p,&n,sizeof(p),host,1,0)); /* Kills wraps to original U8. */
    assert(p[38]==0);before=n;memcpy(original,p,n);assert(!jkdp_translate(p,&n,before,host,0,0));assert(n==before && !memcmp(p,original,n));
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
    puts("PASS: roster, saber-info and MotS chat layouts, truncated prefixes, sequence preservation, high-bit IDs, signed scores/flags, U8 wrap, capacity and opaque-payload checks");return 0;
}
