# OPC UA discovery from RupMES Edge

Before configuring a production station, use the `discover` command from the
RupMES Edge device. It is read-only: it does not write values, invoke PLC
methods, or require a password.

```bash
/opt/rupmes-edge/.venv/bin/python -m rupmes_edge discover \
  opc.tcp://192.168.250.1:4840 \
  --output /var/lib/rupmes-edge/opcua-discovery.json
```

When the PLC accepts the Edge client certificate, use the active Edge
configuration for a secure browse. This loads the endpoint's certificates,
security policy, Application URI, and any configured read-only credentials from
the local device; it does not put secrets on the command line:

```bash
PYTHONPATH=/opt/rupmes-edge/src /opt/rupmes-edge/.venv/bin/python -m rupmes_edge discover \
  opc.tcp://192.168.250.1:4840 \
  --config /etc/rupmes-edge/config.json \
  --endpoint-id bmw-szl-plc \
  --output /var/lib/rupmes-edge/opcua-discovery-secure.json
```

The JSON report contains endpoint URLs, supported OPC UA security policies and
modes, the public server certificate and its SHA-256 fingerprint, available
anonymous user-token types, namespace URIs, and up to 500 browsed nodes.

## Interpret the result

- `browse.success: true`: use the exported paths and `node_id` values
  to map station signals in the Edge configuration.
- `browse.success: false`: endpoint discovery may still succeed, but the PLC
  blocks the selected client identity or browsing permission. Ask the PLC
  administrator for a read-only account and/or permission to browse or an
  exported NodeId list.
- Compare `server_certificate_sha256` with the value provided by the PLC
  administrator before trusting the server certificate.

The report never includes passwords or private keys. Credentials cannot be
discovered from an OPC UA server; keep `RUPMES_EDGE_OPCUA_PASSWORD` in the
device's restricted environment file and configure only its variable name in
the Edge UI.

For a broader address-space scan, increase the explicit limits only as needed:

```bash
/opt/rupmes-edge/.venv/bin/python -m rupmes_edge discover \
  opc.tcp://192.168.250.1:4840 --max-depth 5 --max-nodes 2000 \
  --output /var/lib/rupmes-edge/opcua-discovery-full.json
```

Do not run large scans repeatedly during production: browsing adds more load to
the PLC than the normal configured subscriptions.
