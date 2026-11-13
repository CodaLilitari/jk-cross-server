# Persistent administration through game chat

The server can issue a persistent private credential for an administrator, then
accept authorized commands through ordinary game chat. The bundled dedicated
server patch and its matching manager are required. Retail JK/MotS,
OpenJKDF2, and JKWeb keep their existing executables and game content.

The downloaded `.cog` is an **inert credential container**, with its metadata in
a comment and empty `symbols`/`code` sections. Keep it outside the game's loaded
files and archives. It is not a game script to install, a checksum exception, or
a client modification. The supplied offline helper reads its exact metadata and
calculates a proof; it never executes COG code.

## Issue a key explicitly

Open the server's existing local control panel and find **Admin credentials**.
Enter a label for an administrator or device, select the desired capabilities,
and choose **Issue and download key**.

| Capability | Allows |
|---|---|
| Advance to the next level | `admin next level` |
| Kick players | `admin kick #slot` or an exact, unambiguous current player name |

Labels describe credentials for the operator. They are not player-name
whitelists, and a matching display name does not grant authority. Issue a
separate key for each administrator or device so it can be revoked independently.

Issuance produces `jk-admin-key-<id>.cog` as a one-time download. The normal
credential list contains identifiers, labels, capabilities and timestamps;
it never returns the secret or offers a repeat download. If a download is lost,
use **Rotate and download**. Rotation revokes the old key and issues a new key
with the same label and capabilities in one transaction.

The first explicit issuance creates the server's persistent identity. Merely
opening the panel, viewing status, starting a game, stopping a game, or restarting
the panel does not create or rotate keys. Keys remain valid across these events
until explicitly revoked or rotated. Authentication of a live connection is
temporary, as described below.

Protect the downloaded file and give it to its intended administrator outside
game chat. Do not paste the file's metadata or secret into chat, a console, a
public issue, or a server name.

## Authenticate from an unchanged client

1. Download **Offline browser helper** from the panel, extract all three files
   together, and open `admin-helper.html` locally. The files are HTML, JavaScript,
   and CSS; the helper has no network access or external dependencies.
2. In the game, type `admin login`. The server replies to that connection with
   an ASCII challenge beginning `JKADMIN1:`.
3. In the offline helper, select the issued `.cog` file and paste the complete
   challenge. Choose **Generate proof**. A key for a different server is rejected.
4. Copy the generated `admin prove <key-id> <proof>` line into game chat before
   the challenge expires. The server confirms successful authentication.
5. Use `admin status` to check the connection and `admin help` for the commands.
   Use `admin logout` when finished.

**Ordinary peer chat can display the one-time proof.** The long-term key stays
offline. A proof for your legitimate challenge is bound to the actual connection
and generation that requested it; replaying that proof from another connection
or after consumption fails. The server/manager suppress proof values from their own
general logs. This does not imply that every unchanged peer hides the chat line.

Use only the immediate response to your own `admin login`; never answer a
challenge forwarded by another player. The offline helper verifies the server
ID in your credential, but it cannot authenticate the chat sender or independently
verify that a pasted nonce belongs to your own live connection. This manual
workflow is not resistant to substituted-challenge phishing or relay. A trusted
view of the live connection would be needed for that stronger guarantee.

A challenge expires after two minutes. A syntactically complete proof submission
consumes its challenge, including when the key ID or MAC is incorrect. Request
a new challenge after a mistake.
Successful authentication lasts 15 minutes on that connection. Disconnects,
connection-generation changes, engine/IPC resets and level/session resets invalidate
the relevant grants. Starting a new login replaces that connection's previous
challenge and grant. The persistent credential itself remains available for a
later login.

### Python helper

Download **Python helper**, or use the repository's standalone
[`tools/admin_key.py`](../tools/admin_key.py). It requires only Python's standard
library and works without importing the server installation:

```sh
python3 admin_key.py --key /private/path/jk-admin-key-ID.cog \
  --challenge 'JKADMIN1:SERVER_ID:NONCE'
```

Replace the illustrative challenge with the exact line supplied by the server.
The tool prints only the proof command on success. It does not connect to a
server or execute the COG. Its errors do not echo key material or file contents.

## Commands and execution

| Command | Behavior |
|---|---|
| `admin help` or `admin` | Show the available command forms. |
| `admin login` | Request a fresh challenge for this connection. |
| `admin prove <id> <mac>` | Submit the helper's proof for the pending challenge. |
| `admin status` | Report whether this connection currently has an active grant. |
| `admin players` | With an active grant, request the server's current player list. |
| `admin next level` | With `match.next`, request the ordinary next authored level. |
| `admin kick #slot` | With `player.kick`, request removal of the current player in that listed slot. |
| `admin kick Exact Name` | With `player.kick`, request an exact, unambiguous name match. |
| `admin logout` | Clear this connection's pending challenge and grant. |

