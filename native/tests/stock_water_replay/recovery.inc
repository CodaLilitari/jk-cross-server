/* Fixture-only. Watch just three scalars during learner control. The full
 * initialized planner snapshots are witnesses, never restored into the bot. */
static struct {
    int tick, native, breathDebt;
    flex_t waterSince, previousHealth;
    const char *path;
    __typeof__(bot) *initialBot;
    __typeof__(nav) *initialNav;
} recovery;

static void recovery_begin(void)
{
    recovery.native = independent.fd < 0;
    const char *setting = getenv("LILY_RECOVERY_TICK");
    if (!setting) return;
    char *end;
    long boundary = strtol(setting, &end, 10);
    assert(*setting && !*end && boundary > 0 && boundary < 9000);
    assert(!recovery.native && independent.hold == 1);
    recovery.tick = (int)boundary;
    recovery.path = getenv("LILY_RECOVERY_HANDOFF");
    assert(recovery.path);
    assert(bot.goal == -1 && !bot.routeCount && !bot.routePos && bot.targetSlot == -1);
    assert(nav.objective == BOT_OBJECTIVE_NONE && !nav.objectiveValid && nav.objectiveRouteNode == -1);
    assert(!nav.waterExitPhase && !nav.waterExitUntil && !nav.jumpUntil && !nav.diveEscape);
    assert(bot.world == sithWorld_g_pCurrentWorld && bot.graphDone && bot.nNodes > 0 && bot.graphEdges > 0);
    recovery.initialBot = malloc(sizeof(bot));
    recovery.initialNav = malloc(sizeof(nav));
    assert(recovery.initialBot && recovery.initialNav);
    memcpy(recovery.initialBot, &bot, sizeof(bot));
    memcpy(recovery.initialNav, &nav, sizeof(nav));
    recovery.waterSince = nav.waterSince;
    FILE *file = fopen(recovery.path, "w");
    assert(file);
    fprintf(file, "{\"schema\":1,\"assigned_tick\":%d,\"reached\":false}\n", recovery.tick);
    assert(fclose(file) == 0);
}

static void recovery_observe(const SithThing *me)
{
    if (me->sector->flags & SITH_SECTOR_UNDERWATER) {
        if (!recovery.waterSince) recovery.waterSince = bot.now;
    } else recovery.waterSince = 0;
    recovery.previousHealth = me->actorParams.health;
    recovery.breathDebt = me->actorParams.endurance > 0;
}

static void recovery_bookkeeping(FILE *file)
{
    fprintf(file, "{\"progress_position\":[%.9g,%.9g,%.9g],\"stuck_at\":%.9g,"
            "\"water_since\":%.9g,\"previous_health\":%.9g,\"had_breath_debt\":%d}",
            bot.progressPos.x, bot.progressPos.y, bot.progressPos.z, bot.stuckAt,
            nav.waterSince, bot.previousHealth, nav.hadBreathDebt);
}

static void recovery_handoff(const SithThing *me, int step)
{
    /* The model touched only the normal tick clock and physical inputs.
     * Compare all other bytes, including the graph, RNG, route and timers. */
    __typeof__(bot) *start = recovery.initialBot;
    start->now = bot.now;
    start->frameDt = bot.frameDt;
    memcpy(start->axes, bot.axes, sizeof(bot.axes));
    memcpy(start->keys, bot.keys, sizeof(bot.keys));
    memcpy(start->presses, bot.presses, sizeof(bot.presses));
    memcpy(start->previous, bot.previous, sizeof(bot.previous));
    assert(!memcmp(start, &bot, sizeof(bot)) && !memcmp(recovery.initialNav, &nav, sizeof(nav)));
    assert(me == sithPlayer_g_pLocalPlayerThing && bot.world == sithWorld_g_pCurrentWorld);
    FILE *file = fopen(recovery.path, "w");
    assert(file);
    fprintf(file, "{\"schema\":1,\"assigned_tick\":%d,\"reached\":true,\"step\":%d,"
            "\"clock\":%.9g,\"held_buttons\":%u,\"rng\":%u,\"graph_nodes\":%d,\"graph_edges\":%d,"
            "\"pristine_planner\":true,\"goal\":%d,\"objective\":%d,\"objective_route_node\":%d,"
            "\"route_count\":%d,\"route_pos\":%d,\"water_exit_phase\":%d,\"before\":",
            recovery.tick, step, bot.now, independent_buttons(0), bot.random, bot.nNodes, bot.graphEdges,
            bot.goal, nav.objective, nav.objectiveRouteNode, bot.routeCount, bot.routePos, nav.waterExitPhase);
    recovery_bookkeeping(file);
    bot.progressPos = me->position;
    bot.stuckAt = bot.now;
    nav.waterSince = recovery.waterSince;
    bot.previousHealth = recovery.previousHealth;
    nav.hadBreathDebt = recovery.breathDebt;
    fputs(",\"after\":", file);
    recovery_bookkeeping(file);
    fputs("}\n", file);
    assert(fclose(file) == 0);
    recovery.native = 1;
    free(recovery.initialBot);
    free(recovery.initialNav);
}
