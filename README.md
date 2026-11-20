# Star Citizen Local Telemetry Reader

Python client and Protobuf extractor for Star Citizen's local gRPC `GameTelemetryService` (`sc.game.telemetry.v1`).

## 1. Enable Telemetry in Star Citizen

Add the following to your `USER.cfg` (e.g. `D:\StarCitizen\StarCitizen\PTU\USER.cfg`) and restart the game:

```ini
grpc.client.server.port = 50051
server.game.telemetry.enabled = 1
# Optional: allow TriggerGameAction RPCs
server.game.telemetry.trigger.actions.enabled = 1
```

Useful in-game console (`~`) CVars:
- `server.game.telemetry.enabled 1` / `0`
- `server.game.telemetry.test.data 1` (forces synthetic telemetry frames)
- `server.game.telemetry.stream.interval.ms`
- `server.game.telemetry.trigger.actions.enabled`
- `server.game.telemetry.trigger.debounce.ms`

## 2. Usage

### Stream live telemetry (typed, real field names)
```powershell
python sc_telemetry.py
python sc_telemetry.py stream --max-frames 5
python sc_telemetry.py stream --filter vehicle
python sc_telemetry.py stream --compact
```

### List triggerable game actions
```powershell
python sc_telemetry.py actions
python sc_telemetry.py actions --json
```

### Trigger a game action
```powershell
python sc_telemetry.py trigger <action_name>
python sc_telemetry.py trigger <action_name> --hold-ms 250
```

### Raw wire-format decoder (fallback without compiled stubs)
```powershell
python sc_telemetry_raw.py
```

## 3. Re-extracting `.proto` Definitions After a Game Update

If a new Star Citizen patch updates the telemetry schema, re-extract and recompile the stubs:

```powershell
python extract_sc_protos.py
python -m grpc_tools.protoc -I sc_protos --python_out=. --grpc_python_out=. sc_protos/sc/game/telemetry/v1/types.proto sc_protos/sc/game/telemetry/v1/api.proto
```

You can also point to a different executable path:
```powershell
python extract_sc_protos.py --exe "C:\Path\To\StarCitizen.exe"
```

