/* Called once, after each stock physics move. An invalid attachment is -1. */
static int bank_supported_step(int *streak, int target, int sector,
                               int attached_sector, int dry)
{
    if (dry && sector == target && attached_sector == target)
        ++*streak;
    else
        *streak = 0;
    return *streak >= 38;
}
