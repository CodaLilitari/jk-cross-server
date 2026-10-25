/* SPDX-License-Identifier: MIT */
#include "protocol.h"
#include <string.h>

static uint32_t get32(const uint8_t *p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static void put32(uint8_t *p,uint32_t n) {
    p[0]=(uint8_t)n;p[1]=(uint8_t)(n>>8);p[2]=(uint8_t)(n>>16);p[3]=(uint8_t)(n>>24);
}
static uint32_t alias(uint32_t id,uint32_t host,int retail) {
    return id==(retail?1u:host)?(retail?host:1u):id;
}
int jkdp_translate(uint8_t *raw,size_t *bytes,size_t capacity,uint32_t host,int retail,int mots) {
    uint8_t out[JKDP_MAX_RAW];size_t n=*bytes,read_at,write_at;unsigned type,count,i;
    if(n<4 || n>JKDP_MAX_RAW || n>capacity)return 0;
    memcpy(out,raw,n);type=(unsigned)raw[0]|((unsigned)raw[1]<<8);
    if(type==2 && mots) {
        /* Original MotS Chat: U16 recipientCount, S32 recipient slots,
         * sender slot, text length and text. The gateway projects a private
         * list to one addressed peer before reaching this pure converter. */
        if(retail) {
            if(n<16 || get32(raw+12)!=n-16 || n+2>capacity || n+2>JKDP_MAX_RAW)return 0;
            out[4]=1;out[5]=0;memcpy(out+6,raw+4,n-4);n+=2;
        } else {
            if(n<18 || raw[4]!=1 || raw[5]!=0 || get32(raw+14)!=n-18)return 0;
            memcpy(out+4,raw+6,n-6);n-=2;
        }
    } else if(type==32) {
        if(n<14)return 0;
        count=(unsigned)raw[12]|((unsigned)raw[13]<<8);if(count>32)return 0;
        put32(out+8,alias(get32(raw+8),host,retail));
        read_at=write_at=14;
        for(i=0;i<count;i++) {
            uint32_t flags,id;size_t row=retail?30u:29u;
            if(read_at+4>n || write_at+4>capacity || write_at+4>JKDP_MAX_RAW)return 0;
            flags=get32(raw+read_at);read_at+=4;put32(out+write_at,flags);write_at+=4;
            if(!(flags&4))continue;
            if(read_at+row>n || write_at+(retail?29u:30u)>capacity || write_at+(retail?29u:30u)>JKDP_MAX_RAW)return 0;
            id=get32(raw+read_at);
            /* Original clients broadcast only to active roster entries; the
             * upstream client has a dedicated-host exception. Activate routing
             * on retail only, keeping the host spawn flag clear. */
            if(retail && i==0 && id==1u)put32(out+write_at-4,(flags|1u)&~2u);
            put32(out+write_at,alias(id,host,retail));
            memcpy(out+write_at+4,raw+read_at+4,16);
            if(!mots) {
                /* Original JK1.00 4caa37/4caa54 and 4cad2d: team U8,
                 * then kills/deaths/suicides/score S16. OpenJKDF2 sends
                 * kills/deaths/suicides/team/score as five S16 fields.
                 * Only team narrows; preserve both bytes of every count. */
                if(retail) {
                    out[write_at+20]=raw[read_at+26];
                    memcpy(out+write_at+21,raw+read_at+20,6);
                    memcpy(out+write_at+27,raw+read_at+28,2);
                } else {
                    memcpy(out+write_at+20,raw+read_at+21,6);
                    out[write_at+26]=raw[read_at+20];out[write_at+27]=0;
                    memcpy(out+write_at+28,raw+read_at+27,2);
                }
            } else {
                /* Retain the legacy MotS mapping until separately verified. */
                out[write_at+20]=raw[read_at+20];
                if(retail)memcpy(out+write_at+21,raw+read_at+22,8);
                else {out[write_at+21]=0;memcpy(out+write_at+22,raw+read_at+21,8);}
            }
            read_at+=row;write_at+=retail?29u:30u;
        }
        /* Team scores are five S16 values. Refuse unexplained tail bytes. */
        if(n-read_at!=((get32(raw+4)&1u)?10u:0u))return 0;
        if(write_at+n-read_at>capacity || write_at+n-read_at>JKDP_MAX_RAW)return 0;
        memcpy(out+write_at,raw+read_at,n-read_at);n=write_at+n-read_at;
    } else if(type==49) {
        size_t prefix,old_tail=retail?12u:6u,new_tail=retail?6u:12u;
        /* Original JK 40ca9f/40cc78; MotS 40e39d/40e590. The final
         * super-weapon/shields/surge fields are S16 on retail, U32 upstream.
         * The optional polyline block is selected by baseRadius != 0.0. */
        if(n<28)return 0;
        prefix=40u+((get32(raw+24)&0x7fffffffu)?72u:0u);
        if(n!=prefix+old_tail || prefix+new_tail>capacity || prefix+new_tail>JKDP_MAX_RAW)return 0;
        for(i=0;i<3;i++) {
            if(retail) {out[prefix+i*2]=raw[prefix+i*4];out[prefix+i*2+1]=raw[prefix+i*4+1];}
            else {
                uint32_t value=(uint32_t)raw[prefix+i*2]|((uint32_t)raw[prefix+i*2+1]<<8);
                if(value&0x8000u)value|=0xffff0000u;
                put32(out+prefix+i*4,value);
            }
        }
        n=prefix+new_tail;
    } else if(type==33) {
        if(n<12)return 0;
        put32(out+8,alias(get32(raw+8),host,retail));
    } else if(type==41) {
        if(n<5)return 0;
        count=raw[4];if(count>32 || 5u+count*4u>n)return 0;
        for(i=0;i<count;i++)put32(out+5+i*4,alias(get32(raw+5+i*4),host,retail));
    } else if(type==42) {
        if(n<8)return 0;
        put32(out+4,alias(get32(raw+4),host,retail));
    }
    memcpy(raw,out,n);*bytes=n;return 1;
}
