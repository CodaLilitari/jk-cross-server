#include <cassert>
#include <cstdio>
#include "Platform/Networking/GNS/AdminConnections.h"
#ifdef NDEBUG
#error Admin connection regressions require assertions
#endif

int main()
{
    jk_gateway::AdminConnections connections;
    connections.add(0); connections.add(1);
    assert(!connections.generation(0) && !connections.generation(1));
    connections.add(100); connections.add(101);
    const uint32_t first = connections.generation(100), other = connections.generation(101);
    assert(first && other && first != other && !connections.matches(999, first));
    assert(connections.matches(100, first) && !connections.matches(101, first));
    std::puts("PASS engine-owned nonzero incarnations are distinct and cannot be chosen by another peer");
    assert(connections.consume(100, first, 9));
    assert(!connections.consume(100, first, 9) && !connections.consume(100, first, 0));
    assert(!connections.consume(101, first, 10) && connections.consume(101, other, 9));
    std::puts("PASS execution rejects zero/duplicate requests and wrong actor generations");
    connections.remove(100); assert(!connections.matches(100, first));
    connections.add(100); const uint32_t rejoined = connections.generation(100);
    assert(rejoined && rejoined != first && !connections.consume(100, first, 11));
    assert(connections.consume(100, rejoined, 9) && connections.matches(101, other));
    std::puts("PASS a reused transport ID cannot execute an old occupant's pending authorization");
    connections.renew();
    assert(!connections.matches(100, rejoined) && !connections.matches(101, other));
    const uint32_t mapGeneration = connections.generation(100);
    assert(mapGeneration && connections.generation(101));
    connections.clear(); connections.add(100); assert(connections.generation(100) != mapGeneration);
    std::puts("PASS map/IPC resets invalidate old bindings and session clears never reuse the serial");
    for (uint32_t peer = 101; peer < 140; ++peer) connections.add(peer);
    unsigned registered = 0;
    for (uint32_t peer = 100; peer < 140; ++peer) registered += connections.generation(peer) != 0;
    assert(registered == 31);
    const uint32_t old = connections.generation(100); connections.add(100);
    assert(connections.generation(100) && connections.generation(100) != old);
    std::puts("PASS connection state is bounded to the host's 31 remote seats");
}
