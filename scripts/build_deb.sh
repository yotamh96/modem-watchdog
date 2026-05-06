#!/usr/bin/env bash
# Build a .deb on an aarch64 Linux host.
# Release build:    ./scripts/build_deb.sh release
# Dev build:        ./scripts/build_deb.sh             (default; uses git short-sha)
set -euo pipefail

cd "$(dirname "$0")/.."

MODE="${1:-dev}"
SHORT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

case "$MODE" in
  release)
    # The committed debian/changelog already has version 2.0.0-1 — no rewrite.
    VERSION_LINE_INFO="release version from committed debian/changelog"
    ;;
  dev|*)
    # B-04: dev builds visibly distinct from releases — 2.0.0-0.git<sha>-1
    DEV_VERSION="2.0.0-0.git${SHORT_SHA}-1"
    # Use dch to rewrite the top changelog entry without committing.
    # If dch is not present, fall back to sed.
    if command -v dch >/dev/null 2>&1; then
      DEBEMAIL="dev@draco.co.il" \
      DEBFULLNAME="spark-modem-watchdog devs" \
      dch --newversion "$DEV_VERSION" --distribution UNRELEASED --force-bad-version \
          "Dev build at git $SHORT_SHA" || true
    else
      # sed-based fallback: rewrite the version-and-rev tuple on the first changelog line.
      sed -i "1s/spark-modem-watchdog (2\.0\.0-1)/spark-modem-watchdog ($DEV_VERSION)/" debian/changelog
    fi
    VERSION_LINE_INFO="dev version $DEV_VERSION (rewritten in debian/changelog for this build only)"
    ;;
esac

echo "Building .deb ($VERSION_LINE_INFO)..."
echo "  Architecture: arm64"
echo "  Host arch:    $(uname -m)"
if [[ "$(uname -m)" != "aarch64" ]]; then
  echo "  WARNING: building on non-aarch64 host. The PBS tarball pinned in" >&2
  echo "  debian/python.sha256 is aarch64-only; the resulting .deb will not run" >&2
  echo "  outside aarch64 Linux. Use the QEMU fallback or a self-hosted runner." >&2
fi

mkdir -p dist/

# SOURCE_DATE_EPOCH already set inside debian/rules; export here too for any
# tool that reads it before dpkg-buildpackage spawns make.
export SOURCE_DATE_EPOCH="$(git log -1 --format=%ct 2>/dev/null || date -u +%s)"

# -us -uc: don't sign the .deb (no GPG key in CI; signing is post-build, future).
# -b: binary-only build (we have no upstream source tarball; format 3.0 native).
dpkg-buildpackage -us -uc -b

# dpkg-buildpackage drops artifacts in ../, not in dist/. Move them.
PARENT="$(dirname "$PWD")"
for ext in deb buildinfo changes; do
  for f in "$PARENT"/spark-modem-watchdog_*."$ext"; do
    [ -f "$f" ] || continue
    mv "$f" dist/
  done
done

DEB="$(ls dist/spark-modem-watchdog_*_arm64.deb 2>/dev/null | head -n1 || true)"
if [[ -z "$DEB" ]]; then
  echo "ERROR: build produced no .deb in dist/" >&2
  exit 1
fi

SIZE_BYTES="$(stat -c %s "$DEB" 2>/dev/null || stat -f %z "$DEB")"
SIZE_MIB=$((SIZE_BYTES / 1048576))

echo ""
echo "Build successful: $DEB"
echo "  Size: ${SIZE_MIB} MiB (NFR-51 ceiling: 40 MiB)"
if (( SIZE_MIB > 40 )); then
  echo "  ERROR: .deb exceeds NFR-51 size ceiling (40 MiB)." >&2
  exit 1
fi
