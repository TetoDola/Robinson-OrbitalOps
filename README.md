# Robinson-OrbitalOps

OrbitOps command center for a single orbital GPU datacenter satellite.

The project is intentionally split into two independent entry points:

- `frontend/`: static browser UI and 3D scene.
- `backend/`: telemetry API provider.

The boundary between them is the versioned data contract in [docs/data-contract.md](docs/data-contract.md). Any live source, mock source, or future flipped-bit demo data must be adapted to that contract before it reaches the frontend.

## Run

Use two terminals:

```bash
npm run dev:backend
```

```bash
npm run dev:frontend
```

Then open:

```text
http://localhost:3000
```

Default endpoints:

- Frontend: `http://localhost:3000`
- Backend health: `http://localhost:4000/health`
- Backend telemetry: `http://localhost:4000/api/telemetry`

To point the frontend at another backend:

```bash
ORBITOPS_API_BASE=http://localhost:4000 npm run dev:frontend
```

## Structure

| Path | Role |
| --- | --- |
| `frontend/index.html` | Static OrbitOps UI. Polls the backend every second. |
| `frontend/server.mjs` | Static frontend server. Injects `window.ORBITOPS_API_BASE`. |
| `frontend/geo/` | Frontend-only globe geography asset. |
| `backend/server.mjs` | Backend API server. Owns `/api/telemetry`. |
| `backend/data/telemetry.mock.json` | Backend mock payload. Empty `incidents` by default. |
| `docs/data-contract.md` | Human-readable data contract. |
| `schemas/orbitalops.telemetry.v1.schema.json` | JSON Schema for telemetry payload validation. |

## Data Contract Rules

- The frontend must not import backend files directly.
- The backend must return payloads matching `orbitalops.telemetry.v1`.
- There is exactly one satellite in `satellites`.
- `updatePolicy.intervalMs` is `1000`, so the frontend polls once per second.
- `incidents` stays empty until the team adds synthetic flipped-bit demo incidents.
- API keys or live provider secrets belong in the backend only.

## Checks

```bash
npm run check:json
```
