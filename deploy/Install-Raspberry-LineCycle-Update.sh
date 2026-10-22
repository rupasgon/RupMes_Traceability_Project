#!/usr/bin/env bash
set -euo pipefail

PACKAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$PACKAGE_DIR/rupmes_edge"
APP_DIR="/opt/rupmes-edge/src/rupmes_edge"
PYTHON="/opt/rupmes-edge/.venv/bin/python"

for file in app.py config.py opcua.py runtime.py; do
  sudo install -m 0644 "$SOURCE_DIR/$file" "$APP_DIR/$file"
done
sudo install -m 0644 "$SOURCE_DIR/static/index.html" "$APP_DIR/static/index.html"

sudo "$PYTHON" -m compileall -q "$APP_DIR"
sudo systemctl restart rupmes-edge
sudo systemctl --no-pager --full status rupmes-edge
