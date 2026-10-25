# GitLab release updates

JK Cross Server 0.3.0-dev introduces updates for the installed server package.
It uses the public releases of **codalilitari/jk-cross-server** on GitLab. It
does not require a GitLab login, access token, Git client, or client engine patch.

## Using the control panel

Open **Server updates** in the local browser panel.

- **Check automatically every 6 hours** is enabled by default. The Python
  control panel checks on startup and then every six hours while it is running.
  Closing the browser tab does not stop these checks.
- **Check now** checks immediately. A check can run during a match and does not
  interrupt it. Network failures leave the installed server usable.
- **Install update** downloads, verifies, and installs a newer packaged release.
  Stop the game session first.
- **Install automatically when the server is stopped** is disabled by default.
  Enable it to install new releases without another button press. It never
  stops an active match. If another panel is hosting from the same installation,
  installation waits and retries after that session stops.
- The panel restarts after installation. The browser reconnects with the new
  panel token. The game stays stopped, even if the original command used
  `--start`; start the next session when ready.

Checks include published development releases such as `0.3.0-dev`. Version
selection follows semantic version precedence, skips future releases, and
examines up to the 300 most recently dated release records. A new commit on
`main` alone does not trigger installation: the publisher must provide the
versioned release ZIP and its checksum asset.

Preferences are saved separately in `update-settings.json` inside the selected
state directory (normally `runtime`). The updater always targets this project's
public GitLab endpoint. No account credentials are read or transmitted.

## Upgrading an existing 0.2 installation

Version 0.2 did not contain an updater or a release manifest. **Install 0.3
manually once**; subsequent compatible packaged releases can use the updater.

1. Stop every session and control-panel process using the installation.
2. Keep a backup of that installation.
3. Extract the new ZIP into a temporary directory, then copy its
   `jk-cross-server/` contents into the existing installation, replacing the
   included application files. Preserve executable permissions when copying.
   The ZIP does not contain your `config/`, `runtime/`, virtual environment,
   game data, mods, downloaded browser client, or Wine prefix.
4. Run `python app.py` with the same arguments as before. Check **Server updates**.

The 0.3 update introduces no new Python dependencies. Keeping the same install
directory also keeps existing absolute engine and bridge paths valid. If you
choose a different directory, update those paths in the panel before starting.

For a Git checkout, pull and review changes through Git. The panel can check
releases but deliberately disables in-place installation in a checkout,
including Git worktrees, so local changes and repository history are preserved.

## What an installation preserves

The installer replaces only files listed in the release manifests. It preserves
unmanaged files, the selected configuration and state directories, game data,
the mod directory, browser downloads, and the Wine prefix. It also removes
obsolete files that belonged to the previous package.

If a managed application file has local edits, a new file would collide with
local content, or a release path overlaps configured data, installation stops
with an explanation. Preserve the edits and upgrade manually in that case.
The installer also declines releases that change the Python dependency lists;
install those releases and their pinned dependencies manually. It does not run
`pip`, a downloaded installer script, or shell commands.

Every active game session holds a lock for its installation directory. Updating
takes an exclusive lock, so multiple panel instances cannot overwrite files
under each other's matches. A panel whose files were updated by another panel
must restart before it can start another session.

## Verification, backup, and recovery

The updater accepts HTTPS URLs belonging to this GitLab project and checks each
redirect. It verifies the ZIP's SHA-256 sidecar, the package manifest, the
individual file hashes, the packaged version, and Python syntax compatibility
before installing. It rejects unexpected archive entries and symbolic links.
Downloads and unpacking have size and time limits.

These hashes verify the contents distributed by the project over HTTPS; they
are not a separate publisher signature. Publishing access to this GitLab
project remains the authority for which releases are offered.

Installation records a transaction and saves the previous package. If a write
fails during installation, it restores the previous files. If the process is
interrupted, the next `python app.py` launch recovers before loading the normal
server implementation and reloads the restored launcher when necessary.

The most recent backup is kept at `.jk-update/last-backup/backup/` in the
installation directory, with a receipt at `.jk-update/last-receipt.json`.
Only one completed backup is retained. An incomplete recovery stops startup
and reports the problem so it cannot silently run a mixed installation.

## Publishing the next update

The source includes a deterministic packaging script. Change `VERSION` and the
release notes, run the relevant tests, and stage the intended distributable
source files in Git before generating metadata. The script uses the tracked
file list and executable modes together with the current worktree bytes.

```bash
python scripts/build_release.py --refresh-manifest
python scripts/build_release.py --check
python scripts/build_release.py --output-dir ../releases
```

Commit the generated `release-manifest.json` and `SHA256SUMS` with the source
changes. Tag that commit `v<VERSION>` and publish a GitLab release with the two
generated files as release assets:

- `JK_Cross_Server_<VERSION>.zip`
- `JK_Cross_Server_<VERSION>.zip.sha256`

Use this project's GitLab Generic Package Registry for the assets, with project
release download links pointing to them. The automatically generated GitLab
source archives are not the installable package. The packager excludes local
state and game archives, rejects symlinks and ambiguous paths, and refuses a
build if the manifest no longer matches the files.

See `docs/QUALIFICATION.md` and `qa/update-tests.json` for the updater checks and
the separate, retained game-compatibility results.
