#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$script_dir/../.." && pwd -P)"

usage() {
  printf 'Usage: %s [--host-only]\n' "$(basename "$0")" >&2
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

host_only=0
if [[ "${1:-}" == "--host-only" ]]; then
  host_only=1
elif [[ -n "${1:-}" ]]; then
  usage
  exit 64
fi

python3 "$script_dir/manifest.py" "$script_dir/SOURCE_MANIFEST.json" >/dev/null
bash -n "$script_dir/bootstrap.sh" "$script_dir/verify_source.sh" "$script_dir/revert.sh" "$script_dir/simulate.sh" "$script_dir/build.sh"
PYTHONPATH="$repo_root/ai_assistant/src" python3 -m unittest discover -s "$repo_root/ai_assistant/tests" -p 'test_*.py'
if [[ "${LRRK_BUILD_TEST:-0}" == "1" ]]; then
  python3 "$script_dir/tests/test_manifest.py"
else
  PYTHONPATH="$repo_root/ai_assistant/src" python3 -m unittest discover -s "$script_dir/tests" -p 'test_*.py'
fi
printf 'HOST_GATES=PASS\n'

if [[ "$host_only" == "1" ]]; then
  printf 'ESP_IDF_BUILD=SKIPPED host-only\n'
  exit 0
fi

if ! command -v idf.py >/dev/null 2>&1; then
  printf 'ESP_IDF_BUILD=UNAVAILABLE missing idf.py; no firmware claim made\n' >&2
  exit 20
fi
if [[ -z "${IDF_PATH:-}" ]]; then
  printf 'ESP_IDF_BUILD=UNAVAILABLE IDF_PATH is not set; no firmware claim made\n' >&2
  exit 20
fi

printf 'ESP_IDF_BUILD=BLOCKED target adapter is not yet a flashable ESP32-S3 project\n' >&2
exit 20
