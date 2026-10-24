# Running and reaching a server

The acceptance tests use private local networking. Public hosting and NAT traversal need a separate deployment check with the intended clients and provider. The software does not alter the host firewall or router.

## Endpoints

| Endpoint | Default | Purpose |
| --- | --- | --- |
| Control panel | `127.0.0.1:8765`, HTTP | Local administration |
| Native OpenJKDF2 | UDP `3500` | Existing GNS client transport |
| Browser | `127.0.0.1:8787`, HTTP/WebSocket | Unchanged client files, `/relay`, and `/health` |
| Browser WebRTC | Dynamically selected UDP sockets | Reliable ordered game channels negotiated through `/relay` |
| Engine IPC | `127.0.0.1:46000`, TCP | Private supervisor connection |
| DirectPlay broker | `127.0.0.1:46001`, TCP | Private retail-adapter connection |
| Original DirectPlay | Provider-controlled discovery and session sockets | Original retail clients; independent of the native GNS port |

Changing `native_port` changes GNS, not DirectPlay. Microsoft describes discovery on port 47624 and TCP/UDP session ports in the 2300–2400 range for its legacy DirectPlay protocol. The particular runtime/provider still needs verification: the isolated Wine qualification fixture also used dynamically assigned session sockets. Do not treat one forwarding rule as qualification of every provider. See Microsoft's primary [transport specification](https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-dpl4cs/e61a374b-be48-42a1-9fd4-c7a6efbd8b4b) and [host initialization specification](https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-dpl4cs/7cf81854-85ac-4d4e-9959-6c6ba7a1466c).

The optional game password preserves legacy client behavior. Compatibility requires the original session descriptor, so this field is not a reliable access-control boundary across all three transports. Restrict network reachability when a session needs private access. The control panel and internal adapter tokens are separate from this legacy game setting.

## Local and LAN use

Launch `python app.py`, open `http://127.0.0.1:8765`, enter the game-data paths, and start the session. The included engine and DirectPlay bridge paths are shown in the main README. The browser client is fetched separately with the hash-verifying fetcher.

For another computer on the LAN, set the browser listen address to `0.0.0.0`, then open `http://SERVER_ADDRESS:8787`. Native players use the ordinary native multiplayer connection UI and the configured GNS port. Retail players use their original TCP/IP DirectPlay UI and the server address. Every player needs matching content and the correct JK or MotS executable/mode.

The unchanged browser game has two profile steps: create/select a normal Players profile, then create a multiplayer character under Multiplayer → Multiplayer Characters. Match the server's force rank; the default is rank 0. Save that character before selecting Join Game. The existing browser directory picker needs actual game files available to the browser.

With `web_asset_downloads` enabled, that normal join flow can fetch the host's selected custom episode and active mod. Downloads share the existing `/relay` WebSocket connection or negotiated `jk-map` data channel; there is no separate file-server port or public filesystem endpoint to configure. The client verifies the reconstructed archive fingerprint before installation and uses its existing restart flow for a different mod. Retail and native clients still need their matching custom content installed normally.

Keep the host's custom files in its selected episode archive or configured mod directory. Original game content remains a client prerequisite. Download metadata still advertises the required content when the host disables transfers, allowing matching local/cache copies to be used.

## Remote administration

One way to reach the local administration panel from another machine is an SSH tunnel:

```sh
ssh -L 8765:127.0.0.1:8765 user@server
```

Open `http://127.0.0.1:8765` on the operator's machine. If the local browser-game link is also wanted through the tunnel, forward port 8787 separately; otherwise use the game's actual LAN/public URL. The control panel validates its host and port, so retain the matching local port or launch it with the intended `--port`.

## Public browser origin

Serve the browser gateway through an HTTPS reverse proxy using the same origin for the HTML/JS/WASM and `/relay`. Preserve WebSocket upgrades and the original Host header. If the proxy changes Host, put the exact public origin in `web_origins`. The asset handler already supplies the cross-origin isolation headers used by the published client.

Optional STUN/TURN settings can be entered in the panel's advanced JSON field or in `web_ice_servers`:

```json
[
  {
    "urls": ["turn:relay.example.com:3478?transport=udp"],
    "username": "your-turn-user",
    "credential": "your-turn-credential"
  }
]
```

Use the actual credentials and addresses for the chosen service. The default empty array contacts no external ICE service. The gateway passes configured ICE servers to the existing browser transport as well as its own WebRTC connection.

If WebRTC cannot establish a route, the original browser client can fall back to WebSocket. That path worked in the full-browser local game test, with the client's existing movement throttle. A fallback connection is not evidence that UDP/ICE works through a particular router. Check the `/health` transport metrics and real player behavior when qualifying a deployment.

## Multiple sessions

JK and MotS run as distinct sessions. Separate instances need separate configuration/state directories and distinct native, IPC, broker, browser, and administration ports. Original DirectPlay has additional provider-level socket/session behavior; simultaneous retail hosts on one machine have not been certified by this build. Start with one retail-enabled instance per tested runtime environment.
