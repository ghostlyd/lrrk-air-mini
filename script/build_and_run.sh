#!/bin/zsh
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
package_dir="$repo_root/micro_controller"
build_dir="$package_dir/.build/arm64-apple-macosx/debug"
dist_dir="$package_dir/dist"
app_dir="$dist_dir/LoudPilot.app"
binary="$build_dir/LoudPilot"

mode="${1:-run}"
case "$mode" in
    run|--debug|--logs|--telemetry|--verify)
        ;;
    *)
        print -u2 "usage: $0 [run|--debug|--logs|--telemetry|--verify]"
        exit 2
        ;;
esac

cd "$repo_root"
swift build --package-path "$package_dir" --product LoudPilot

rm -rf "$app_dir"
mkdir -p "$app_dir/Contents/MacOS" "$app_dir/Contents/Resources"
cp "$binary" "$app_dir/Contents/MacOS/LoudPilot"
cp "$package_dir/Resources/Info.plist" "$app_dir/Contents/Info.plist"
chmod 755 "$app_dir/Contents/MacOS/LoudPilot"

/usr/bin/codesign --force --deep --sign - "$app_dir" >/dev/null

if [[ "$mode" == "--verify" ]]; then
    /usr/bin/plutil -lint "$app_dir/Contents/Info.plist"
    /usr/bin/codesign --verify --deep --strict "$app_dir"
    /usr/bin/file "$app_dir/Contents/MacOS/LoudPilot"
    pkill -x LoudPilot 2>/dev/null || true
    pkill -x LiteWingMicroController 2>/dev/null || true
    pkill -f "$dist_dir/LiteWingMicroController.app/Contents/MacOS/LiteWingMicroController" 2>/dev/null || true
    /usr/bin/open -n "$app_dir"
    sleep 1
    pgrep -x LoudPilot >/dev/null
    print "verified: $app_dir"
    exit 0
fi

pkill -x LoudPilot 2>/dev/null || true
pkill -x LiteWingMicroController 2>/dev/null || true
pkill -f "$dist_dir/LiteWingMicroController.app/Contents/MacOS/LiteWingMicroController" 2>/dev/null || true
/usr/bin/open -n "$app_dir"
print "launched: $app_dir"
print "mode: $mode (UI remains read-only; no mode enables flight commands)"
