#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$script_dir/../.." && pwd -P)"
idf_project_dir="$script_dir/esp-idf"

usage() {
  printf 'Usage: %s [--host-only] [--flight-checkout PATH] [--reference-checkout PATH]\n' "$(basename "$0")" >&2
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

host_only=0
flight_checkout="${LRRK_NINJAPILOT_ROOT:-}"
reference_checkout="${LRRK_OPENPILOT_ESP32_ROOT:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --host-only)
      host_only=1
      shift
      ;;
    --flight-checkout)
      [[ $# -ge 2 ]] || { usage; exit 64; }
      flight_checkout="$2"
      shift 2
      ;;
    --reference-checkout)
      [[ $# -ge 2 ]] || { usage; exit 64; }
      reference_checkout="$2"
      shift 2
      ;;
    *)
      usage
      exit 64
      ;;
  esac
done

python3 "$script_dir/manifest.py" "$script_dir/SOURCE_MANIFEST.json" >/dev/null
bash -n "$script_dir/bootstrap.sh" "$script_dir/verify_source.sh" "$script_dir/revert.sh" "$script_dir/simulate.sh" "$script_dir/build.sh"
python3 "$script_dir/verify_external_sources.py" --help >/dev/null
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

if [[ -z "$flight_checkout" || -z "$reference_checkout" ]]; then
  printf 'ESP_IDF_BUILD=UNAVAILABLE external checkouts not supplied; no firmware claim made\n' >&2
  exit 20
fi

python3 "$script_dir/verify_external_sources.py" \
  --manifest "$script_dir/SOURCE_MANIFEST.json" \
  --flight "$flight_checkout" \
  --reference "$reference_checkout"

if [[ "${LRRK_BUILD_SIMULATION:-0}" == "1" ]]; then
  "$script_dir/simulate.sh" "$flight_checkout"
fi

if [[ -z "${IDF_PATH:-}" ]]; then
  local_idf_root="${LRRK_ESP_IDF_ROOT:-$repo_root/.toolchains/esp-idf-v5.3.2}"
  local_idf_tools="${IDF_TOOLS_PATH:-$repo_root/.toolchains/espressif}"
  if [[ -f "$local_idf_root/export.sh" ]]; then
    export IDF_TOOLS_PATH="$local_idf_tools"
    export PATH="/opt/homebrew/bin:${PATH:-}"
    # shellcheck disable=SC1090
    source "$local_idf_root/export.sh"
  fi
fi

if ! command -v idf.py >/dev/null 2>&1; then
  printf 'ESP_IDF_BUILD=UNAVAILABLE missing idf.py; no firmware claim made\n' >&2
  exit 20
fi
if [[ -z "${IDF_PATH:-}" ]]; then
  printf 'ESP_IDF_BUILD=UNAVAILABLE IDF_PATH is not set; no firmware claim made\n' >&2
  exit 20
fi
idf_version="$(idf.py --version 2>/dev/null || true)"
if [[ "$idf_version" != *"ESP-IDF v5.3.2"* ]]; then
  printf 'ESP_IDF_BUILD=UNAVAILABLE expected ESP-IDF v5.3.2, got %s; no firmware claim made\n' "$idf_version" >&2
  exit 20
fi

# ESP-IDF runs component requirement discovery in a child CMake process. Keep
# the pinned source boundary available in both the top-level configure and
# that child process; the CMake project still verifies the exact commits.
export NINJAPILOT_ROOT="$flight_checkout"
export OPENPILOT_ESP32_ROOT="$reference_checkout"

idf.py -C "$idf_project_dir" \
  -DIDF_TARGET=esp32s3 \
  -DNINJAPILOT_ROOT="$flight_checkout" \
  -DOPENPILOT_ESP32_ROOT="$reference_checkout" \
  build
printf 'ESP_IDF_BUILD=PASS target=esp32s3\n'
