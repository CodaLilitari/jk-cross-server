# Cross-platform release implementation plan

Goal: publish the combined bots/spectator server as v0.4.0-dev on GitHub and GitLab, with native Linux and Linux-backed Windows/macOS downloads; update the existing portfolio.

Architecture: Ubuntu 24.04 linux/amd64 container reuses the packaged engines. Docker Compose launchers expose admin only on host loopback, native UDP 3500 and browser TCP 8787. Original data mounts read-only; /data persists settings/runtime. The image seeds a version-specific named /app volume so normal in-place updates are writable. Admin stays at loopback:8765 behind an internal proxy on 8766 preserving Host/Origin checks. Retail/Wine remains optional, with Docker networking qualification explicitly limited.

User choice: Linux-backed Windows/Mac packages approved in this conversation. Apple Silicon uses amd64 emulation, not a native ARM build. Do not install Docker Desktop or alter user networking; validate the container on a GitHub Ubuntu runner if local Docker is unavailable.

- [ ] Runtime: packaging/Dockerfile, packaging/container_runtime.py, packaging/compose.yaml, focused config/proxy/lifecycle tests. Preserve current admin/auth guard and avoid game assets in image.
- [ ] Launchers and archives: Start-Server.ps1, Start-Server.command, start-server.sh, scripts/build_platform_releases.py, focused launcher/archive tests, docs/PLATFORMS.md. All artifacts use the existing deterministic updater ZIP payload.
- [ ] Root integration: VERSION 0.4.0-dev, README/CHANGELOG links, release manifests, Ubuntu/Windows/macOS CI checks. Run actual container smoke on Ubuntu and native Python/browser regressions as needed.
- [ ] Publish both repository main refs and v0.4.0-dev release assets, then anonymously verify downloads.
- [ ] Update existing Sites project page with merged-main features, accurate platform labels, and verified download links; build and deploy latest source without overwriting parallel work.