Use `admin players` immediately before a kick and select the current target.
The dedicated server resolves and validates the target; a name or slot is a
selection argument, never an authentication identity. The host and invalid
targets are rejected. Commands do not provide arbitrary console, shell, file,
script, or COG execution.

The dedicated engine alone performs game actions. Next-level uses the ordinary
end-level/tally transition and authored episode progression, including the
stock transition delay. It can reject a single-level session, an invalid next
entry, or a transition already in progress. A successful command request is not
by itself evidence that every connected client completed the transition.

The manager accepts only the dedicated patch's authenticated local IPC events,
which carry the transport-derived player identity and connection generation.
The engine validates that identity again before executing a typed action.
Public clients cannot directly send a manager grant or use the local IPC token.
See the [controller](../manager/chat_admin.py) and
[IPC implementation](../web_gateway/ipc.py) for the integration contract.

## Revoke, rotate, and protect persistent state

Choose **Revoke key** in the panel to revoke that credential. The policy checks
the current store on every privileged command; an already authenticated
connection cannot keep using a revoked or rotated key. Other credentials are
unaffected. Revoked records are retained for operator history.

The default manager store is:

```text
<state-dir>/authority/keys.sqlite3
```

This is outside `runs/`, staged game content, per-session files and the generic
game configuration. It persists independently of a particular match. The
authority directory uses mode `0700`, and the database uses mode `0600`.
The implementation rejects symlinks, nonregular database/journal files,
unexpected ownership, insecure permissions, corrupt data, and unsupported
schema. It does not silently regenerate an identity when existing state is bad.

The database contains HMAC-equivalent secret material. Protect it and its
backups as private credentials. Back up the authority while it is idle or use a
consistent SQLite backup; preserve permissions. Restoring an old backup can
also restore older revocation state, so reconcile revocations before enabling
administration again. Losing the authority database loses that server's
credential identity; starting a new authority requires new keys.

The manager's update/package and game-staging paths protect the authority
directory and generated `jk-admin-key-*.cog` files. Do not deliberately place
keys in a map, mod, browser asset bundle, repository, or loaded game folder.
Credential issuance is never part of a normal session-start workflow.

An unavailable or invalid authority denies privileged commands while ordinary
gameplay can continue. Repair or restore the private store through the operator's
normal filesystem controls; the panel does not repair unsafe permissions or
overwrite corrupt state automatically.

## Proof format and limits

The implementation uses standard HMAC-SHA256 with a random 32-byte secret per
credential. The persistent server ID and each challenge nonce have 128 bits of
randomness; key IDs have 64 bits and are identifiers, not secrets. The challenge
has this exact form:

```text
JKADMIN1:<32 lowercase hex server ID>:<32 lowercase hex nonce>
```

The HMAC input is ASCII, with no trailing newline:

```text
JKADMIN1\n<server ID>\n<nonce>\n<16 lowercase hex key ID>
```

The proof is `admin prove <key ID> <64 lowercase hex HMAC>`, within the ordinary
127-character chat bound. Verification uses constant-time MAC comparison.
Pending challenges live only in the current policy instance and are bound to
the actual unsigned 32-bit player ID and connection generation. Replays after
consumption, expiry or reset fail. Grants are also connection-bound and cannot
be restored merely by reusing an old player ID.

The policy bounds pending challenges, grants and rate-limit state. It permits
four challenge requests and eight proof submissions per connection per minute,
with an additional global challenge bound. Repeated attempts can require waiting
before requesting a fresh challenge. The credential ledger is also bounded and
retains revocation records.

The helper accepts only the exact inert container and canonical metadata schema.
It rejects duplicate fields, appended code, malformed identifiers, unsupported
versions/capabilities, and challenges for another server. The browser helper uses
Web Crypto; the CLI uses Python `hmac`/`hashlib`. Neither implements custom
cryptography or changes a game checksum.

## Evidence and qualification

[`tests/test_authority.py`](../tests/test_authority.py) exercises persistence,
explicit issuance, permission/link/corruption rejection, rollback and revocation,
connection/generation binding, replay and timeout boundaries, rate/state bounds,
capability separation, API guards, download redaction, and parity of the actual
browser Web Crypto and standalone Python helpers. The broader controller and
engine tests and connected gameplay receipts are separate.

The store/policy/helper tests do not establish a successful live kick or map
transition for a particular client build. Connected results must name the exact
dedicated binary, unchanged clients present, command, target and observed result;
an IPC acknowledgement or printed request is not sufficient gameplay evidence.

