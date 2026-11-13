#include <assert.h>
#include <stdio.h>
#include "AI/jkBotLoadout.h"

int main(void)
{
    jkBotLoadout p;
    assert(!jkBotLoadout_Plan(-1,0,0,&p));
    assert(!jkBotLoadout_Plan(9,0,0,&p));
    assert(!jkBotLoadout_Plan(8,2,0,&p));
    assert(!jkBotLoadout_Plan(8,0,2,&p));
    assert(!jkBotLoadout_Plan(8,0,0,NULL));
    int cases=0;
    for (int rank=0; rank<=8; ++rank) for (int dark=0; dark<=1; ++dark)
    for (int master=0; master<=1; ++master) {
        assert(jkBotLoadout_Plan(rank,dark,master,&p));
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
        if (rank==8 && master) {
            for(int n=0;n<4;++n) assert(p.stars[side+n]==4);
            for(int n=21;n<=24;++n) assert(!p.stars[n]);
            assert(p.unspent==8);
        }
        ++cases;
    }
    puts("Bot loadout: 36 legal rank/side/style combinations and invalid inputs passed.");
    assert(cases==36);
    return 0;
}
