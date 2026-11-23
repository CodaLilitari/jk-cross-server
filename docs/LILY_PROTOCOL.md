# Lily companion extension

All frames use the existing JKCP v1 header and little-endian packed payloads. Only the seat configured with `JK_BOT_LILY=1` emits extension events or accepts extension commands. State, chat, release and strategy retain their v1 layouts. The world and life in the header fence all extension IDs. Sequence numbers in action progress are original command sequences. Sample and offer IDs are native counters independent of transport event sequence.

Use `bots.lily.protocol.decode_event(kind, payload)` for events (invalid or unknown returns None) and `encode_command(kind, body, deadline)` for command payloads (invalid raises ValueError). Constants are `OFFERS=5`, `PROGRESS=6`, `SENSE=7`, `COMMIT=19`, `MOTOR=20`. Format strings below use Python struct little-endian standard sizes with no alignment.

### Commands

| Kind | Layout after header | JSON body |
|---|---|---|
| COMMIT | `<dIIII` | `sample_id, revision, offer_id, node` |
| MOTOR | `<dIIB` followed by 1–5 `<HbbbbBBB` steps | `sample_id, revision, steps` |

Deadline is a finite positive absolute monotonic-clock second value at offset zero. Sample, revision and offer IDs are nonzero uint32. Node is an unsigned graph index below 8192. A sample must be from the current fence and at most 1 second old. Offers are valid for up to 2 seconds and can be superseded. Route commands use the most recent offers and a fresh sense sample. A step requires integer `duration_ms` (1–600); combined duration is at most 600 ms. Optional normalized numeric `forward, strafe, turn, pitch` default to zero, range [-1,1], quantized to signed hundredths. Optional integer `buttons, weapon, force` default to zero. Bits 0–4 are jump, duck, activate, primary fire, secondary fire. Weapon 1–10 selects an ordinary weapon slot. Force is a stock inventory bin 21–34. Zero means no selection/request. All command bodies reject unknown keys. A native owner admits at most one queued motor successor.

### Events

| Kind | Fixed layout | Trailing records |
|---|---|---|
| OFFERS | `<IIB` sample_id, offer_id, count | at most 8 `<IiBB3fff` node, sector, class code, item_bin, position[3], cost, utility |
| PROGRESS | `<IIIBBBBIi` action_seq, revision, sample_id, owner, phase, reason, outcome, applied_ms, node | none |
| SENSE | `<IIIIiBBBBI3f3f3f3ffff4fBBBB` sample_id, action_seq, revision, owner_sample_id, node, owner, phase, safe_handover, supported, medium, position[3], velocity[3], facing[3], up[3], head_pitch, breath_used_ms, tick_ms, axes[4], buttons, weapon, force, peer_count | at most 8 `<IIIi3f3f` slot, net_id, guid, sector, position[3], velocity[3] |

Decoded OFFERS gives `{sample_id,offer_id,choices:[{node,sector,class,item_bin,position,cost,utility}]}`. Class is `patrol` or `item` (codes 0,1); item_bin zero denotes an unknown or inapplicable bin. Cost is native graph path cost. Utility is a current native heuristic score. ID belongs to this offer set, not a persistent node identity.

Decoded PROGRESS gives `{action_seq, revision, sample_id, owner, phase, reason, outcome, applied_ms, node}`. Owner codes are `baseline, route, motor` (0–2). Phase codes 0–7 are `idle, queued, started, running, completed, interrupted, failed, expired`. Reason codes 0–8 are `none, released, life, world, deadline, invalid_route, survival, disconnected, replaced`. Outcome codes 0–2 are `none, arrived, playback`. Only arrived denotes physical route completion. A route invalidated while waiting to start is interrupted. A failed route had already started. Applied time is measured in simulated control-frame milliseconds. Terminal notices repeat with the same action identity. Deduplicate by fence and action identity.

Decoded SENSE gives `{sample_id,action_seq,revision,owner_sample_id,node,owner,phase,safe_handover,supported,medium,position,velocity,facing,up,head_pitch,breath_used_ms,tick_ms,axes,buttons,weapon,force,peers}`. Axes are an array [forward,strafe,turn,pitch] of applied ordinary axis values. Weapon and force are applied input selections. Medium is a string `air` or `water` (0,1). Node -1 means no committed route. Safe handover means the native owner is idle and no atomic baseline traversal/Force action is pending. Peers are synchronized engine observations including occluded players, with fields `slot,net_id,guid,sector,position,velocity`. Sense is emitted on control ticks at approximately 20 Hz. Stock state retains its 5 Hz cadence. No reliable content digest is present. Supply an explicit environment ID before persisting cross-run estimates.
