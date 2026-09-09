#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
manifest="$script_dir/SOURCE_MANIFEST.json"

usage() {
  printf 'Usage: %s WORKSPACE [NINJAPILOT_CHECKOUT]\n' "$(basename "$0")" >&2
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

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
mkdir -p "$workspace"

python3 - "$workspace" "$checkout" <<'PY'
from pathlib import Path
import sys
workspace = Path(sys.argv[1])
checkout = Path(sys.argv[2])
try:
    checkout.relative_to(workspace)
except ValueError:
    raise SystemExit("error: checkout must be inside the selected workspace")
PY

python3 "$script_dir/manifest.py" "$manifest" >/dev/null
flight_repo="$(python3 - "$manifest" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["sources"]["flight_tree"]["repository"])
PY
)"
flight_branch="$(python3 - "$manifest" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["sources"]["flight_tree"]["branch"])
PY
)"
flight_commit="$(python3 - "$manifest" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["sources"]["flight_tree"]["commit"])
PY
)"

marker="$workspace/.lrrk-litewing-patch-marker"
patch_cache="$workspace/.lrrk-litewing-patches"
mkdir -p "$patch_cache"

if [[ ! -e "$checkout" ]]; then
  git clone --depth 1 --branch "$flight_branch" "$flight_repo" "$checkout"
  git -C "$checkout" fetch --depth 1 origin "$flight_commit"
  git -C "$checkout" checkout --detach "$flight_commit"
elif ! git -C "$checkout" rev-parse --git-dir >/dev/null 2>&1; then
  printf 'error: checkout path exists but is not a Git repository: %s\n' "$checkout" >&2
  exit 2
fi

patch_files=()
patch_names=()
patch_hashes=()
while IFS=$'\t' read -r patch_name patch_source patch_apply patch_url patch_path expected_sha; do
  if [[ "$patch_source" == "repository" ]]; then
    candidate="$script_dir/../../$patch_path"
  else
    candidate="$patch_cache/$patch_name"
    if [[ ! -f "$candidate" ]] || [[ "$(shasum -a 256 "$candidate" | awk '{print $1}')" != "$expected_sha" ]]; then
      tmp="$candidate.tmp.$$"
      rm -f "$tmp"
      curl --fail --location --retry 2 --silent --show-error "$patch_url" -o "$tmp"
      actual_sha="$(shasum -a 256 "$tmp" | awk '{print $1}')"
      if [[ "$actual_sha" != "$expected_sha" ]]; then
        rm -f "$tmp"
        printf 'error: downloaded patch checksum mismatch for %s\n' "$patch_name" >&2
        exit 3
      fi
      mv "$tmp" "$candidate"
    fi
  fi
  if [[ ! -f "$candidate" ]]; then
    printf 'error: patch is missing: %s\n' "$candidate" >&2
    exit 4
  fi
  if [[ "$patch_apply" != "true" ]]; then
    continue
  fi
  patch_files+=("$candidate")
  patch_names+=("$patch_name")
  patch_hashes+=("$expected_sha")
done < <(python3 "$script_dir/manifest.py" "$manifest" --patches)

if [[ -f "$marker" ]]; then
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
  for ((index=${#patch_files[@]}-1; index>=0; index--)); do
    git -C "$checkout" apply --reverse --check "${patch_files[$index]}"
  done
  printf 'already bootstrapped: %s\n' "$checkout"
  exit 0
fi

"$script_dir/verify_source.sh" "$checkout" "$patch_cache" >/dev/null

applied=()
rollback() {
  result=$?
  for ((index=${#applied[@]}-1; index>=0; index--)); do
    git -C "$checkout" apply --reverse "${applied[$index]}" >/dev/null 2>&1 || true
  done
  exit "$result"
}
trap rollback ERR

for patch_file in "${patch_files[@]}"; do
  git -C "$checkout" apply --check "$patch_file"
  git -C "$checkout" apply "$patch_file"
  applied+=("$patch_file")
done
trap - ERR

umask 077
marker_tmp="$marker.tmp.$$"
{
  printf 'checkout=%s\n' "$checkout"
  printf 'source_commit=%s\n' "$flight_commit"
  for index in "${!patch_names[@]}"; do
    printf 'patch_%s=%s\n' "${patch_names[$index]}" "${patch_hashes[$index]}"
  done
} > "$marker_tmp"
mv "$marker_tmp" "$marker"

printf 'bootstrapped: %s\n' "$checkout"
printf 'source commit: %s\n' "$flight_commit"
printf 'patches applied: %s\n' "${#patch_files[@]}"
printf 'no device was flashed\n'
