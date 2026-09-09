#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
manifest="$script_dir/SOURCE_MANIFEST.json"

usage() {
  printf 'Usage: %s WORKSPACE [NINJAPILOT_CHECKOUT]\n' "$(basename "$0")" >&2
}

workspace_arg="${1:-}"
if [[ -z "$workspace_arg" ]]; then
  usage
  exit 64
fi
workspace="$(python3 - "$workspace_arg" <<'PY'
from pathlib import Path
import sys
print(Path(sys.argv[1]).expanduser().resolve())
PY
)"
checkout_arg="${2:-$workspace/NinjaPilot}"
checkout="$(python3 - "$checkout_arg" <<'PY'
from pathlib import Path
import sys
print(Path(sys.argv[1]).expanduser().resolve())
PY
)"
marker="$workspace/.lrrk-litewing-patch-marker"
patch_cache="$workspace/.lrrk-litewing-patches"

if [[ ! -f "$marker" ]]; then
  printf 'error: patch marker is absent; refusing to guess which changes to remove\n' >&2
  exit 2
fi
if ! git -C "$checkout" rev-parse --git-dir >/dev/null 2>&1; then
  printf 'error: not a Git checkout: %s\n' "$checkout" >&2
  exit 3
fi

python3 "$script_dir/manifest.py" "$manifest" >/dev/null
flight_commit="$(python3 - "$manifest" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["sources"]["flight_tree"]["commit"])
PY
)"
python3 - "$marker" "$checkout" "$flight_commit" <<'PY'
from pathlib import Path
import sys
values = {}
for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if "=" in line:
        key, value = line.split("=", 1)
        values[key] = value
if values.get("checkout") != sys.argv[2] or values.get("source_commit") != sys.argv[3]:
    raise SystemExit("error: patch marker does not match requested checkout or source revision")
PY

LRRK_ALLOW_DIRTY=1 "$script_dir/verify_source.sh" "$checkout" "$patch_cache" >/dev/null

patch_files=()
while IFS=$'\t' read -r patch_name patch_source patch_apply patch_url patch_path expected_sha; do
  [[ "$patch_apply" == "true" ]] || continue
  if [[ "$patch_source" == "repository" ]]; then
    candidate="$script_dir/../../$patch_path"
  else
    candidate="$patch_cache/$patch_name"
  fi
  if [[ ! -f "$candidate" ]]; then
    printf 'error: patch required for safe revert is missing: %s\n' "$candidate" >&2
    exit 4
  fi
  patch_files+=("$candidate")
done < <(python3 "$script_dir/manifest.py" "$manifest" --patches)

for ((index=${#patch_files[@]}-1; index>=0; index--)); do
  git -C "$checkout" apply --reverse --check "${patch_files[$index]}"
done
for ((index=${#patch_files[@]}-1; index>=0; index--)); do
  git -C "$checkout" apply --reverse "${patch_files[$index]}"
done
rm -f "$marker"

printf 'reverted LiteWing patches: %s\n' "$checkout"
printf 'source checkout remains unflashed\n'
