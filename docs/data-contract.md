# OrbitalOps Data Contract

Version: `orbitalops.telemetry.v1`

This contract describes the payload the frontend should consume, whether the source is a local mock, a backend proxy, or a live satellite feed.

## Envelope

```json
{
  "contractVersion": "orbitalops.telemetry.v1",
  "generatedAt": "2026-07-04T10:15:00Z",
  "source": {
    "mode": "mock",
    "provider": "local-demo",
    "latencyMs": 42
  },
  "updatePolicy": {
    "transport": "polling",
    "intervalMs": 1000
  },
  "mission": {},
  "groundStations": [],
  "satellites": [],
  "incidents": [],
  "missionPatch": {}
}
```

## Required Top-Level Fields

| Field | Type | Notes |
| --- | --- | --- |
| `contractVersion` | string | Must be `orbitalops.telemetry.v1` for this first version. |
| `generatedAt` | ISO datetime string | Timestamp for the whole snapshot. |
| `source` | object | Where the data came from: mock, live, replay, or fallback. |
| `updatePolicy` | object | Expected frontend refresh behavior. Current target: polling every second. |
| `mission` | object | Current global mission state. |
| `groundStations` | array | Known downlink stations. |
| `satellites` | array | Exactly one satellite for the current demo. |
| `incidents` | array | Empty for now. Future demo incidents can include synthetic flipped-bit events. |
| `missionPatch` | object | Commander Agent recommended recovery plan. |

## Satellite Object

```json
{
  "id": "AKJA-01",
  "name": "AKJA Orbital Datacenter 01",
  "status": "degraded",
  "severity": "red",
  "orbit": {
    "model": "tle",
    "tle": {
      "line1": "1 00000U 26001A   26185.42708333  .00000000  00000+0  00000+0 0  9991",
      "line2": "2 00000  51.6000 120.0000 0005000  45.0000 315.0000 15.50000000    01"
    },
    "position": {
      "latDeg": 48.85,
      "lonDeg": 2.35,
      "altitudeKm": 420
    },
    "velocityKms": 7.67,
    "phase": "approaching_eclipse",
    "timeToEclipseSec": 660
  },
  "telemetry": {
    "computeLoadPct": 78,
    "agentLatencyMs": 38,
    "batteryPct": 38,
    "solarInputKw": 1.2,
    "radiationRisk": "elevated",
    "thermalC": 20.8,
    "eccTrend": "rising"
  },
  "radiationRisk": {
    "radiationRiskScore": 36,
    "radiationLevel": "MEDIUM",
    "mainCause": "solar",
    "recommendedAction": "delay compute",
    "explanation": "NOAA/SWPC live ingest: solar 44%, Van Allen 8%, geomagnetic 22%."
  },
  "downlink": {
    "activeStationId": "zurich-03",
    "windowAvailableGb": 22,
    "windowRequiredGb": 180,
    "signalPct": 86
  },
  "checkpoints": {
    "lastTrustedId": "ckpt-184500",
    "latestId": "ckpt-184900",
    "latestStatus": "suspect"
  },
  "nodes": [],
  "agents": []
}
```

## Enumerations

Status:

```text
nominal | degraded | unsafe | unavailable | unknown
```

Severity:

```text
green | yellow | orange | red
```

Orbit phase:

```text
sunlit | approaching_eclipse | eclipse | exiting_eclipse | unknown
```

Radiation level:

```text
LOW | MEDIUM | HIGH | CRITICAL
```

Radiation main cause:

```text
solar | Van Allen | geomagnetic storm
```

Radiation recommended action:

```text
continue | delay compute | migrate workload | shutdown sensitive tasks
```

Source mode:

```text
mock | live | replay | fallback
```

## Data Needed From The Team

I inferred the first contract from the current UI. The current decisions are:

- One satellite only.
- Live refresh target is polling every 1 second.
- `incidents` stays empty for now; synthetic flipped-bit incidents can be added later for demos.

Open questions:

1. Satellite source: will live orbital position come as TLE, lat/lon/altitude snapshots, or both?
2. Compute telemetry: do you have real GPU/node metrics, or should we keep node status synthetic?
3. Security: will the data source require API keys? If yes, route it through a backend proxy, not directly from the browser.

## Frontend Mapping

Current UI IDs can map directly to these fields:

| UI element | Contract field |
| --- | --- |
| `metricSpeed` | `satellites[0].orbit.velocityKms` |
| `metricAltitude` | `satellites[0].orbit.position.altitudeKm` |
| `metricLocation` | `satellites[0].orbit.position.latDeg`, `lonDeg` |
| `metricCompute` | `satellites[0].telemetry.computeLoadPct` |
| `metricLatency` | `satellites[0].telemetry.agentLatencyMs` |
| `metricBattery` | `satellites[0].telemetry.batteryPct` |
| `metricSolar` | `satellites[0].telemetry.solarInputKw` |
| `metricEclipse` | `satellites[0].orbit.timeToEclipseSec` |
| `metricRadiation` | `satellites[0].radiationRisk.radiationLevel`, `radiationRiskScore`, `explanation` |
| `metricECC` | `satellites[0].telemetry.eccTrend` |
| `metricTrusted` | `satellites[0].checkpoints.lastTrustedId` |
| `metricLatest` | `satellites[0].checkpoints.latestId` + `latestStatus` |
| `metricDownlink` | `windowAvailableGb` / `windowRequiredGb` |
| `agent*` | `satellites[0].agents[]` |
| incident strip | `incidents[]` |
| patch panel | `missionPatch` |

## Ownership Boundary

- Frontend entry point: `frontend/index.html`.
- Frontend data access: HTTP request to `${ORBITOPS_API_BASE}/api/telemetry`.
- Backend entry point: `backend/server.mjs`.
- Backend mock/live adapter output: `orbitalops.telemetry.v1`.

The frontend must not read `backend/data/telemetry.mock.json` directly. The backend owns source-specific details and must adapt them to this contract.

## Radiation Risk Pipeline

Radiation is a backend data entry point. The frontend must not fetch raw solar wind, X-ray, proton, geomagnetic, or belt data and must not duplicate radiation scoring rules.

Backend flow:

1. Read the active satellite position from the telemetry snapshot: `orbit.position.latDeg`, `lonDeg`, `altitudeKm`, and snapshot `generatedAt`.
2. Build a short predicted trajectory from the current orbit state.
3. Ingest radiation environment data from `ORBITOPS_RADIATION_SOURCE`:
   - `auto` attempts NOAA/SWPC public JSON feeds and falls back to `backend/data/radiation-environment.mock.json`.
   - `live` requires NOAA/SWPC ingest to succeed.
   - `mock` uses the backend mock radiation environment file.
4. Estimate solar exposure from solar wind, X-ray flux, and proton flux.
5. Estimate geomagnetic storm pressure from Kp.
6. Estimate Van Allen/South Atlantic Anomaly risk from altitude and current/predicted positions.
7. Return only the processed risk object to clients.

The output object is `satellites[0].radiationRisk` and `/api/radiation-risk.radiationRisk`:

```json
{
  "radiationRiskScore": 36,
  "radiationLevel": "MEDIUM",
  "mainCause": "solar",
  "recommendedAction": "delay compute",
  "explanation": "NOAA/SWPC live ingest: solar 44%, Van Allen 8%, geomagnetic 22%."
}
```

Agents should treat `radiationRisk` as one decision input alongside power, thermal, downlink, checkpoint integrity, and workload state.
