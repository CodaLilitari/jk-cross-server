#include <assert.h>
#include <stdio.h>
#include "AI/jkBotLoadout.h"

int main(void)
{
    jkBotLoadout p;
    assert(jkBotLoadout_Style(NULL)==JKBOT_STYLE_BALANCED);
    assert(jkBotLoadout_Style("balanced")==0 && jkBotLoadout_Style("master")==1);
    assert(jkBotLoadout_Style("competitive")==2);
    assert(jkBotLoadout_Style("unknown")<0);
    assert(!jkBotLoadout_Plan(8,0,-1,&p));
    assert(!jkBotLoadout_Plan(-1,0,0,&p));
    assert(!jkBotLoadout_Plan(9,0,0,&p));
    assert(!jkBotLoadout_Plan(8,2,0,&p));
    assert(!jkBotLoadout_Plan(8,0,3,&p));
    assert(!jkBotLoadout_Plan(8,0,0,NULL));
    int cases=0;
    for (int rank=0; rank<=8; ++rank) for (int dark=0; dark<=1; ++dark)
    for (int style=0; style<=2; ++style) {
        assert(jkBotLoadout_Plan(rank,dark,style,&p));
        int spent=0, side=dark?30:25, opposite=dark?25:30;
        for (int bin=0; bin<35; ++bin) {
            assert(p.stars[bin]>=0 && p.stars[bin]<=4);
            spent+=p.stars[bin];
            if (bin<21 || bin==29 || bin==34) assert(p.stars[bin]==0);
        }
        assert(spent+p.unspent==rank*3);
        assert(p.unspent>=0 && p.rank==rank);
        for (int n=0;n<4;++n) {
            assert(p.stars[opposite+n]==0);
            if (rank<4+n) assert(p.stars[side+n]==0);
        }
        if (!rank) assert(!spent);
        if (rank==8 && style==1) {
            for(int n=0;n<4;++n) assert(p.stars[side+n]==4);
            for(int n=21;n<=24;++n) assert(!p.stars[n]);
            assert(p.unspent==8);
        }
        if (style==2) {
            const int bins[]={21,22,23,24,dark?31:28,dark?33:25};
            /* Expected levels for each rank, in the six requested positions. */
            static const int levels[2][9][6]={
                {{0},{1,1,1,0},{2,2,1,1},{3,2,2,2},{3,3,2,2,0,2},
                 {3,3,3,3,0,3},{4,4,4,3,0,3},{4,4,4,3,3,3},{4,4,4,4,4,4}},
                {{0},{1,1,1,0},{2,2,1,1},{3,2,2,2},{3,3,3,3},
                 {3,3,3,3,3},{4,4,4,3,3},{4,4,4,3,3,3},{4,4,4,4,4,4}}
            };
            assert(p.unspent==0);
            for (int i=0;i<6;i++) assert(p.stars[bins[i]]==levels[dark][rank][i]);
            assert(spent==rank*3);
        }
        ++cases;
    }
    puts("Bot loadout: 54 legal rank/side/style combinations and invalid inputs passed.");
    assert(cases==54);
    return 0;
}
