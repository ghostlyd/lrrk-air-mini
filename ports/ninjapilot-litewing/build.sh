#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$script_dir/../.." && pwd -P)"

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

if ! command -v idf.py >/dev/null 2>&1; then
  printf 'ESP_IDF_BUILD=UNAVAILABLE missing idf.py; no firmware claim made\n' >&2
  exit 20
fi
if [[ -z "${IDF_PATH:-}" ]]; then
  printf 'ESP_IDF_BUILD=UNAVAILABLE IDF_PATH is not set; no firmware claim made\n' >&2
  exit 20
fi

idf.py -C "$script_dir/esp-idf" \
  -DIDF_TARGET=esp32s3 \
  -DNINJAPILOT_ROOT="$flight_checkout" \
  -DOPENPILOT_ESP32_ROOT="$reference_checkout" \
  build
printf 'ESP_IDF_BUILD=PASS target=esp32s3\n'
