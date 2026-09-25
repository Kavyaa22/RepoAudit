#!/bin/sh
# Install Gitleaks + OSV-Scanner binaries for Railway / Docker.
# Not pip packages — they must be baked into the image.
set -eu

GITLEAKS_VERSION="${GITLEAKS_VERSION:-8.30.1}"
OSV_SCANNER_VERSION="${OSV_SCANNER_VERSION:-2.4.0}"

if [ -n "${REPOAUDIT_SECURITY_TOOLS_DIR:-}" ]; then
  DEST="$REPOAUDIT_SECURITY_TOOLS_DIR"
elif [ -w /usr/local/bin ] 2>/dev/null; then
  DEST="/usr/local/bin"
else
  DEST="${HOME}/.local/bin"
fi

mkdir -p "$DEST"

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64)
    GITLEAKS_ARCH="x64"
    OSV_ARCH="amd64"
    ;;
  aarch64|arm64)
    GITLEAKS_ARCH="arm64"
    OSV_ARCH="arm64"
    ;;
  *)
    echo "Unsupported architecture: $ARCH" >&2
    exit 1
    ;;
esac

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Installing gitleaks v${GITLEAKS_VERSION} (${GITLEAKS_ARCH}) -> ${DEST}"
curl -fsSL \
  "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_${GITLEAKS_ARCH}.tar.gz" \
  -o "$TMP/gitleaks.tar.gz"
tar -xzf "$TMP/gitleaks.tar.gz" -C "$TMP" gitleaks
cp "$TMP/gitleaks" "$DEST/gitleaks"
chmod 0755 "$DEST/gitleaks"

echo "Installing osv-scanner v${OSV_SCANNER_VERSION} (${OSV_ARCH}) -> ${DEST}"
curl -fsSL \
  "https://github.com/google/osv-scanner/releases/download/v${OSV_SCANNER_VERSION}/osv-scanner_linux_${OSV_ARCH}" \
  -o "$DEST/osv-scanner"
chmod 0755 "$DEST/osv-scanner"

"$DEST/gitleaks" version >/dev/null
"$DEST/osv-scanner" --version >/dev/null || "$DEST/osv-scanner" version >/dev/null || true

echo "Security tools installed in ${DEST}"
echo "Add ${DEST} to PATH (REPOAUDIT_SECURITY_TOOLS_DIR=${DEST})"
