/* Optional private demonstrations, taken before ordinary stock input handling. */
static FILE *motorTrace;
static const char *motorEpisode, *motorPolicy, *motorGroup;
static rdVector3 motorStart;
static void motor_trace_begin(SithThing *me)
{
    const char *path=getenv("LILY_MOTOR_TRACE");
    /* The imitation schema describes baseline demonstrations exclusively. */
    if (!path || lily.enabled) return;
    motorEpisode=getenv("LILY_MOTOR_EPISODE");
    motorPolicy=getenv("LILY_MOTOR_POLICY");
    assert(motorEpisode && motorPolicy);
    motorGroup=getenv("LILY_MOTOR_GROUP");
    if (!motorGroup) motorGroup=motorEpisode;
    motorTrace=fopen(path,"w"); assert(motorTrace);
    motorStart=me->position;
}
static void motor_trace_frame(SithThing *me,const BotNode *dry,float elapsed,float dt)
{
    if (!motorTrace) return;
    rdVector3 delta=Bot_Sub(dry->pos,me->position);
    float distance=sqrtf(delta.x*delta.x+delta.y*delta.y+delta.z*delta.z);
    if (distance<0.00001f) return;
    unsigned buttons=(bot.keys[INPUT_FUNC_JUMP]?1:0)|(bot.keys[INPUT_FUNC_DUCK]?2:0);
    fprintf(motorTrace,"{\"schema\":1,\"event\":\"observation\",\"monotonic_seconds\":%.9g,"
        "\"run_id\":\"stock-water-replay\",\"world_epoch\":1,\"life_epoch\":1,"
        "\"episode_id\":\"%s\",\"split_group\":\"%s\",\"policy_hash\":\"%s\",\"controller\":\"native-baseline\","
        "\"goal\":{\"position\":[%.9g,%.9g,%.9g],\"direction\":[%.9g,%.9g,%.9g],\"distance\":%.9g},"
        "\"state\":{\"health\":%.9g,\"shields\":%.9g,\"mana\":%.9g},"
        "\"sense\":{\"action_seq\":0,\"owner\":\"baseline\",\"phase\":\"running\","
        "\"position\":[%.9g,%.9g,%.9g],\"velocity\":[%.9g,%.9g,%.9g],"
        "\"facing\":[%.9g,%.9g,%.9g],\"up\":[%.9g,%.9g,%.9g],"
        "\"head_pitch\":%.9g,\"supported\":%s,\"medium\":\"%s\","
        "\"breath_used_ms\":%u,\"tick_ms\":%.9g,\"axes\":[%.9g,%.9g,%.9g,%.9g],\"buttons\":%u}}\n",
        elapsed,motorEpisode,motorGroup,motorPolicy,dry->pos.x,dry->pos.y,dry->pos.z,delta.x/distance,delta.y/distance,delta.z/distance,distance,
        me->actorParams.health,sithInventory_GetInventory(me,SITHBIN_SHIELDS),sithInventory_GetInventory(me,SITHBIN_FORCEMANA),
        me->position.x,me->position.y,me->position.z,me->physicsParams.vel.x,me->physicsParams.vel.y,me->physicsParams.vel.z,
        me->orient.lvec.x,me->orient.lvec.y,me->orient.lvec.z,me->orient.uvec.x,me->orient.uvec.y,me->orient.uvec.z,
        me->actorParams.headPYR.x,(me->attach_flags&SITH_ATTACH_SURFACE)?"true":"false",
        (me->sector->flags&SITH_SECTOR_UNDERWATER)?"water":"air",me->actorParams.endurance,dt*1000,
        bot.axes[INPUT_FUNC_FORWARD],bot.axes[INPUT_FUNC_SLIDE],bot.axes[INPUT_FUNC_TURN],bot.axes[INPUT_FUNC_PITCH],buttons);
}
static void motor_trace_end(SithThing *me,int success,float elapsed)
{
    if (!motorTrace) return;
    fprintf(motorTrace,"{\"schema\":1,\"event\":\"outcome\",\"monotonic_seconds\":%.9g,"
        "\"run_id\":\"stock-water-replay\",\"world_epoch\":1,\"life_epoch\":1,"
        "\"episode_id\":\"%s\",\"controller\":\"native-baseline\",\"policy_hash\":\"%s\",\"action_seq\":0,"
        "\"status\":\"%s\",\"physical_success\":%s,\"duration_seconds\":%.9g,"
        "\"criterion\":\"38 consecutive supported dry physics steps\","
        "\"start_position\":[%.9g,%.9g,%.9g],\"end_position\":[%.9g,%.9g,%.9g]}\n",
        elapsed,motorEpisode,motorPolicy,success?"completed":"failed",success?"true":"false",elapsed,
        motorStart.x,motorStart.y,motorStart.z,me->position.x,me->position.y,me->position.z);
    fclose(motorTrace); motorTrace=NULL;
}
