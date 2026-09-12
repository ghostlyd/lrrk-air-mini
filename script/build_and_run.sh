#!/bin/zsh
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
package_dir="$repo_root/micro_controller"
build_dir="$package_dir/.build/arm64-apple-macosx/debug"
dist_dir="$package_dir/dist"
app_dir="$dist_dir/LoudPilot.app"
install_dir="/Applications/LoudPilot.app"
binary="$build_dir/LoudPilot"
bundle_identifier="ai.lrrk.loudpilot"
stable_adhoc_requirement="designated => identifier \"$bundle_identifier\""

mode="${1:-run}"
case "$mode" in
    run|--debug|--logs|--telemetry|--verify|--install)
        ;;
    *)
        print -u2 "usage: $0 [run|--debug|--logs|--telemetry|--verify|--install]"
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

signing_identity="${LOUDPILOT_SIGNING_IDENTITY:-}"
if [[ -z "$signing_identity" ]]; then
    signing_identity="$(/usr/bin/security find-identity -v -p codesigning 2>/dev/null \
        | /usr/bin/awk -F'\"' '/Apple Development:|Developer ID Application:/ {print $2; exit}')"
fi

if [[ -n "$signing_identity" ]]; then
    print "signing: $signing_identity"
    /usr/bin/codesign --force --deep --sign "$signing_identity" "$app_dir" >/dev/null
else
    # Keep the designated requirement stable on developer machines without an
    # Apple signing identity. The previous bare `--sign -` fallback used a
    # cdhash, so every rebuilt binary looked like a new Bluetooth client to
    # macOS privacy services and triggered the permission prompt again.
    print "signing: stable local ad-hoc requirement ($bundle_identifier)"
    /usr/bin/codesign --force --deep --sign - \
        --identifier "$bundle_identifier" \
        -r="$stable_adhoc_requirement" \
        "$app_dir" >/dev/null
fi

launch_app="$app_dir"
if [[ "$mode" == "--install" ]]; then
    if [[ -e "$install_dir" ]]; then
        rm -rf "$install_dir"
    fi
    /usr/bin/ditto "$app_dir" "$install_dir"
    launch_app="$install_dir"
    print "installed: $install_dir"
fi

if [[ "$mode" == "--verify" ]]; then
    /usr/bin/plutil -lint "$app_dir/Contents/Info.plist"
    /usr/bin/codesign --verify --deep --strict "$app_dir"
    /usr/bin/file "$app_dir/Contents/MacOS/LoudPilot"
    pkill -x LoudPilot 2>/dev/null || true
    /usr/bin/open -n "$app_dir"
    sleep 1
    pgrep -x LoudPilot >/dev/null
    print "verified: $app_dir"
    exit 0
fi

pkill -x LoudPilot 2>/dev/null || true
/usr/bin/open -n "$launch_app"
print "launched: $launch_app"
print "mode: $mode (control-plane encoder available; launch does not enable output)"
