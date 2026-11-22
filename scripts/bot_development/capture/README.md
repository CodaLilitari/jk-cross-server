# Recording and artifact helpers

These preserve the tools used for refinement trials 2–5. Duplicate, round-specific
copies are consolidated into parameterized commands. They use an ordinary installed
Chrome or Chromium and the project's custom JKWeb runtime. They do not build a
separate browser. Python 3.11+ is required; recording additionally needs the arena's
Python dependencies, `aiohttp`, Playwright, installed Chrome and hardware WebGL.
The live trial that established this workflow used Windows. The POSIX process
cleanup path is included but has not received a new live four-seat capture test.

## Record a trial

Use a clean, exact repository commit or a verified overlay with `deployed-build.json`.
All arguments are local paths. Put the work directory outside the source checkout.
Fetch the pinned relay using the existing `web_bots/fetch_relay.py` workflow.
The optional cosmetic GOB and retail game data are supplied by the caller.

```bash
python scripts/bot_development/capture/record_trial.py \
  --checkout /path/to/jk-cross-server --commit FULL_40_CHARACTER_COMMIT \
  --work-dir /path/to/private-trials --data /path/to/owned-jk \
  --chrome /path/to/chrome --relay-script /path/to/relay.py \
  --model-gob /path/to/optional-model.gob --label trial-6 --seconds 240
```

`--python` selects the arena's Python environment; the runner itself must also have
the recording dependencies. `--companion-chat` enables the arena's existing companion
chat option. It does not add strategy commands. `--mode`, `--warmup-seconds` and
`--timeout` control the same arena and launcher options. The capture is limited to
30–240 seconds. `launcher_adapter.py` checks exact source entry points before adding
headless mode, audible capture, 6,000 retained console entries, clock alignment and
the rendered saber material pair in memory. A changed launcher fails its guards;
the checkout is never rewritten by this adapter.

The run contains `review-result.json`, `own-state-traces.json`, the Chrome
qualification receipt and a `trial-traces.json.gz` envelope consumed by the analysis
helpers. The envelope's `directed_commands` is empty because this runner never sends
strategy overrides. Console entries use the launcher's token redaction. Credentials
stay in the arena's private run directory, and are not copied into the trace envelope.
Treat recordings, observations and chat logs as private until deliberately reviewed.

## Encode and verify the recording

```bash
python scripts/bot_development/capture/transcode_trial.py \
  --result /path/to/run/review-result.json --output /path/to/trial.mp4
```

Defaults preserve the recorded presentation: `dlil.3do`, the red saber pair and
`ff-guns`. Use `--expected-model`, `--expected-saber-side`, `--expected-saber-tip` and
`--mode` for an explicitly different trial. If a completed run has moved, supply
`--run-dir` and `--qualification`. FFmpeg comes from `--ffmpeg`, PATH, or the optional
`imageio-ffmpeg` package. The helper checks four seats, qualification, camera/model,
capture size, one audio track and duration. It writes a new 960×540, 30 fps H.264/AAC
MP4, fully decodes both streams, rejects effectively silent game audio and writes
a JSON receipt beside it. Existing outputs are never silently overwritten.

An existing output from this encoding profile can be decoded independently:

```bash
python scripts/bot_development/capture/transcode_trial.py \
  --inspect-only /path/to/trial.mp4 --seconds 240
```

The inspection profile assumes 30 fps video and 48 kHz stereo audio. It is not a
general media probe. Passing capture checks says nothing about sustained bot
movement, route quality, skill against humans or whether every weapon input hit.

## Hash-checked artifact transfer

`transfer_packets.py` replaces the separate video exporter, packet receiver and
checkpoint installer. It has no network endpoint. It can transfer an MP4, Git bundle
or an overlay through a transport that accepts bounded JSON. Every packet is at
most 1 MiB and records its offset, total size and SHA-256.

```bash
python scripts/bot_development/capture/transfer_packets.py pack artifact.bundle packets.jsonl
python scripts/bot_development/capture/transfer_packets.py unpack packets.jsonl recovered.bundle \
  --bytes EXPECTED_BYTES --sha256 EXPECTED_SHA256
```

The sender prints the complete size/hash manifest. Supply those independently to
the receiver. `unpack - ...` reads JSONL from stdin; `chunk` emits a single range.
Missing, reordered, changed or duplicate packets are rejected. Installation checks
the full digest and readback and refuses a conflicting existing destination.
These checks establish byte identity; use `git bundle verify` in the intended
repository to establish a bundle's Git prerequisites before fetching it.

## Verified runtime overlays

`install_overlay.py` preserves the eight-file diagnostic overlay workflow. It
requires the old deployment manifest, the complete gzip JSON payload, its size and
hash, and explicit old/new commit identities. Its fixed allowlist covers the browser
runtime, host, launcher, client and companion sources used in these trials.

```bash
python scripts/bot_development/capture/install_overlay.py \
  --base-checkout /path/to/old-overlay --target /path/to/new-overlay \
  --base-commit OLD_COMMIT --commit NEW_COMMIT \
  --payload overlay.json.gz --bytes EXPECTED_BYTES --sha256 EXPECTED_SHA256
```

It verifies the baseline and every incoming file before installing a new directory.
An overlay is a diagnostic runtime snapshot, not a complete Git checkout or a
substitute for the source patch and build receipts. A normal Git checkout is the
preferred route when it is available.
