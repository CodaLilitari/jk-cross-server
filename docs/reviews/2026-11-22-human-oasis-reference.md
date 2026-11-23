# Human Full Force Canyon Oasis reference

## What was inspected

This is a bounded visual review, not a rating of the players or a demonstration
dataset. Public recordings supply examples of play in the requested ruleset.
The uploader's labels establish match context; the pictures establish only what
is visible. No human input logs or synchronized engine state were available.

| Source | Evidence reviewed | Context and limits |
| --- | --- | --- |
| [Spidey versus WD_Shinji](https://www.youtube.com/watch?v=XfU43kYxC88&t=120s) | A downloaded 02:00–03:00 excerpt, decoded into 60 one-second samples. All 60 samples were visually inspected. | The uploader identifies himself as Spidey and specifies Full Force on Canyon Oasis. He says Shinji had a new machine without 3D acceleration. This is a human reference, not a fair-strength benchmark. |
| [Spidey versus Durham](https://www.youtube.com/watch?v=_tTWrQepvn4) | Official seek previews at nominal ten-second spacing, 00:00–04:00. | The title identifies a tournament duel. Canyon Oasis geometry and attack effects are visible. Sparse previews cannot resolve a maneuver. |
| [March 2018 team match](https://www.youtube.com/watch?v=1dCC8uMLdjo&t=370s) | A downloaded 06:10–06:50 excerpt, decoded into 40 one-second samples. All 40 were inspected, plus four 640×360 stills around 06:26 and a 1920×1080 frame at 06:27. Also inspected seek previews spanning 04:10–08:10. | The uploader specifies Full Force 2v2 on Canyon Oasis and names CRoW/Spidey and best n world/Gordakarn as the teams. Participant lists alone do not identify the camera player. |

Times refer to the original videos and are nominal sample times. One-second
samples still omit most input transitions and collision frames. The HUD is too
small in the inspected contact sheets for reliable exact health, ammunition or
mana readings. One high-resolution check resolves a status message below.
No audio or subsecond input timing was analyzed. Raw third
party clips and preview images remain private research inputs and are not in the
repository.

The [review receipt](../../qa/lily-human-footage.json) records clip hashes,
decoded dimensions, durations, frame counts and the number of samples actually
inspected. Decoder validation of all frames is distinct from visual inspection
of the sampled stills.

## Observations from the Spidey excerpt

At 02:12–02:17 the camera follows the player along an elevated metal walkway.
At 02:18–02:23 the visible route passes the central pillar at a lower level.
At 02:24–02:32 bright attack effects appear around the adjacent ledges as the
player's position and view change. At 02:36–02:47 the samples move from an upper
rock surface through an enclosed passage and back toward the open arena.
At 02:48–02:59 the player returns to metal walkways and changes viewing direction.

These samples establish substantial movement through several connected areas
within one minute. They do not establish which item the player intended to reach,
whether a pickup was available, whether a shot connected, which Force power was
pressed, or the cause of each turn. The outlines and color changes are visual
facts; their presence is not an input label.

## Engineering hypotheses to test

The useful unit for future demonstrations is a decision interval with a visible
starting condition and an independently observed outcome. A bank escape, supply
run or disengagement can contain many changes of direction. Those changes alone
do not imply that its objective changed. Conversely, repeated visits to the same
landmark do not establish a bad loop: a supply circuit and an unsuccessful retry
can look similar without information about inventory, threats and progress.

For Lily this motivates a persistent task above the fast movement controller.
Let steering respond to new observations while preserving the selected target.
Record the reason for ending or changing a task. Evaluate eventual completion,
cost, loss of control and time spent, rather than treating every useful stride
as another win. This is a design inference, not a reconstruction of Spidey's
hidden intentions.

## Observations from the team excerpt

At 06:12–06:16 the samples follow the player through a confined passage.
At 06:19–06:24 the view crosses elevated stone surfaces overlooking lower paths.
Other actors and bright attack effects appear in the following samples, and
at 06:30–06:39 the route passes a narrow rock opening and areas below upper
walkways. At 06:40–06:49 the player is back in the open arena amid further effects.

An older tactics note attributed empty ammunition to roughly 06:26. The 640×360
stills did not establish an ammunition value or its causal role. A follow-up
1920×1080 frame at 06:27 explicitly says **"You are taking Grip damage!"**
The empty-ammo explanation remains unverified, and the status message supplies
a separate observed condition. It does not exclude simultaneous ammunition
depletion. The player and camera also cannot be identified as Gordakarn
solely from the uploader's team roster. The useful observed pattern is movement
through cover and elevation changes during a fight, not a verified inventory
policy or a prescribed retreat threshold.

Future tactical labels should therefore include known control-affecting combat
states. An apparent movement stall alone should not become a navigation-failure
label when another observed condition could explain it.

An annotated combat corpus will need higher-resolution HUD reads, contiguous
motion, camera identity, known rules and, ideally, demonstrations recorded through
our own input/state harness. The current clips cannot train a trustworthy
inverse-input model or justify changing jump timing, item timers, health cutoffs
or Force behavior. They also cannot establish that a larger language model or a
weight edit would improve control.

The concrete implementation is the [bank task](../superpowers/specs/2026-11-22-lily-bank-task-design.md).
Its exact stock-physics verdict is deliberately separate from these visual
observations. Human footage informs what to measure; engine evidence establishes
whether the implemented controller achieved it.

## Reproducible review helpers

`scripts/bot_development/analysis/review_youtube_previews.py` collects public
metadata and official seek previews without accounts or browser state.
`scripts/bot_development/analysis/sample_public_match.py` requests a bounded
public video interval and decodes indexed one-second samples. It needs `yt-dlp`
and FFmpeg supplied by the operator. Both write a new explicit output directory;
neither includes credentials, media or game assets in the release.

The first motion request from the research environment received HTTP 403. The
same public recording was accessible from the authorized desktop connection.
No account credentials, login, cookies or private browser session were used.
