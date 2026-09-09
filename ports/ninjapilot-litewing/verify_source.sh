#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
manifest="$script_dir/SOURCE_MANIFEST.json"

usage() {
  printf 'Usage: %s CHECKOUT [PATCH_CACHE]\n' "$(basename "$0")" >&2
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

checkout="${1:-}"
patch_cache="${2:-$(cd "$(dirname "$checkout")" && pwd -P)/.lrrk-litewing-patches}"
if [[ -z "$checkout" ]]; then
  usage
  exit 64
fi
if ! git -C "$checkout" rev-parse --git-dir >/dev/null 2>&1; then
  printf 'error: not a Git checkout: %s\n' "$checkout" >&2
  exit 2
fi

python3 "$script_dir/manifest.py" "$manifest" >/dev/null
expected_remote="$(python3 - "$manifest" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["sources"]["flight_tree"]["repository"])
PY
)"
expected_commit="$(python3 - "$manifest" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["sources"]["flight_tree"]["commit"])
PY
)"

actual_remote="$(git -C "$checkout" remote get-url origin 2>/dev/null || true)"
if [[ "$actual_remote" != *"MAVProxyUser/NinjaPilot-15.02.ninja"* ]]; then
  printf 'error: unexpected NinjaPilot remote: %s (expected %s)\n' "$actual_remote" "$expected_remote" >&2
  exit 3
fi

actual_commit="$(git -C "$checkout" rev-parse HEAD 2>/dev/null || true)"
if [[ "$actual_commit" != "$expected_commit" ]]; then
  printf 'error: source commit mismatch: %s (expected %s)\n' "$actual_commit" "$expected_commit" >&2
  exit 4
fi

if [[ -n "$(git -C "$checkout" status --porcelain)" && "${LRRK_ALLOW_DIRTY:-0}" != "1" ]]; then
  printf 'error: source checkout is dirty; refusing to validate or patch it\n' >&2
  exit 5
fi

while IFS= read -r required_path; do
  if [[ ! -e "$checkout/$required_path" ]]; then
    printf 'error: required source path is missing: %s\n' "$required_path" >&2
    exit 6
  fi
done < <(python3 - "$manifest" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    for path in json.load(handle)["sources"]["flight_tree"]["required_paths"]:
        print(path)
PY
)

while IFS=$'\t' read -r patch_name patch_source patch_apply patch_url patch_path expected_sha; do
  if [[ "$patch_source" == "repository" ]]; then
    candidate="$script_dir/../../$patch_path"
  else
    candidate="$patch_cache/$patch_name"
  fi
  if [[ ! -f "$candidate" ]]; then
    printf 'error: patch is missing: %s\n' "$candidate" >&2
    exit 7
  fi
  actual_sha="$(shasum -a 256 "$candidate" | awk '{print $1}')"
  if [[ "$actual_sha" != "$expected_sha" ]]; then
    printf 'error: patch checksum mismatch for %s: %s (expected %s)\n' "$patch_name" "$actual_sha" "$expected_sha" >&2
    exit 8
  fi
done < <(python3 "$script_dir/manifest.py" "$manifest" --patches)

printf 'source valid: %s\n' "$checkout"
printf 'commit: %s\n' "$actual_commit"
printf 'patches valid: %s\n' "$patch_cache"
