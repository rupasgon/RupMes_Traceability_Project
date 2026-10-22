#!/usr/bin/env bash
# Applies the production dashboard update to an existing RupMES Edge install.
# It intentionally does not copy /etc/rupmes-edge or /var/lib/rupmes-edge:
# certificates, secrets, configuration and history remain untouched.
set -euo pipefail

PACKAGE_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
APP_ROOT="/opt/rupmes-edge"
APP_SOURCE="$APP_ROOT/src/rupmes_edge"
PYTHON="$APP_ROOT/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "Python environment not found: $PYTHON" >&2
  exit 1
fi

for file in app.py config.py domain.py opcua.py runtime.py store.py; do
  if [[ ! -f "$PACKAGE_DIR/rupmes_edge/$file" ]]; then
    echo "Missing update file: $PACKAGE_DIR/rupmes_edge/$file" >&2
    exit 1
  fi
done

if [[ ! -f "$PACKAGE_DIR/rupmes_edge/static/index.html" ]]; then
  echo "Missing dashboard file: $PACKAGE_DIR/rupmes_edge/static/index.html" >&2
  exit 1
fi

echo "Installing RupMES Edge production update..."
for file in app.py config.py domain.py opcua.py runtime.py store.py; do
  sudo install -o root -g root -m 0644 "$PACKAGE_DIR/rupmes_edge/$file" "$APP_SOURCE/$file"
done
sudo install -d -o root -g root -m 0755 "$APP_SOURCE/static"
sudo install -o root -g root -m 0644 "$PACKAGE_DIR/rupmes_edge/static/index.html" "$APP_SOURCE/static/index.html"

echo "Checking Python sources..."
PYTHONPATH="$APP_ROOT/src" "$PYTHON" -m compileall -q "$APP_SOURCE"

echo "Restarting service..."
sudo systemctl restart rupmes-edge
sudo systemctl is-active --quiet rupmes-edge

echo "Update installed successfully."
echo "Open the dashboard and force a browser refresh (Ctrl+F5)."
echo "For diagnostics: sudo journalctl -u rupmes-edge -n 100 --no-pager"
