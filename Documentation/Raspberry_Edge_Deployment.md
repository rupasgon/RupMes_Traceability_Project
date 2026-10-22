# RupMES Edge on Raspberry Pi

The RupMES Edge service runs as `itsys` and is managed by `systemd`.

```bash
sudo systemctl status rupmes-edge
sudo systemctl restart rupmes-edge
sudo journalctl -u rupmes-edge -n 100 --no-pager
```

The dashboard is published on the configured local-network address at
`http://<raspberry-wifi-ip>:8020/edge`.

## Administrator token

The dashboard configuration screen requires the administrator token. It is
stored locally, in a restricted root-readable environment file; it is not in
the SQLite database or `config.json`.

Show it from an SSH terminal on the Raspberry:

```bash
sudo sed -n 's/^RUPMES_EDGE_ADMIN_TOKEN=//p' /etc/rupmes-edge/environment
```

Treat the output as a secret. Do not paste it into tickets, screenshots, source
control, or chat. Use it only in the dashboard's **Administrator token** field.

### Troubleshoot an invalid-token error

If the dashboard rejects the value read from the environment file, first check
which environment-variable name the active SQLite configuration expects. This
prints only the variable name, never its value:

```bash
sudo python3 -c "import sqlite3,json; db=sqlite3.connect('/var/lib/rupmes-edge/rupmes-edge.db'); row=db.execute('SELECT payload FROM edge_configuration WHERE id=1').fetchone(); print(json.loads(row[0])['admin'].get('token_secret_ref') if row else 'No configuration found')"
```

The normal result is `RUPMES_EDGE_ADMIN_TOKEN`. If it is different, recover
that named variable from `/etc/rupmes-edge/environment`, or correct the active
configuration through an authorised Edge administrator. If the expected name
is `RUPMES_EDGE_ADMIN_TOKEN` and the value is still rejected, rotate the token
using the next procedure and restart the service.

Any token entered into a chat, ticket, screenshot, or other non-approved
channel must be treated as exposed and rotated immediately.

### Replace a lost or exposed token

Generate a replacement while preserving any other environment variables (for
example, the OPC UA password), then restart the service:

```bash
sudo python3 - <<'PY'
from pathlib import Path
import os
import secrets

path = Path("/etc/rupmes-edge/environment")
lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
token = secrets.token_urlsafe(32)
lines = [line for line in lines if not line.startswith("RUPMES_EDGE_ADMIN_TOKEN=")]
lines.append(f"RUPMES_EDGE_ADMIN_TOKEN={token}")
temporary = path.with_suffix(".tmp")
temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
os.chmod(temporary, 0o600)
os.replace(temporary, path)
print(token)
PY
sudo systemctl restart rupmes-edge
```

Copy the generated value from the console straight to the approved password
vault, then use it to access the dashboard. It is not saved anywhere else.

## Runtime locations

| Purpose | Path |
| --- | --- |
| Service | `/etc/systemd/system/rupmes-edge.service` |
| Bootstrap configuration | `/etc/rupmes-edge/config.json` |
| Protected secrets | `/etc/rupmes-edge/environment` |
| OPC UA certificates | `/etc/rupmes-edge/certificates/` |
| SQLite data and discovery reports | `/var/lib/rupmes-edge/` |
| Application source | `/opt/rupmes-edge/src/rupmes_edge/` |

After the first start, active line, endpoint, station, and NodeId settings are
stored in SQLite. Use the dashboard Configuration form to edit them, then
restart `rupmes-edge` to apply new OPC UA connections.
