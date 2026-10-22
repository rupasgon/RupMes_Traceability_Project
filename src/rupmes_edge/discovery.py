"""Read-only OPC UA endpoint and address-space discovery for RupMES Edge."""

from __future__ import annotations

import asyncio
import base64
import hashlib
from datetime import datetime, timezone
from typing import Any


def _endpoint_summary(endpoint: Any) -> dict[str, Any]:
    """Return only the server metadata useful to configure a client."""
    certificate = bytes(endpoint.ServerCertificate or b"")
    return {
        "endpoint_url": endpoint.EndpointUrl,
        "security_policy_uri": endpoint.SecurityPolicyUri,
        "security_mode": getattr(endpoint.SecurityMode, "name", str(endpoint.SecurityMode)),
        "security_level": endpoint.SecurityLevel,
        "transport_profile_uri": endpoint.TransportProfileUri,
        "server_certificate_sha256": hashlib.sha256(certificate).hexdigest() if certificate else None,
        "server_certificate_der_base64": base64.b64encode(certificate).decode("ascii") if certificate else None,
        "user_token_types": [
            getattr(token.TokenType, "name", str(token.TokenType)) for token in endpoint.UserIdentityTokens
        ],
    }


async def discover_opcua(
    url: str,
    *,
    timeout_seconds: int = 10,
    max_depth: int = 3,
    max_nodes: int = 500,
    endpoint_config: Any | None = None,
) -> dict[str, Any]:
    """Discover an OPC UA server without writing to it.

    Endpoint discovery is attempted first.  Browsing is attempted with an
    anonymous, no-security session unless an Edge endpoint configuration is
    supplied.  With an endpoint configuration it uses the same read-only,
    secure client identity as the dashboard collector.
    """
    try:
        from asyncua import Client
    except ImportError as exc:  # pragma: no cover - depends on installation
        raise RuntimeError("OPC UA discovery requires the RupMES Edge dependencies") from exc

    report: dict[str, Any] = {
        "url": url,
        "discovered_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "endpoints": [],
        "browse": {
            "attempted": False,
            "success": False,
            "connection_profile": "secure_edge_configuration" if endpoint_config else "anonymous_no_security",
            "namespaces": [],
            "nodes": [],
        },
    }

    endpoint_client = Client(url=url, timeout=timeout_seconds)
    try:
        endpoints = await endpoint_client.connect_and_get_server_endpoints()
        report["endpoints"] = [_endpoint_summary(endpoint) for endpoint in endpoints]
    except Exception as exc:
        report["endpoint_discovery_error"] = str(exc)

    browse_client = Client(url=url, timeout=timeout_seconds)
    browse_result = report["browse"]
    browse_result["attempted"] = True
    node_count = 0

    async def configure_browse_client() -> None:
        if endpoint_config is None:
            return
        if endpoint_config.application_uri:
            browse_client.application_uri = endpoint_config.application_uri
        if endpoint_config.username:
            from rupmes_edge.config import secret_from_reference

            password = secret_from_reference(endpoint_config.password_secret_ref)
            browse_client.set_user(endpoint_config.username)
            browse_client.set_password(password.get_secret_value() if password else "")
        if endpoint_config.security.policy != "None":
            security = endpoint_config.security
            await browse_client.set_security_string(
                f"{security.policy},{security.mode},{security.client_certificate_path},{security.private_key_path},{security.server_certificate_path}"
            )

    async def browse(node: Any, path: list[str], depth: int) -> None:
        nonlocal node_count
        if depth > max_depth or node_count >= max_nodes:
            return
        try:
            children = await node.get_children()
        except Exception as exc:
            browse_result.setdefault("errors", []).append({"path": "/".join(path), "error": str(exc)})
            return
        for child in children:
            if node_count >= max_nodes:
                return
            try:
                browse_name = await child.read_browse_name()
                node_class = await child.read_node_class()
                name = f"{browse_name.NamespaceIndex}:{browse_name.Name}"
                entry = {
                    "node_id": child.nodeid.to_string(),
                    "browse_name": name,
                    "path": "/".join([*path, name]),
                    "node_class": getattr(node_class, "name", str(node_class)),
                }
                browse_result["nodes"].append(entry)
                node_count += 1
                # Objects and variables may contain useful production tags.
                if depth < max_depth:
                    await browse(child, [*path, name], depth + 1)
            except Exception as exc:
                browse_result.setdefault("errors", []).append(
                    {"path": "/".join(path), "node_id": child.nodeid.to_string(), "error": str(exc)}
                )

    try:
        await configure_browse_client()
        await browse_client.connect()
        browse_result["namespaces"] = await browse_client.get_namespace_array()
        await browse(browse_client.nodes.objects, ["Objects"], 1)
        browse_result["success"] = True
    except Exception as exc:
        browse_result["error"] = str(exc)
    finally:
        try:
            await browse_client.disconnect()
        except Exception:
            pass

    browse_result["truncated"] = node_count >= max_nodes
    browse_result["max_depth"] = max_depth
    browse_result["max_nodes"] = max_nodes
    return report


def run_discovery(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Synchronous helper used by the CLI and useful for external callers."""
    return asyncio.run(discover_opcua(*args, **kwargs))
