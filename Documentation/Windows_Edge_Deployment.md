# RupMES Edge on Windows

## Install on a new PC

On the development PC, generate the installation ZIP:

```powershell
.\scripts\Build-EdgeWindowsPackage.ps1
```

Copy `dist\RupMES-Edge-Windows.zip` to the destination PC, extract it, and run `INSTALL_EDGE_WINDOWS.cmd` with **Run as administrator**.

The installer creates the Python environment, preserves an existing bootstrap configuration, registers the `RupMES Edge Dashboard` scheduled task, and starts it on demand. The PC needs access to the configured Python package repository when the ZIP was built without its offline dependency bundle.

During a first installation, the installer creates a secure administrator token if the configured machine variable does not exist. It prints the token once in the administrator console. Store it in the approved password vault before closing that console.

## Local files and data

RupMES Edge keeps local runtime material under `C:\ProgramData\RupMES Edge\`:

- `config.json`: **bootstrap only**. It provides the SQLite path, local bind address/port, administration-token variable name, and the initial configuration used when the database is empty.
- `certificates\`: OPC UA client certificate, private key, and trusted PLC certificate.
- `data\rupmes-edge.db`: SQLite database containing historical cycles, counters, station states, and the active operational configuration.

These paths are outside the repository and must not be copied to Git.

## Configuration source of truth

After its first start, Edge imports the initial line, station, endpoint, and NodeId settings from `config.json` into SQLite. From that moment, the SQLite configuration is the source of truth.

Do not edit `config.json` to change line settings, stations, endpoints, targets, or NodeIds. Use the dashboard instead:

1. Open `http://127.0.0.1:8020/edge`.
2. Select **Configuration**.
3. Enter the Edge administrator token.
4. Select **Load configuration**.
5. Edit the line, OPC UA endpoints, stations, targets, output station flag, or NodeIds.
6. Select **Save configuration**.
7. Restart the scheduled task to apply new OPC UA connections:

```powershell
Stop-ScheduledTask -TaskName "RupMES Edge Dashboard"
Start-Sleep -Seconds 3
Start-ScheduledTask -TaskName "RupMES Edge Dashboard"
```

One line can have any number of stations. The form supports adding, editing, and removing stations and endpoints. At least one station and one endpoint must remain configured.

## First OPC UA configuration

Copy the required OPC UA certificate files to the configured paths under `C:\ProgramData\RupMES Edge\certificates`. Set the OPC UA reader password as a machine environment variable:

```powershell
[Environment]::SetEnvironmentVariable("RUPMES_EDGE_OPCUA_PASSWORD", "<reader-password>", "Machine")
```

The OPC UA account must be read-only. Do not expose the dashboard to an untrusted network; its default binding is `127.0.0.1`.

## Administrator token

The dashboard task runs as `SYSTEM`, so its administrator token is stored as a **machine** environment variable, normally named `RUPMES_EDGE_ADMIN_TOKEN`. It is never stored in the SQLite database or displayed in the dashboard.

### Show the current token

Run PowerShell as administrator:

```powershell
[Environment]::GetEnvironmentVariable("RUPMES_EDGE_ADMIN_TOKEN", "Machine")
```

Treat the output as a secret: do not include it in screenshots, tickets, or chat messages.

### Replace a lost or exposed token

Run PowerShell as administrator, choose a strong replacement value, then restart Edge:

```powershell
[Environment]::SetEnvironmentVariable("RUPMES_EDGE_ADMIN_TOKEN", "<new-long-random-token>", "Machine")
Stop-ScheduledTask -TaskName "RupMES Edge Dashboard"
Start-Sleep -Seconds 3
Start-ScheduledTask -TaskName "RupMES Edge Dashboard"
```

Replacing the token does not remove the saved configuration or historical data.

## Update an existing Edge installation

To update the dashboard and configuration interface without reinstalling dependencies:

1. Extract `dist\RupMES-Edge-History-Update.zip` on the Edge PC.
2. Run `Install-EdgeHistoryUpdate.ps1` as administrator.
3. Reload `http://127.0.0.1:8020/edge` with `Ctrl+F5`.

The update preserves `config.json`, certificates, SQLite history, and the active SQLite configuration. If the administrator token is missing, the update generates and displays one once.

## Run manually

```powershell
$env:PYTHONPATH = "C:\RupMES\RupMes_Trazability_Project\src"
python -m rupmes_edge dashboard --config "C:\ProgramData\RupMES Edge\config.json"
```

## Register automatic startup manually

From an elevated PowerShell window:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\Install-EdgeWindowsService.ps1 -ProjectRoot "C:\RupMES\RupMes_Trazability_Project" -PythonExe "C:\RupMES\RupMes_Trazability_Project\.venv\Scripts\python.exe"
Start-ScheduledTask -TaskName "RupMES Edge Dashboard"
```

The task runs as `SYSTEM`, starts on boot, and retries three times after a failure. Validate `http://127.0.0.1:8020/edge/health` after installation.
