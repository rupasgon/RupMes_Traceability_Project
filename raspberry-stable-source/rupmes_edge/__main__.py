from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="RupMES Edge local dashboard")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("simulator", help="Run the local OPC UA simulator")
    dashboard = subcommands.add_parser("dashboard", help="Run the local dashboard")
    dashboard.add_argument("--config", help="Path to a validated edge JSON configuration")
    dashboard.add_argument("--host", help="Override the configuration bind host")
    dashboard.add_argument("--port", type=int, help="Override the configuration port")
    discover = subcommands.add_parser("discover", help="Read-only OPC UA endpoint and NodeId discovery")
    discover.add_argument("url", help="OPC UA URL, for example opc.tcp://192.168.250.1:4840")
    discover.add_argument("--output", default="opcua-discovery.json", help="JSON report path")
    discover.add_argument("--timeout", type=int, default=10, help="Connection timeout in seconds")
    discover.add_argument("--max-depth", type=int, default=3, help="Maximum address-space depth to browse")
    discover.add_argument("--max-nodes", type=int, default=500, help="Maximum nodes to include in the report")
    discover.add_argument("--config", help="Edge bootstrap configuration; uses its active SQLite endpoint configuration")
    discover.add_argument("--endpoint-id", help="Configured endpoint identifier to use for secure discovery")
    arguments = parser.parse_args()

    if arguments.command == "simulator":
        from rupmes_edge.simulator import run_simulator

        asyncio.run(run_simulator())
        return

    if arguments.command == "discover":
        from rupmes_edge.discovery import run_discovery

        if arguments.timeout < 1 or arguments.max_depth < 1 or arguments.max_nodes < 1:
            parser.error("discovery timeout, max-depth and max-nodes must be greater than zero")
        endpoint = None
        if arguments.config:
            from rupmes_edge.config import EdgeConfig, load_config
            from rupmes_edge.store import EdgeStore

            bootstrap_config = load_config(arguments.config)
            store = EdgeStore(bootstrap_config.storage.database_path)
            try:
                saved = store.load_configuration()
            finally:
                store.close()
            active_config = EdgeConfig.model_validate_json(saved) if saved else bootstrap_config
            endpoint_id = arguments.endpoint_id
            endpoint = next(
                (
                    item
                    for item in active_config.endpoints
                    if item.endpoint_id == endpoint_id or (endpoint_id is None and item.url == arguments.url)
                ),
                None,
            )
            if endpoint is None:
                parser.error("No configured endpoint matches this URL; specify --endpoint-id")
        report = run_discovery(
            arguments.url,
            timeout_seconds=arguments.timeout,
            max_depth=arguments.max_depth,
            max_nodes=arguments.max_nodes,
            endpoint_config=endpoint,
        )
        output = Path(arguments.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"OPC UA discovery report written to {output}")
        if report.get("endpoint_discovery_error"):
            print(f"Endpoint discovery failed: {report['endpoint_discovery_error']}")
        elif report["browse"].get("success"):
            print(f"Browsing succeeded: {len(report['browse']['nodes'])} nodes found.")
        else:
            print("Endpoint discovery succeeded; browsing was not permitted.")
        return

    from rupmes_edge.app import create_app
    from rupmes_edge.config import default_config_path, demo_config, load_config
    import uvicorn

    configured_path = default_config_path()
    use_external_config = bool(arguments.config or os.getenv("RUPMES_EDGE_CONFIG") or configured_path.exists())
    config_path = arguments.config or configured_path
    config = load_config(config_path) if use_external_config else demo_config()
    uvicorn.run(create_app(config, config_path if use_external_config else None), host=arguments.host or config.admin.bind_host, port=arguments.port or config.admin.port, reload=False)


if __name__ == "__main__":
    main()
