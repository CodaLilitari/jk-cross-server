# Changes

## Unreleased — Bot branch refresh and host spectator

- Incorporate main into the configurable-player-bots branch while retaining
  bots, normal map progression, persistent chat administration, reconnect
  identities and the later DirectPlay surrogate lifecycle behavior.
- Add explicit auto/offscreen/Xvfb/existing-display startup, separate Wine
  display preparation, and readiness based on a valid current session descriptor.
- Retain the web interface and its controls in an original JK-inspired console
  with section navigation, responsive layouts and clear keyboard focus.
- Add toggleable free-flight and player-follow spectator modes. The host camera
  has no gameplay actor, collision, health or network identity, and consumes no
  player slot. It uses an authenticated private frame/control path.
- Protect gameplay from render-pass side effects, expire held movement, tie
  camera commands to current epochs, reject departed follow identities, and
  close observation when the viewer lease expires.
- Retain retail, native OpenJKDF2 and unchanged JKWeb connection routes and
  game-facing packet formats. Keep the JK Cross Server name.
- Correct player-limit wording: the dedicated host is added separately.
  Configuration ceilings and the existing conservative bot headroom rule remain.

## Unreleased — Original JK DirectPlay adapter corrections

- Correct original JK roster statistics: team is U8 before signed 16-bit
  kills, deaths, suicides and score. Reorder the native fields in both
  directions without narrowing kills or changing the other signed values.
- On eligible failed JK sends, query DirectPlay before discarding an obsolete
  destination. Require a complete player snapshot and an owned, local, present
  sender; reject present destinations and broadcasts with live remote players.
  Keep other send failures fatal and log sender, destination and byte count.
- Include the tested gateway `73158f1dda3782ab9ab80b175fcf9d08ba576c36db24687bfbb9fbfb29af3c95`,
  score-layout regressions and 15 departure-policy assertions. MotS handling
  is unchanged; its roster field semantics were not newly verified.
- Import three adapter QA receipts with their original fixture identities and
  historical outcomes. The scoreboard retest passed field conversion but
  failed on retail departure. The final gateway passed normal join, leave,
  rejoin and leave; its failed-send reconciliation branch was not exercised
  live. See `docs/QUALIFICATION.md` for exact scope and provenance.

At that earlier main-branch checkpoint, the integration changed only the
adapter and its documentation/tests. The native engine, browser transport,
updater, dependencies and version were unchanged, and the separate bot
prototype used by its test fixture was not included. The current bot-branch
refresh above retains the newer bot and adapter behavior and rebuilds the
dedicated engine with the host spectator.

## 0.3.0-dev — GitLab release updates

- Check this project's public GitLab releases on startup and every six hours,
  with manual checking in the browser panel.
- Install verified release ZIPs between sessions, with optional automatic
  installation, persistent preferences, and an automatic panel restart.
- Preserve configuration, game content, browser files, Wine prefixes, and other
  unmanaged data; reject local application edits and file collisions.
- Coordinate installations and sessions across panel instances, defer while a
  session uses the installation, and prevent stale panels from starting games.
- Verify package and file hashes, retain a previous-version backup, roll back
  failed writes, and recover interrupted installations before server startup.
- Provide a deterministic release packager, manifests, focused updater tests,
  and documented upgrade instructions. Git checkouts and dependency changes
  use an explicit manual upgrade path.

At the original 0.3 updater checkpoint, the native engine, DirectPlay bridge,
client transports and dependency lists were unchanged from 0.2.0-dev. That
historical updater qualification is separate from the adapter correction above
and the retained stock-session and browser-download qualification.

## 0.2.0-dev — Browser asset delivery

- Send the selected missing custom JK/MotS episode through the published
  browser client's existing JKMT transfer protocol.
- Advertise the active mod with the existing JKMD fingerprint and prepare a
  deterministic mod pack for the browser's normal download/restart flow.
- Reconstruct matching original content through the client's retail-reference
  scheme; original game files and the special MotS Remastered pack remain
  local client requirements.
- Add a default-enabled download switch and a live browser-content section in
  the Python administration panel, including fingerprints and transfer counts.
- Keep asset work separate from game messages, with bounded queues,
  backpressure, retry handling and cancellation on departure.
- Reject resource overrides that would be missing from the advertised content;
  custom resources belong in the selected episode or configured mod folder.
- Accept the original installed resource aliases `res1.gob`, `res1low.gob` and
  `jkmsnd.goo` during server preflight.

The regression suite has 34 passing checks. Actual unchanged-browser download,
restart and rendered-game observations are recorded separately in
`docs/QUALIFICATION.md`. The native engine and original-retail bridge binaries
are unchanged from 0.1.0-dev. Clients do not need an engine patch.

## 0.1.0-dev — Dedicated cross-client session

Initial native dedicated engine, original DirectPlay adapter, browser gateway,
Python administration panel, pinned-client fetcher and reproducible source /
build materials. Qualification includes simultaneous original-retail, native
and published-browser stock sessions in JK and MotS; see the recorded limits
in the qualification report.
