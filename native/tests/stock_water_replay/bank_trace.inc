/* Evidence of actual inputs and physical outcomes, independent of live sense. */
static FILE *bankTrace;
static void bank_begin(const BotNode *dry)
{
    bankTrace = fopen(getenv("LILY_BANK_TRACE"), "w");
    assert(bankTrace);
    setvbuf(bankTrace, NULL, _IOLBF, 0);
    fprintf(bankTrace, "{\"event\":\"assigned\",\"sector\":%d,\"position\":[%.9g,%.9g,%.9g],\"seed\":%u}\n",
            dry->sector->id, dry->pos.x, dry->pos.y, dry->pos.z, bot.random);
}
static void bank_frame(SithThing *me, int tick, int step)
{
    unsigned buttons=0;
    for (int i=0; i<5; i++)
        if (bot.keys[lilyButtons[i]]) buttons |= 1u << i;
    fprintf(bankTrace, "{\"event\":\"control\",\"tick\":%d,\"step\":%d,\"owner\":\"%s\","
            "\"world_epoch\":%u,\"life_epoch\":%u,\"sample_id\":%u,\"action_seq\":%u,\"revision\":%u,\"wet\":%s,\"axes\":[%.9g,%.9g,%.9g,%.9g],\"buttons\":%u}\n",
            tick, step, bankOwner, companion.world, companion.life, bankSample, bankActionSeq, bankRevision,
            (me->sector->flags & SITH_SECTOR_UNDERWATER) ? "true" : "false",
            bot.axes[lilyAxes[0]], bot.axes[lilyAxes[1]], bot.axes[lilyAxes[2]], bot.axes[lilyAxes[3]], buttons);
}
static void bank_terminal(SithThing *me, const char *terminal, int ticks, int step, int streak, int breath)
{
    fprintf(bankTrace, "{\"event\":\"terminal\",\"terminal\":\"%s\",\"ticks\":%d,\"step\":%d,"
            "\"sector\":%d,\"health\":%.9g,\"dry_steps\":%d,\"first_breath_step\":",
            terminal, ticks, step, me->sector->id, me->actorParams.health, streak);
    if (breath < 0) fputs("null}\n", bankTrace);
    else fprintf(bankTrace, "%d}\n", breath);
    fclose(bankTrace);
}
