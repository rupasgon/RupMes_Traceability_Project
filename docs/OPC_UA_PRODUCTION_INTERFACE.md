# Production interface: BMW SZL Levers

The dashboard reads the published `OPC_UA` interface from the PLC with a
read-only, secured OPC UA session.  The collector uses periodic reads at the
endpoint's configured interval (500 ms by default).  This avoids OPC UA
servers that return the initial subscription values but later reject
`PublishRequest` with `BadNoSubscription`.

## Line counters

When station NodeIds use the `ns=4;s=OPC_UA.STxx.*` convention, the following
BMW counters are detected automatically as a backwards-compatible adapter:

| Dashboard value | PLC NodeId |
| --- | --- |
| Total / OK / NOK | `OPC_UA.Contador_Total.QTY`, `.QTY_OK`, `.QTY_NOK` |
| WI / OK / NOK | `OPC_UA.Contador_WI.QTY`, `.QTY_OK`, `.QTY_NOK` |
| DI / OK / NOK | `OPC_UA.Contador_DI.QTY`, `.QTY_OK`, `.QTY_NOK` |

The application never writes to the PLC.

For every new line, configure `production_counters` on its OPC UA endpoint.
The list can contain any number of counters and each counter may expose only a
quantity, or a quantity plus OK/NOK values:

```json
"production_counters": [
  {
    "counter_id": "finished",
    "name": "Finished units",
    "quantity_node": "ns=4;s=Line.Finished.Quantity",
    "ok_node": "ns=4;s=Line.Finished.OK",
    "nok_node": "ns=4;s=Line.Finished.NOK"
  },
  {
    "counter_id": "rework",
    "name": "Rework",
    "quantity_node": "ns=4;s=Line.Rework.Quantity"
  }
]
```

The dashboard creates its header cards from this list; it does not assume a
fixed number or name of counters.

## Station signals

Each station uses `Running`, `CycleActive`, `CycleComplete`,
`CycleTime_Estacion`, `PartsCounter_NOK`, `FaultActive` and `AutoMode` from
the corresponding `OPC_UA.STxx` structure.  `PartsCounter_NOK` is deliberately
shown as an NOK counter; it is not the production quantity.

The daily station view records state transitions, cycle completions and NOK
counter changes.  It derives a production stop when the station is automatic
and reports `IDLE`, `STOPPED` or `FAULT`; manual mode is not counted as a
production stop.  Faults are shown as *Fault active* until the PLC alarm-bit
descriptions are mapped to the individual `OPC_UA_Alarm_*` arrays.

## SQLite safety

Only the OPC UA collector persists events.  Dashboard HTTP requests are
read-only.  SQLite access is serialised and uses WAL mode, allowing multiple
users to open or refresh the dashboard without creating duplicate state events
or sharing the connection unsafely.
