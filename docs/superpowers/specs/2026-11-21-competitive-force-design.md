# Competitive Force builds and input sequencing

This increment continues the competitive-bot design. It supplies deliberate legal builds and improves the ordinary native Force input policy. It does not establish top-player performance, implement the full predictive splash controller, or connect an external companion.

## Evidence and choices

[Jeb Springfield's BGJ guide](https://www.jkdf2.net/articles/jebs-bgj-ff-tips-mostly-1-on-1-tactics/) recommends four stars each in Jump, Speed, Seeing, Pull, Grip and Destruction for rank-eight dark FF duels. It describes a situational two-star transfer from Pull to Throw against Protection. That alternative depends on throwable map objects and is retained as future matchup knowledge, not automatically selected here.

[AcidRain's Oasis guide](https://www.jkdf2.net/articles/ffo-guide-dark-side/) emphasizes movement routes, item denial, Grip, and combined Destruction/concussion pressure. Its use of Seeing differs from Jeb's BGJ guidance. These are firsthand historical starting points; current competition must test them under the actual client versions, rank, map and rules.

The light benchmark build is four stars each in Jump, Speed, Seeing, Pull, Healing and Absorb. This is an engineering baseline inferred from the stock mechanics, not a sourced claim that a particular champion used that exact allocation. Both sides preserve mobility and neutral counters instead of automatically sacrificing them for the rank-eight ultimate.

The inspected retail scripts establish:

- Seeing prevents new Blind effects; casting it after blindness begins does not clear the existing effect. Its map markers are not unrestricted three-dimensional target knowledge.
- Any active Absorb prevents weapon disarm. At four stars it converts eligible magic damage fully to mana. Grip's movement restriction remains; Protection blocks that restriction too.
- Grip acquires a local target on a 0.33-second pulse and starts its effect on key release. Selecting a different Force power cancels it. Ordinary weapon attacks can accompany the continuing effect. The bot must release only for its intended, still-valid target.
- Destruction has a three-second cooldown on its own inventory bin. The bot's previous universal 2.4-second gap between different powers is not a stock rule.
- Protection deducts its nominal cost without the generic minimum-mana check used by most powers. Its legality and its strategic desirability must be separate decisions.

The original script hashes are recorded in `qa/bots-force-source-audit.json`. No original scripts are committed. Timing statements are script observations, not connected-match receipts.

## Builds

Add a `competitive` Force style alongside the existing `balanced` and `master` styles. Preserve their previous planner behaviour for compatibility. All new allocations occur in the isolated saved multiplayer character before joining; no live stars, mana, health or ammunition are granted.

The competitive planner spends at most rank times three stars, never exceeds four per power, respects neutral rank one and side-power unlock ranks four through seven, and never allocates the opposite side or directly sets an ultimate. At rank eight each of the six selected powers reaches four stars. Lower ranks allocate one level at a time across the ordered eligible list, retaining a legal fallback when advanced powers are not available.

Dark priority list: Jump, Speed, Seeing, Pull, Grip, Destruction.

Light priority list: Jump, Speed, Seeing, Pull, Absorb, Healing.

Shipped persona profiles select `competitive` after the matching executable is built. Explicit legacy styles remain selectable. Omitted custom-profile style retains its historical `balanced` interpretation.

## Runtime policy

Enable the new sequencing policy only for the competitive style. Keep the existing live `force_enabled`, `sabers_only`, peace and team restrictions, inventory availability, actual bin waits, actor state, range, aim and line-of-sight gates.

Before an observed engagement, consider Seeing while unblinded. A recently observed threat or unexplained received damage can also justify it; do not inspect hidden enemy inventory or clear a blindness flag. Absorb may be prepared for a visible engagement or a recent received Force threat. Both use normal costs and the existing activation state, and urgent healing remains a higher priority.

Use a short input sequencing guard between different powers while obeying the actual COG-owned per-bin cooldown. A held power is still held through acquisition and receives a normal release. Do not send multiple new Force requests in a frame or mutate the COG's waits.

For Grip, validate the local inventory COG's selected victim against the requested player's thing identity before releasing. If it is unknown, absent, mismatched, or the player identity has changed, take the ordinary deselection cancellation path. Never resolve an ambiguous marker by writing a target into the COG. While a successfully released Grip remains active and its target remains allowed, avoid switching to another Force power automatically; ordinary weapon inputs continue. Existing peace/team cancellation still has priority.

Resource Pull, enemy counter inference, observation-limited Seeing minimap interpretation, map-specific burst planning and optimal Force movement remain subsequent work. The presence of a competitive profile is not evidence those behaviours exist.

## Verification and packaging

Test all legal rank/side/style allocations, exact rank-eight selected powers, invalid styles and default profile transport. Exercise the actual patched native controller with controlled perception and inventory fixtures: proactive Seeing, existing blindness, a cross-power sequence, real bin-wait rejection, Grip marker match/mismatch, identity changes, post-release weapon continuation, and peace/Force-disable cancellation.

Recompile both `jkBot.c` and `jkGUIMultiplayer.c` because the loadout planner is included by the latter. Preserve the native multiplayer compile flags and record source, object, archive and executable hashes. Candidate packaging must retain the corresponding patch and relink inputs. A successful compile or hotkey test is not evidence that a remote victim received the effect.

Connected qualification requires ordinary client join, the saved build actually loaded, COG-owned mana/effect results, and an independently observed target outcome. If the needed asset/runtime path is unavailable, retain a clearly labelled candidate and report the exact missing test rather than claiming multiplayer qualification.
