/* Fixture-only include after the original jkBotLily.inc. Observe the actual
 * arbitration branch before Lily_EndFrame clears the last tick's identity. */
static const char *bankOwner;
static uint32_t bankActionSeq, bankRevision, bankSample;
static int Bank_ObserveDrive(SithThing *self)
{
    int route = lily.active.owner == LILY_ROUTE || lily.queued.owner == LILY_ROUTE;
    int handled = Lily_Drive(self);
    if (!handled)
        bankOwner = "baseline";
    else if (lily.active.owner == LILY_MOTOR && lily.active.seq) {
        bankOwner = "motor";
        bankActionSeq = lily.active.seq;
        bankRevision = lily.active.revision;
        bankSample = lily.active.sample;
    } else
        bankOwner = route ? "unknown" : "neutral";
    return handled;
}
#define Lily_Drive Bank_ObserveDrive
