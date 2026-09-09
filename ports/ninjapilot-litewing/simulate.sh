#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
checkout="${1:-}"
if [[ "$checkout" == "--help" || "$checkout" == "-h" || -z "$checkout" ]]; then
  printf 'Usage: %s NINJAPILOT_CHECKOUT\n' "$(basename "$0")" >&2
  [[ -n "$checkout" ]] && exit 0 || exit 64
fi
if ! git -C "$checkout" rev-parse --git-dir >/dev/null 2>&1; then
  printf 'SIMULATION=BLOCKED not a Git checkout: %s\n' "$checkout" >&2
  exit 2
fi

LRRK_ALLOW_DIRTY=1 "$script_dir/verify_source.sh" "$checkout" >/dev/null
if ! command -v qmake >/dev/null 2>&1; then
  printf 'SIMULATION=UNAVAILABLE missing qmake/Qt; no hardware claim made\n' >&2
  exit 20
fi

if ! make -C "$checkout" fw_simlitewing; then
  printf 'SIMULATION=FAILED host POSIX build failed\n' >&2
  exit 21
fi
printf 'SIMULATION=PASS fw_simlitewing\n'
