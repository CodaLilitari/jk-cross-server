# Multiplayer companion

An external program can attach to one running JK bot, read its observations and game chat, and request short-lived strategy changes. The native bot continues choosing inputs every frame if the companion disconnects. The Python client and service use the standard library. They do not require model credentials.

## Start a private session

Start your stock JK Cross Server first. Point the launcher at that server's configuration and an engine built with the JKCP v1 companion hooks. The bot still needs an ordinary free player slot. For a private session in which you authorize the companion to speak, run:

```sh
python -m bots.run --server-config instance.json --profiles boba_fett \
    --connect 127.0.0.1:3500 --companion-port 0 --companion-chat --no-taunts
```

Omit `--companion-chat` for observation and strategy only. The separate `--no-taunts` disables the bot's existing preset chatter. Port 0 selects a free loopback port. The launcher prints the service URL and the directory containing each bot's private credential. Only the selected bot can be accessed with its credential. The launcher removes the credentials and closes the service when the run ends. Regular manager launches retain their existing behavior.

For the following commands, substitute the directory printed by the launcher:

```sh
cred=/path/to/run/companion/boba_fett.json
companion() { python -m bots.companion_cli --credentials "$cred" "$@"; }
companion capabilities
companion observe
companion attach Lily
companion strategy pressure --ttl-seconds 8 --range 1.5 --risk 0.7 --request-id press-1
companion events --after 0
companion say "I have the west lift." --request-id lift-1
companion command lift-1
companion renew
companion release --request-id done-1
```

The CLI saves the lease in a private sibling `boba_fett.lease.json`. `--lease-file` before the subcommand sets a different path. Read operations do not require a lease. Reattach after a world/life transition or lease expiry. Mutations poll briefly for the native reply. Use `--wait 0` to return immediately or check a known request ID later. For scripted retries, set a unique request ID before the first call and reuse the exact original request body. The request ID printed by the CLI also works with `command`.

## HTTP interface

Use the literal loopback URL in the credential file. Send `Authorization: Bearer <token>` for every request and `Content-Type: application/json` for POST. The service requires an exact Host and permits either no Origin or its own Origin. It serves no web pages and accepts no cross-origin browser credentials. Each path begins with `/v1/bots/{bot_id}/`. POST bodies are single JSON objects with a 4096-byte limit. Unknown fields and duplicate fields are rejected.

The observation fence comprises `run_id`, `world_epoch` and `life_epoch`. Copy those three fields from the latest observation when attaching. Keep the returned fence with the lease. Commands racing a death, respawn, world replacement, restart or expired lease receive a conflict. A lease lasts 30 seconds and only its holder can renew it. An expired strategy returns to native autonomous control even if the Python process disappears.

| Method and suffix | Required input | Result |
| --- | --- | --- |
| GET capabilities | None | Fence, protocol, native_active, chat_enabled, modes, resource_bins, lease_seconds |
| GET observation | None | Fence, native_active, age_seconds, state. State is null before the first frame. Native_active requires state no more than 3 seconds old. |
| GET events?after=N | Optional exclusive cursor, default 0 | Fence, cursor, gap, wire_dropped, events. The latest 128 chat/sound events are retained. A history overrun sets gap. Wire sequence gaps increment wire_dropped and can include state frames. |
| POST attach | Fence, controller (1–64 ASCII letters/digits, underscore or hyphen) | Fence, lease_id, expires_in |
| POST renew | Fence, lease_id | Fence, lease_id, expires_in |
| POST strategy | Fence, lease_id, request_id, mode | Command receipt. Optional parameters below. |
| POST say | Fence, lease_id, request_id, text | Command receipt. Requires chat authorization at launch. |
| POST release | Fence, lease_id, request_id | Command receipt. Clears controller ownership and requests native autonomous control. |
| GET commands/{request_id} | None | Command receipt if retained |

Command receipts contain `run_id`, `world_epoch`, `life_epoch`, `request_id`, `kind`, `status`, and numeric `reason` (null before a native response). A new action returns HTTP 202 with `pending`. A native ACK can report `applied`, `rejected`, `expired`, `stale` or `rate_limited`. A command definitely discarded before dispatch can be `cancelled` or `expired`. If it was dispatched and no ACK arrives in its lifetime, its result is `unconfirmed`. An applied SAY means the bot submitted ordinary game chat. Independent receipt by a player is a separate observation. Never automatically retry an unconfirmed line under a new ID.