### Live qualification by dedicated build

The [final live receipt](../qa/chat-admin-live-4be9.json) records the completed
fixture, with successful, incomplete, and unrun checks distinguished. It names
dedicated binary `4be9e8fa`, DirectPlay adapter `a6ee4452`, bot client `50924ed7`,
and the exact unchanged human-client artifacts.
Historical results retain their own binary attribution:

| Dedicated build | Recorded live evidence |
|---|---|
| `6c4c25dd` | Native and retail authentication; a native administrator kicked retail; native and bots reached the next map and native reauthenticated. Browser reconnect/authentication and automatic retail map continuation remained limited. See [round one](../qa/chat-admin-live-6c4c.json). |
| `234edc4f` | The same persistent key authenticated after a new panel process. Native observed retail and both bots on the next map, followed by grant denial and reauthentication. Browser was closed during that transition. See [round two](../qa/chat-admin-native-round2.json). |
| `4be9e8fa` | Same-key authentication after game-only restart; simultaneous authentication of all three unchanged human clients; retail-admin native kick followed by fresh-identity rejoin and reauthentication; recovered-browser rejoin and permission denial; live key revocation. The browser reauthentication retry was blocked by its input driver. See [round three](../qa/chat-admin-native-round3.json) and the current receipt. |

In the final-build snapshot, original JK 1.00 retail, the pinned unchanged
OpenJKDF2 client, and the published unchanged JKWeb client were fully joined on
`JK1MP/m2.jkl` with Boba and Jan bots. Retail and browser rosters agreed on all
five playing peers, and three connection-bound grants referenced the same
persistent test credential. The native client had first received an actual
denial after the game-only restart, then authenticated with that existing key;
the panel process and credential were retained.

The retail administrator subsequently kicked the native player. The target left
the game through its ordinary tally/menu path while the server continued. The
same unchanged native process rejoined with a different canonical identity and
connection generation, received an actual permission denial, and authenticated
again with the same key. Its normal discovery/join window recorded no surrogate
replacement churn after the native discovery reservation refinement.

These were bounded stages. The fixture later reached its 8 GiB memory limit;
the browser process tree exited, and retail and Jan subsequently left during
that interval. Cumulative OOM counters do not identify which process was killed
or establish every departure's cause. Only Boba and the native player were
observed at the native reauthentication checkpoint, so uninterrupted five-player
participation through the later actions is not claimed.

The unchanged browser was then restarted, its normal menu set to 30 FPS, and it
rejoined through ordinary menus. At 08:23:25 UTC it was fully joined on `m2`
with a fresh canonical identity, alongside Boba, native, and the rejoined retail
player. Its prior grant did not transfer: the browser received an actual
permission denial. A fresh login challenge reached it, but the private input
helper reported completion without an observed proof chat or new grant. A
sequential input retry later hit the 30-second watchdog and closed the browser
context. Browser recovery/rejoin passed; this reauthentication retry is
incomplete. The earlier successful browser authentication remains separately
recorded. No privileged browser map or kick command was submitted.

Live revocation passed on the final build. The native connection's existing
grant was first verified, then the panel revoked the original test credential.
Its `admin next level` command received an actual permission denial 131.378
seconds before that grant's nominal expiry. A fresh `admin login` received "No active admin
credentials have been issued." Native and retail remained in multiplayer on
`m2` with Boba, the same server and adapter processes continued, and the safe
manager observer reported no grants or queued commands. Login produced no new
challenge, so no fresh revoked-key proof was attempted and no second QA key was
issued. That narrower live result is distinct from the separate revoked-proof
policy tests.

An authorized next-level transition on final build `4be9e8fa` was not run; the
last sampled map remained `m2`. The denied revocation command is not a successful
map transition. The intermediate `234edc4f` native/retail transition to `m4`
remains attributed to that earlier binary. Live MotS administration is also
unqualified.

Fixture cleanup completed with an outer exit status of zero and an empty process
registry. All 18 recorded game, browser, retail, native, display, and namespace
keeper processes were absent, with no processes left in the owned namespace.
The test credential was revoked before its private key file, authority database
directory, and panel token were removed.

The separate [server Python regression receipt](../qa/server-final-python.json)
records a passing result for all 149 distinct tests across 158 executions. Nine
initial updater cases encountered the zero-free-disk guard; all nine unchanged
cases passed after disk cleanup, including actual child-process crash recovery.
The original disk failures remain in that receipt, and all 36 recorded source
hashes were unchanged between the initial runs and the focused rerun.

The manual copied-challenge workflow retains the substituted-challenge
phishing/relay limitation described above; successful live authentication does
not remove that limitation.
