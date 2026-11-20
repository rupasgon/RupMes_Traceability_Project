# Configuración de ciclo total de línea

El ciclo de línea es opcional e independiente de los ciclos de cada estación. Se usa
cuando el PLC publica un valor confirmado que representa una pieza completa.

```json
{
  "line_cycle": {
    "endpoint_id": "bmw-szl-plc",
    "cycle_time_node": "ns=4;s=OPC_UA.ST01.CycleTime_Total",
    "cycle_complete_node": "ns=4;s=OPC_UA.ST01.CycleComplete",
    "target_cycle_seconds": 10.0
  }
}
```

Selecciona los dos NodeId que confirme el responsable del PLC. El colector registra un
ciclo únicamente en el flanco ascendente de `cycle_complete_node`; un tiempo retenido
por OPC UA no se cuenta varias veces. El panel muestra tiempo actual, objetivo,
desviación, promedio de la sesión y ciclos por encima del objetivo.