Native reason codes are 0 success, 1 invalid parameters, 2 unavailable player, 3 stale epoch or target, 4 reserved chat, 5 rate limit and 6 expiration. HTTP 400 indicates invalid input, 401 invalid credential, 403 disallowed origin/host or chat, 404 unknown operation or receipt, 409 stale identity/lease, conflicting request ID or unavailable native state, and 429 a limit. The hub retains up to 256 command receipts plus one reserved release and enforces 16 outstanding commands per bot. It preserves idempotency for the full active lease. As old lease history is evicted, an old ticket cannot execute another action.

Strategy modes are `autonomous`, `pressure`, `resource` and `recover`. The following optional fields are JSON numbers:

| Field | Values |
| --- | --- |
| ttl_seconds | 0.1–30, default 10. Expiration is capped by the current lease deadline. |
| weapon | 0 automatic, 1–10 stock weapon preference |
| resource | 0 automatic, or stock resource bin 11, 12, 14, 15, 40, 60, 62, 63, 64, 65 or 66 |
| range | 0 for the local default, or 0.2–12 world units |
| risk | 0–1, default 0.5 |
| focus_net_id, focus_guid | Both zero (automatic) or both from the current observation target |

Autonomous restores the native default policy. A weapon preference also increases the value of a useful, active matching pickup while the bot is healthy. The normal route planner must still find a reachable approach, and stock contact rules must award the pickup. A preference does not grant equipment, change damage or modify simulation speed. SAY accepts 1–110 printable ASCII characters, excludes the reserved first word `admin`, and has a five-second cooldown. Received chat is a typed observation. It has no command privileges.

The v1 state object reports slot, net_id, guid, signature, game_time, position, health, shields, mana, weapon, kills, deaths, mode, goal, flags, target, hearing, ammo and force_mask. The target and hearing can be null. A visible target includes its slot, net_id, guid, signature, position and age. Hearing provides category, position, age and strength. Ammo reports energy, power, explosives (thermal detonators) and rail. State age is in seconds. Chat events include player slot, net_id and text. Sound events include category, position, strength and uncertainty. Each event also includes its cursor and world/life epochs. The four sound categories are movement, weapon, projectile/explosion, and ambiguous Force/arrival.

In a supply trial, use successive live observations from the same life to check for an increase in
ammunition. The bot can touch an item and turn toward air before the stock host confirms a grant.
A route selection, item contact and inventory change answer different questions. JKCP v1 reports
ammunition counts and the current goal. Attributing a gain to a specific backpack also requires
evidence of its identity and the stock grant. See the [supply recovery receipt](../qa/bots-supply-recovery.json).

## Engine boundary

The launcher gives the ordinary native player a single inherited nonblocking Unix datagram socket via `JK_BOT_COMPANION_FD`. The companion pump is bounded per bot. A separate same-origin WASM host adapter can forward the same binary records over its own scoped channel. A local browser adapter can take exclusive ownership with `hub.open_browser_channel(bot_id)`, relay incoming bytes through `channel.enqueue_native_frame(data)`, and drain commands with `channel.outgoing_frames()`. The owner closes the channel at teardown. Its browser-facing transport must authenticate independently of the companion controller. The player credential never goes into a game packet or chat. The v1 snapshot above describes precisely what this API exports. Additional privileged match observations for competitive use require explicit fields and engine support.

Binary command deadlines are absolute monotonic seconds, not game time or a duration. The native same-host adapter uses the host monotonic clock. WASM has a different clock origin: the browser translates the hub deadline using the hub's sampled `server_mono` and the WASM timestamp taken before that HTTP exchange. Time spent in the exchange therefore consumes the command's remaining lifetime. The engine rejects nonfinite, expired, or more-than-30-second deadlines. Never send a hub clock value directly to WASM, and never turn a delayed delivery into a fresh full-length command.

On a new world, death or respawn, the engine publishes a state snapshot on the transition tick. It sends that snapshot before a sound detected on the same tick so the hub can accept events under the new world and life. Event sequence numbers continue across the transition. [Event-order regression](../qa/bots-companion-event-order.json)

Snapshots are normally emitted at 5 Hz. This API directs strategy; it does not replace frame-by-frame gameplay. A future diagnostic extension should explicitly identify water, attachment, breath, recovery and Force outcomes before external policies depend on them. The v1 fields cannot reliably infer all of those facts from position alone. Absence of an observed damage change is not proof that an opponent used Absorb.

The self-hosted unchanged JKWeb classic client can share a Cross Server session with native players. That transport relationship alone does not establish that the browser runs these hooks, that every current upstream netcode supports Cross Server, or that a public lobby accepts these bots. See the build-specific qualification notes and the [binary protocol specification](superpowers/specs/2026-11-21-companion-hearing-design.md).
