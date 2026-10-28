# Host spectator view

The local control panel includes a live view of the running match. Open
**Spectator view** while the session is ready. Closing it stops observation
without stopping the server. It starts closed after each server or map load.

## Camera controls

**Free flight** moves an invisible camera through walls and floors. Click or
focus the image, then use these controls:

| Control | Action |
| --- | --- |
| W / S | Move forward / backward |
| A / D | Move left / right |
| Q / E | Move down / up |
| Mouse or touch drag | Look around |
| Arrow keys | Look around with the keyboard |
| Escape, leaving the view, or switching tabs | Release movement |
| Buttons below the image | Hold to move on a touch screen |

**Follow player** follows the selected joined player's viewpoint. The target
is tied to that connection's identity, so another player cannot become the
target merely by taking the same slot or name. The camera follows ordinary
respawns on that connection. When the player leaves, it returns to free flight
at the last observed position; choose a new target explicitly.

Flying outside the map shows an empty view. The position and sector readout
helps you return. The camera is not constrained by collision surfaces.

After reloading a page with an open free camera, choose **Take camera control**
to move it. The same action transfers movement control from another panel tab.
Other open tabs can continue viewing without sending competing movement.

## Server setup

**Prepare spectator graphics when the server starts** is enabled by default in
Advanced settings (`spectator_rendering: true`). The engine retains its hidden
graphics context so the view can open later. This uses the same selected
offscreen, Xvfb, or existing-display backend as the dedicated engine. A working
OpenGL implementation is required.

Set the option to false and restart the session to run without the prepared
observer context. The setting does not open the view automatically. An older
engine without observer support can still run its normal game session; the
panel reports the view as unavailable.

The initial implementation supports the packaged Linux server and its Unix
frame channel. It streams a 640 × 360 image at up to five frames per second,
without audio. The image scales to the panel width. It is an operator's view,
so it does not display the host's weapon, HUD, automap, or console. Extra saber
and weapon cosmetic meshes from the engine's stateful weapon-render hook are
also omitted.

A hidden or closed tab stops requesting images. The server closes the view
after five seconds without an authenticated image request. Open it again when
you return. Held movement expires within 250 milliseconds if input stops.

## Game and client compatibility

Observation uses an independent camera with no player object, health,
inventory, collision body, network identity, or player slot. It cannot take
damage, pick up items, block a player, or send gameplay input. The existing
dedicated host remains in its normal role.

The observer's render pass suppresses gameplay sighting events, AI wakeups,
visibility changes, palette effects, and the stateful extra weapon hook. It
restores the shared render and animation caches used by gameplay before the
next simulation step. The camera does not edit templates, map geometry, COG
bytecode, or other data used to calculate the world checksum.

Retail DirectPlay, native OpenJKDF2, and the unchanged JKWeb client retain
their existing connection routes and game packet formats. The spectator
controls and images travel only through the authenticated host-management
interface. No game-client patch, spectator mod, or additional player slot is
required. Players still need matching original game content and mods, as for
any session.

Implementation details are in [SPECTATOR_PROTOCOL.md](SPECTATOR_PROTOCOL.md).
Compatibility evidence is recorded separately in
[QUALIFICATION.md](QUALIFICATION.md); historical live receipts identify the
exact binaries they tested.
