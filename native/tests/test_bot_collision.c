/* Exercise the actual swept-sphere helper and its original math routines.
 * No map assets, bot inputs, game state mutations, or network are needed. */
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "Engine/sithIntersect.c"
#ifdef NDEBUG
#error Assertions must remain enabled for the collision regression
#endif

static unsigned engine_asserts;
static void record_assert(const char *condition, const char *file, int line)
{
    (void)condition; (void)file; (void)line;
    engine_asserts++;
}
static HostServices test_services = {.assert = record_assert};
HostServices *pSithHS = &test_services;

static flex_t from_bits(uint32_t bits)
{
    float value;
    memcpy(&value, &bits, sizeof(value));
    return value;
}

int main(void)
{
    rdVector3 normal = {0, 0, 1}, plane = {0, 0, 0};
    /* The owned C2 debugger stop had moveDistance 0x3e51fcc7 and reported
     * hitDistance 0x3e51fcc8. This valid unit-direction fixture recreates that
     * exact one-ULP endpoint mismatch using the real plane/dot routines. */
    rdVector3 start = {0, 0, from_bits(0x3d27ff93)};
    rdVector3 direction = {0.9797938466072083f, 0, -from_bits(0x3e4ccf6c)};
    flex_t distance = from_bits(0x3e51fcc7), hit = -1;
    int result = sithIntersect_CheckSphereHit(&start, &direction, distance,
        0, &normal, &plane, &hit, RAYCAST_1 | RAYCAST_200);
    if (!result || hit < 0 || hit > distance || engine_asserts) {
        fprintf(stderr, "FAIL endpoint: hit=%.9g bound=%.9g engine_asserts=%u\n",
            (double)hit, (double)distance, engine_asserts);
        return 1;
    }
    puts("PASS one-ULP swept-sphere endpoint stays within requested travel without assertion");

    start.z = 1; direction = (rdVector3){0, 0, -1};
    assert(sithIntersect_CheckSphereHit(&start, &direction, 2, 0.25f,
        &normal, &plane, &hit, 0) == 1);
    assert(fabsf(hit - 0.75f) < 0.000001f);
    assert(sithIntersect_CheckSphereHit(&start, &direction, 0.5f, 0.25f,
        &normal, &plane, &hit, 0) == 0);
    direction.z = 1;
    assert(sithIntersect_CheckSphereHit(&start, &direction, 2, 0.25f,
        &normal, &plane, &hit, 0) == 0);
    start.z = -1; direction.z = -1;
    assert(sithIntersect_CheckSphereHit(&start, &direction, 2, 0.25f,
        &normal, &plane, &hit, 0) == 0);
    assert(!engine_asserts);
    puts("PASS ordinary interior hits, too-short sweeps, outward travel, and back faces retain behavior");

    start.z = 0.125f; direction.z = -1; hit = 9;
    assert(sithIntersect_CheckSphereHit(&start, &direction, 1, 0.25f,
        &normal, &plane, &hit, 0) == 1);
    assert(hit == 0);
    hit = 0.5f;
    assert(sithIntersect_CheckSphereHit(&start, &direction, 1, 0.25f,
        &normal, &plane, &hit, RAYCAST_400) == 1);
    assert(hit == 0.75f && !engine_asserts);
    puts("PASS existing overlap and special radius-adjustment behavior is unchanged");
    return 0;
}
