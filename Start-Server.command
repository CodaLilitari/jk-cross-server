#!/bin/sh
# Run from Terminal with --game-data '/exact/path/to/Jedi Knight'.
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec sh "$script_dir/start-server.sh" "$@"
