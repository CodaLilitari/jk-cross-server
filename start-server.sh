#!/bin/sh
# Docker launcher for macOS and Linux; native Linux setup is in docs/PLATFORMS.md.
set -eu

usage() {
    cat <<'EOF'
Usage: ./start-server.sh [start|stop|logs] [--game-data PATH] [--state-dir PATH]
Start requires the installed game-data directory (resource/ and episode/).
State defaults to $HOME/.jk-cross-server. JK_GAME_DATA and JK_STATE_DIR are
also accepted. Stop/logs target the existing jk-cross-server container.
Docker Desktop with Linux containers is required on macOS; Docker Engine
with Compose v2 is supported on Linux. No software or networking is installed.
For native Linux without Docker, follow docs/PLATFORMS.md.
EOF
}

fail() { printf '%s\n' "$*" >&2; exit 1; }
action=start
game_data=${JK_GAME_DATA:-}
state_dir=${JK_STATE_DIR:-}
while [ "$#" -gt 0 ]; do
    case "$1" in
        start|stop|logs) action=$1; shift ;;
        --game-data|--state-dir)
            option=$1
            [ "$#" -ge 2 ] || fail "Missing path after $option"
            case "$option" in
                --game-data) game_data=$2 ;;
                --state-dir) state_dir=$2 ;;
            esac
            shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) fail "Unknown argument: $1. Use --help for launch instructions." ;;
    esac
done

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
if [ "$action" = start ]; then
    [ -n "$game_data" ] || fail 'Supply --game-data with your installed game-data directory.'
    [ -d "$game_data" ] || fail 'The selected game-data path must be an existing directory.'
    JK_GAME_DATA=$(CDPATH= cd -- "$game_data" && pwd -P)
    if [ -z "$state_dir" ]; then
        [ -n "${HOME:-}" ] || fail 'Supply --state-dir: a user home directory could not be determined.'
        state_dir=$HOME/.jk-cross-server
    fi
    mkdir -p -- "$state_dir" || fail 'Cannot create the persistent state directory.'
    JK_STATE_DIR=$(CDPATH= cd -- "$state_dir" && pwd -P)
    probe=$(mktemp "$JK_STATE_DIR/.write-test.XXXXXX") || fail 'The persistent state directory must be writable.'
    rm -- "$probe"
    export JK_GAME_DATA JK_STATE_DIR
fi

command -v docker >/dev/null 2>&1 || fail 'Docker was not found. On macOS install/start Docker Desktop with Linux containers; on Linux install/start Docker Engine and Compose v2. This launcher does not install them.'
docker_os=$(docker info --format '{{.OSType}}') || fail 'Docker is not running. Start Docker Desktop (macOS) or Docker Engine (Linux), then retry.'
[ "$docker_os" = linux ] || fail 'Docker must use Linux containers; Windows containers are not supported.'
case "$action" in
    stop) exec docker stop jk-cross-server ;;
    logs) exec docker logs --tail 200 --follow jk-cross-server ;;
esac

docker compose version --short >/dev/null 2>&1 || fail 'Docker Compose v2 is required (docker compose).'
[ -f "$script_dir/packaging/compose.yaml" ] || fail 'packaging/compose.yaml is missing. Extract the complete release ZIP before starting.'
if [ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = arm64 ]; then
    printf '%s\n' 'Apple Silicon: this release uses linux/amd64 emulation. It is not a native ARM engine; performance and compatibility need host validation.' >&2
fi
docker compose --project-name jk-cross-server --project-directory "$script_dir" -f "$script_dir/packaging/compose.yaml" up --build -d
printf '%s\n' 'Container started. Open http://127.0.0.1:8765 and select a map to start the game.'
printf 'Persistent state: %s\n' "$JK_STATE_DIR"
