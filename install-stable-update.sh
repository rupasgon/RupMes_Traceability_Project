#!/usr/bin/env bash
set -euo pipefail

# Run this script from the uploaded RupMES-Edge-Stable-Update directory.
PACKAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_SOURCE="$PACKAGE_DIR/rupmes_edge"
LIVE_ROOT="/opt/rupmes-edge/src"
LIVE_SOURCE="$LIVE_ROOT/rupmes_edge"
PYTHON="/opt/rupmes-edge/.venv/bin/python"
SERVICE="rupmes-edge"
STAGE_ROOT="$(mktemp -d /tmp/rupmes-edge-update.XXXXXX)"
BACKUP_ROOT="${LIVE_SOURCE}.backup-$(date +%Y%m%d-%H%M%S)"

cleanup() { rm -rf "$STAGE_ROOT"; }
trap cleanup EXIT

for file in app.py bmw_station_catalog.py config.py domain.py opcua.py runtime.py process_metrics.py store.py stoppages.py sync.py __init__.py static/index.html; do
  test -f "$PACKAGE_SOURCE/$file" || { echo "Falta $file en el paquete" >&2; exit 1; }
done

mkdir -p "$STAGE_ROOT/rupmes_edge/static"
cp "$PACKAGE_SOURCE"/*.py "$STAGE_ROOT/rupmes_edge/"
cp "$PACKAGE_SOURCE/static/index.html" "$STAGE_ROOT/rupmes_edge/static/"

# Metric polling opens its own OPC UA session.  Its Application URI must be
# the URI embedded in the existing client certificate or the PLC rejects it.
"$PYTHON" - "$STAGE_ROOT/rupmes_edge/opcua.py" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
source = path.read_text(encoding="utf-8")
marker = "class MetricPollCollector:"
if marker in source:
    head, tail = source.split(marker, 1)
    if "client.application_uri = self.endpoint.application_uri" not in tail:
        tail, changes = re.subn(
            r"(?m)^([ \t]*)client = Client\((.+)\)$",
            r"\1client = Client(\2)\n\1client.application_uri = self.endpoint.application_uri",
            tail,
            count=1,
        )
        if changes != 1:
            raise SystemExit("No se pudo configurar Application URI para el lector de métricas")
        path.write_text(head + marker + tail, encoding="utf-8")
PY

echo "Validando el paquete antes de tocar el servicio..."
PYTHONPATH="$STAGE_ROOT:$LIVE_ROOT" "$PYTHON" -m compileall -q "$STAGE_ROOT/rupmes_edge"
PYTHONPATH="$STAGE_ROOT:$LIVE_ROOT" "$PYTHON" -c 'from rupmes_edge.app import create_app; print("Importación validada")'

echo "Creando copia de seguridad: $BACKUP_ROOT"
sudo cp -a "$LIVE_SOURCE" "$BACKUP_ROOT"

echo "Aplicando archivos coherentes..."
for file in app.py bmw_station_catalog.py config.py domain.py opcua.py runtime.py process_metrics.py store.py stoppages.py sync.py __init__.py; do
  sudo install -m 0644 "$STAGE_ROOT/rupmes_edge/$file" "$LIVE_SOURCE/$file"
done
sudo install -m 0644 "$STAGE_ROOT/rupmes_edge/static/index.html" "$LIVE_SOURCE/static/index.html"

rollback() {
  echo "La comprobación no ha superado; restaurando automáticamente la copia de seguridad..." >&2
  sudo cp -a "$BACKUP_ROOT/." "$LIVE_SOURCE/"
  sudo systemctl restart "$SERVICE"
}

sudo systemctl restart "$SERVICE"
sleep 8
if ! curl --fail --silent --show-error http://127.0.0.1:8020/edge/api/snapshot >/dev/null; then
  rollback
  exit 1
fi

echo "Actualización aplicada y API comprobada correctamente."
echo "Copia de seguridad disponible en: $BACKUP_ROOT"
