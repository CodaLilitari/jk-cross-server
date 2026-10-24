#!/usr/bin/env bash
set -euo pipefail
native_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd "$native_dir/.." && pwd)"
build_root="${1:-$project_dir/.build-native}"
base=74e4657c4f1751d09af9ad9e056acb8f41997acb
source_dir="$build_root/source"
if [[ ! -d "$source_dir/.git" ]]; then
  if [[ -e "$source_dir" ]]; then
    printf '%s\n' 'Refusing to replace an existing non-git source directory.' >&2
    exit 1
  fi
  mkdir -p "$build_root"
  git clone https://gitlab.com/codalilitari/OpenJKDF2-MotS-Fixes.git "$source_dir"
  git -C "$source_dir" checkout --detach "$base"
fi
[[ "$(git -C "$source_dir" rev-parse HEAD)" == "$base" ]] || {
  printf '%s\n' 'The source checkout does not match the pinned base.' >&2
  exit 1
}
git -C "$source_dir" submodule update --init lib/zlib lib/libpng lib/glew lib/freeglut lib/physfs lib/GameNetworkingSockets lib/protobuf lib/SDL lib/SDL_mixer
git -C "$source_dir/lib/SDL_mixer" submodule update --init external/ogg external/vorbis external/opus external/opusfile
if ! git -C "$source_dir" apply --reverse --check "$native_dir/crossplay-dedicated.patch" 2>/dev/null; then
  git -C "$source_dir" apply --check "$native_dir/crossplay-dedicated.patch"
  git -C "$source_dir" apply "$native_dir/crossplay-dedicated.patch"
fi
build_dir="$build_root/build"
cmake -S "$source_dir" -B "$build_dir" -DCMAKE_BUILD_TYPE=Release
python3 -m venv "$build_dir/cogapp_venv"
"$build_dir/cogapp_venv/bin/python" -m pip install 'cogapp==3.6.0'
cmake --build "$build_dir" -j4
python3 "$native_dir/package_native.py" "$source_dir" "$build_dir"
printf 'Native server installed under %s/bin/linux-x86_64\n' "$project_dir"
