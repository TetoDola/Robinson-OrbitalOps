# OrbitOps Backend Plan

OrbitOps backend is a Dockerized mission-control simulator: it models an orbital GPU datacenter, runs independent agents over live telemetry, calculates orbit-aware constraints, generates safe mission patches, executes approved mock commands, and streams the full incident lifecycle to the UI.

The backend should not become a real spacecraft simulator. It should feel serious, deterministic, inspectable, and demoable.

## 1. Backend Definition

Build one Dockerized backend that:

- Simulates a space GPU datacenter.
- Runs mock independent agents.
- Calculates orbit, power, radiation, thermal, vibration, and downlink state.
- Generates mission patches.
- Waits for human approval.
- Executes mock commands.
- Verifies recovery.
- Streams world state and lifecycle events to the UI.

Product loop:

```text
Monitor -> Detect -> Explain -> Propose -> Approve -> Execute -> Verify
```

Core safety rule:

```text
Agents monitor and propose.
Commander creates mission patches.
Safety validator blocks unsafe actions.
Human approves.
Executor acts.
System verifies recovery.
```

## 2. Stack

Use this stack for the hackathon backend:

```text
FastAPI
PostgreSQL
SQLAlchemy 2 async ORM
Alembic migrations
Redis Streams
Python async workers
Crusoe Managed Inference
Smithers optional workflow supervision
Docker Compose
MinIO optional
```

Rationale:

- FastAPI provides REST endpoints and WebSockets for live UI updates.
- PostgreSQL is the source of truth.
- PostgreSQL `jsonb` handles flexible telemetry, findings, and patch payloads.
- SQLAlchemy 2 async ORM is the implementation layer for models, relationships, constraints, and transactions.
- Alembic owns schema migrations. Do not hand-write ad hoc runtime DDL in application code.
- Redis Streams provide a lightweight append-only event bus for simulator, agents, commander, executor, and UI events.
- Python async workers keep implementation simple while still separating responsibilities.
- Docker Compose runs the whole backend stack with one command.
- Crusoe Managed Inference is used by the Commander Agent for explanation and JSON polish, not for deterministic safety decisions.
- Smithers can help scaffold, run, watch, and approve agent workflows during development and demos, but it should not become the source of truth for mission state.
- MinIO is optional for mock thermal images, vibration files, logs, and checkpoint manifests.

Crusoe integration should follow the local root reference file:

```text
../CRUSOE.md
```

Known Crusoe settings from that file:

```text
CRUSOE_BASE_URL=https://api.inference.crusoecloud.com/v1/
CRUSOE_API_KEY=<provided by environment>
```

Recommended default model for text-only Commander polishing:

```text
deepseek-ai/Deepseek-V4-Flash
```

Use an exact model string from `../CRUSOE.md`. Do not guess model names.

Smithers note:

```text
Use Smithers for agent workflow orchestration and supervision.
Use Redis + Postgres for runtime state and frontend status.
Do not make the UI depend directly on Smithers internals.
```

Do not confuse:

```text
Smithers = optional workflow orchestration and supervision runtime.
Smithery = MCP server registry / agent tool marketplace.
```

## 3. Runtime Services

Run these services in Docker Compose.

### `orbitops-api`

Responsibilities:

- FastAPI backend.
- REST API.
- WebSocket live feed.
- Mission patch approval and rejection endpoints.
- Reads and writes PostgreSQL.
- Publishes UI events.

### `orbitops-simulator`

Responsibilities:

- Mock satellite orbit.
- Mock GPU telemetry.
- Mock power and battery state.
- Mock radiation and ECC events.
- Mock thermal, vibration, and downlink events.
- Publishes telemetry to Redis Streams.

### `orbitops-agents`

Responsibilities:

- Runs independent mock agents:
  - Workload Agent.
  - Thermal / Physical Health Agent.
  - Power / Orbit Agent.
  - Radiation / Integrity Agent.
  - Checkpoint / Downlink Agent.
  - Vibration Health Agent.
  - Commander Agent.
- Consumes telemetry and world state.
- Produces findings and mission patches.
- Emits agent status updates for the UI:
  - monitoring
  - detecting
  - explaining
  - proposing
  - awaiting_approval
  - idle
  - blocked
  - error

### `orbitops-workflow-supervisor` optional

Responsibilities:

- Optional Smithers-driven workflow runner for demos and development.
- Starts scripted agent workflow runs.
- Watches agent steps.
- Mirrors Smithers run status into `agent:status` and `ui:events`.
- Never bypasses API approval or safety validation.

Use this only if it helps demo reliability. The core backend must still work without it.

### `orbitops-executor`

Responsibilities:

- Listens for approved mission patch actions.
- Executes mock commands.
- Mutates world state.
- Emits command and verification events.

### `postgres`

Responsibilities:

- Source of truth for assets, jobs, checkpoints, telemetry history, findings, incidents, patches, approvals, and commands.

### `redis`

Responsibilities:

- Event bus.
- Redis Streams for telemetry, findings, patches, command requests, command results, and UI events.

### `minio` optional

Responsibilities:

- Mock object store for:
  - Thermal images.
  - Vibration telemetry files.
  - Logs.
  - Checkpoint manifests.

Keep MinIO out of Phase 1 unless the demo needs file URLs.

## 4. Architecture Flow

```text
Simulator
  -> telemetry:events
  -> Independent Mock Agents
  -> agent:findings
  -> Commander Agent
  -> commander:patches
  -> API Approval Endpoint
  -> command:requests
  -> Executor
  -> command:results
  -> Verification Events
  -> World State + WebSocket Feed
```

The UI should mostly depend on:

```text
GET /world-state
WS /ws/live
```

Everything visual should be derivable from the canonical world state and event stream.

## 4C. Runtime Guarantees

These guarantees must be implemented before broad agent work starts. They prevent state drift, duplicate execution, lost stream events, and unsafe approvals.

### ORM-First Persistence

Implementation rule:

```text
Use SQLAlchemy 2 async ORM for normal database reads/writes.
Use Alembic for schema creation and migration.
Do not use direct SQL strings for application CRUD.
Raw SQL in this document is schema intent only.
```

Allowed exceptions:

```text
Alembic migration operations.
Postgres advisory locks when SQLAlchemy has no clean ORM helper.
Postgres-specific indexes/constraints expressed in migrations.
Small health checks if the ORM session is not initialized yet.
```

Implementation files:

```text
backend/app/db/models.py      SQLAlchemy ORM models
backend/app/db/session.py     async engine, async_sessionmaker, transaction helpers
backend/app/db/migrations/    Alembic migration scripts
```

Transaction style:

```python
async with async_session() as session:
    async with session.begin():
        patch = await session.get(MissionPatch, patch_id, with_for_update=True)
        # mutate ORM objects
        session.add(OutboxEvent(...))
```

Do not mix ORM state with separate raw SQL updates inside the same unit of work unless it is in an Alembic migration.

### Single World-State Writer

PostgreSQL owns canonical world state. Redis Streams distribute changes. No service should keep private authoritative state.

Use one table for current state and one table for history:

```sql
CREATE TABLE world_state_current (
  id BOOLEAN PRIMARY KEY DEFAULT true CHECK (id),
  version BIGINT NOT NULL DEFAULT 0,
  state JSONB NOT NULL,
  updated_by TEXT NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE world_state_snapshots (
  version BIGINT PRIMARY KEY,
  state JSONB NOT NULL,
  reason TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

Write path:

```text
simulator/executor computes a state patch
  -> calls world_state service
  -> world_state service opens DB transaction
  -> SELECT world_state_current FOR UPDATE
  -> applies patch and increments version
  -> inserts snapshot when needed
  -> inserts outbox row for world_state.updated
  -> commits
  -> outbox publisher writes to Redis/ui streams
```

Rules:

```text
Only services.world_state writes world_state_current.
Simulator can propose telemetry patches but does not directly own state.
Agents never mutate world state.
Commander never mutates world state.
Executor mutates world state only through services.world_state.
API reads from world_state_current for GET /world-state.
```

### Transaction Boundaries and Outbox

Any API call that changes mission state must use one DB transaction and an outbox row.

Approval transaction:

```text
BEGIN
  SELECT mission_patch FOR UPDATE
  validate status = pending_approval
  if already approved, return existing approval and commands
  insert approval row with idempotency key
  update mission_patch status = approved
  create command rows for patch actions
  insert outbox event mission_patch.approved
  insert outbox event command.batch_created
COMMIT
outbox publisher writes command:requests and ui:events
```

Reject transaction:

```text
BEGIN
  SELECT mission_patch FOR UPDATE
  validate status = pending_approval
  insert approval row with status = rejected
  update mission_patch status = rejected
  insert outbox event mission_patch.rejected
COMMIT
outbox publisher writes ui:events
```

Outbox table:

```sql
CREATE TABLE outbox_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type TEXT NOT NULL,
  stream_name TEXT NOT NULL,
  dedupe_key TEXT NOT NULL UNIQUE,
  payload JSONB NOT NULL,
  published_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

### Idempotency

All mutating endpoints accept an optional `Idempotency-Key` header.

Required dedupe keys:

```text
approval:{mission_patch_id}:{operator_id}:{decision}
command:{mission_patch_id}:{action_index}:{action_type}:{target_asset_id}
incident:{incident_key}
patch:{incident_id}:active
finding:{agent}:{finding_signature}:{scenario_time_bucket}
world_state:{version}
```

Duplicate approvals must be harmless:

```text
If patch is already approved, return 200 with existing commands.
If patch is already rejected, return 409 for approve.
If the same idempotency key repeats, return the original response.
```

### Incident and Patch Uniqueness

Each incident needs a deterministic `incident_key`.

Example:

```text
training_continuity_risk:llm-train-042:ckpt-184900
thermal_physical_risk:node-c
radiation_integrity_risk:node-b:gpu-b-3
```

Database rules:

```sql
ALTER TABLE incidents ADD COLUMN incident_key TEXT NOT NULL;
CREATE UNIQUE INDEX incidents_one_active_key
  ON incidents (incident_key)
  WHERE status IN ('open', 'investigating', 'pending_approval');

CREATE UNIQUE INDEX mission_patches_one_active_incident
  ON mission_patches (incident_id)
  WHERE status IN ('draft', 'pending_approval', 'approved', 'executing');
```

Commander rule:

```text
Use incident_key plus SELECT FOR UPDATE or pg_advisory_xact_lock(hashtext(incident_key)).
Update an existing active incident/patch instead of creating duplicates.
```

### Redis Consumer Groups, ACK, Retry, and Dead Letter

Every worker must consume Redis Streams through consumer groups.

| Stream | Consumer group | Consumers |
|---|---|---|
| `telemetry:events` | `agents` | `orbitops-agents-*` |
| `agent:status` | `api-status` | `orbitops-api-*` |
| `agent:findings` | `commander` | `orbitops-agents-commander-*` |
| `commander:patches` | `api-patches` | `orbitops-api-*` |
| `command:requests` | `executor` | `orbitops-executor-*` |
| `command:results` | `api-results` | `orbitops-api-*` |
| `ui:events` | `websocket-broadcast` | `orbitops-api-*` |

Processing contract:

```text
Read with consumer group.
Validate payload schema.
Check dedupe key before side effects.
Apply DB transaction.
ACK only after DB commit succeeds.
If processing fails, leave pending for retry.
If retry_count > 3, move to deadletter:events and ACK original.
```

Dead-letter event shape:

```json
{
  "source_stream": "command:requests",
  "source_id": "redis-message-id",
  "consumer_group": "executor",
  "error": "validation failed",
  "payload": {},
  "failed_at": "2026-07-04T19:30:00Z"
}
```

### Command Enum and Payload Schemas

Use one command enum everywhere: mission patches, safety validator, executor, commands table, API docs, and UI labels.

Allowed command types for the hackathon:

```text
collect_logs
snapshot_evidence
run_health_check
mark_node_suspect
mark_checkpoint_suspect
rollback_training
cordon_node
pause_job
kill_process
set_gpu_power_limit
increase_checkpoint_frequency
switch_cooling_loop
transfer_priority
```

Payload schemas:

```json
{
  "mark_checkpoint_suspect": {
    "checkpoint_id": "ckpt-184900"
  },
  "rollback_training": {
    "job_id": "llm-train-042",
    "checkpoint_id": "ckpt-184500"
  },
  "cordon_node": {
    "node_id": "node-b",
    "scope": "critical_training"
  },
  "set_gpu_power_limit": {
    "node_id": "node-a",
    "power_percent": 70
  },
  "increase_checkpoint_frequency": {
    "job_id": "llm-train-042",
    "interval_minutes": 15
  },
  "transfer_priority": {
    "send_first": ["checkpoint_manifest", "checkpoint_hashes", "training_logs", "delta_checkpoint"],
    "defer": ["full_checkpoint"]
  },
  "switch_cooling_loop": {
    "from_loop_id": "coolant-loop-a",
    "to_loop_id": "coolant-loop-b"
  }
}
```

### Startup and Dependency Readiness

Docker Compose `depends_on` is not enough by itself.

Requirements:

```text
Postgres service has healthcheck.
Redis service has healthcheck.
Application services retry DB and Redis connections on startup.
Phase 1 boots without CRUSOE_API_KEY.
If CRUSOE_API_KEY is missing, Commander uses deterministic template explanations.
```

## 4A. Agent Workflow and Cadence

Decision:

```text
Simulator ingests and publishes telemetry every 1 second.
Fast numeric agents evaluate every 2 seconds.
Heavier evidence agents evaluate every 5 seconds.
Commander evaluates every 10 seconds or immediately after RED findings.
Mission Patch creation is debounced so one incident produces one patch, not a flood.
Frontend receives status/events in real time over WebSocket.
```

Keep these roles separate:

```text
Simulator = generates world telemetry.
Agents = independently inspect telemetry and produce findings/status.
Commander = fuses findings into incidents and mission patches.
Safety validator = deterministic gate before approval.
API = human approval interface and frontend stream.
Executor = mutates mock state after approval.
Smithers = optional workflow supervisor, not source of truth.
```

### Data Ingestion Cadence

Use this cadence for the hackathon:

| Producer | Cadence | Output | Notes |
|---|---:|---|---|
| Simulator tick | 1s | `telemetry:events`, world state patch | Updates orbit, power, thermal, radiation, downlink, training, nodes. |
| API world-state snapshot | 1s or on change | `world_state.updated` | WebSocket sends compact state diffs or full state for simplicity. |
| Workload Agent | 2s | `agent:status`, `agent:findings` | Detects stuck ranks, orphan GPU load, scheduler mismatch. |
| Thermal / Physical Agent | 2s | `agent:status`, `agent:findings` | Watches temp, hotspot, cooling state. |
| Power / Orbit Agent | 2s | `agent:status`, `agent:findings` | Watches eclipse, battery, solar, power budget. |
| Radiation / Integrity Agent | 2s | `agent:status`, `agent:findings` | Watches ECC, Xid, NaN loss, checkpoint trust. |
| Checkpoint / Downlink Agent | 5s | `agent:status`, `agent:findings` | Watches checkpoint size, transfer window, hashes, manifests. |
| Vibration Health Agent | 5s | `agent:status`, `agent:findings` | Watches structure-borne vibration anomaly score. |
| Commander Agent | 10s or immediate on RED | `commander:patches`, `ui:events` | Groups active findings, creates one pending patch. |
| Executor | on approval | `command:results`, `ui:events` | Runs mock commands and emits verification. |

For the demo, this is fast enough to feel live without flooding the UI.

### Agent Loop

Each agent runs the same loop:

```text
1. Publish agent.status.updated = monitoring.
2. Read latest world state snapshot.
3. Read recent telemetry events for owned domains.
4. Compute domain risk score.
5. Publish agent.status.updated = detecting.
6. If no issue, publish healthy/monitoring status and stop.
7. If issue exists, build finding with evidence.
8. Publish agent.finding.created.
9. Publish agent.status.updated = proposing.
10. Wait for Commander/approval/executor lifecycle updates.
```

Agent workers should not call each other directly. They communicate through state, streams, and findings.

### Commander Loop

The Commander runs when:

```text
any RED finding is created
two or more ORANGE findings are open
checkpoint trust changes to suspect
time_to_eclipse_min < 15 and battery_percent < 45
every 10 seconds while an incident is active
```

Commander behavior:

```text
1. Publish commander status = monitoring.
2. Collect open findings from the last 2 minutes.
3. Group findings by incident type and affected assets.
4. If a pending mission patch already exists for the incident, update it only if severity increased.
5. Run deterministic action selection.
6. Run safety validator.
7. Optionally call Crusoe for explanation/JSON polish.
8. Persist incident and mission patch.
9. Publish mission_patch.created.
10. Publish commander status = awaiting_approval.
```

Patch debounce:

```text
Do not create a new patch more than once every 30 seconds for the same incident unless severity escalates to RED.
```

### Human Approval Loop

Approval flow:

```text
1. Mission patch status = pending_approval.
2. All related agents publish status = awaiting_approval.
3. Frontend shows Mission Patch approval panel.
4. Operator approves, rejects, modifies, or asks Commander to replan.
5. API runs the approval transaction described in Runtime Guarantees.
6. Outbox publisher emits mission_patch.approved or mission_patch.rejected.
7. Outbox publisher emits command.batch_created and command:requests for approved patches.
8. Executor starts only after approved command rows exist.
```

No approval means no risky command execution. Agents may still run safe autonomous actions:

```text
collect_logs
snapshot_evidence
increase_monitoring
run_health_check
mark_node_suspect
```

### Executor and Verification Loop

Executor flow:

```text
1. Consume approved mission patch from command:requests.
2. Create command rows for each action.
3. Publish command.started.
4. Apply mock world-state effect.
5. Publish command.succeeded or command.failed.
6. Run verification checks.
7. If all checks pass, patch status = verified.
8. Publish verification.completed.
9. Agents return to monitoring with updated state.
```

## 4B. Smithers Role

Smithers is useful for workflow supervision, not mission state.

Use Smithers to:

```text
Run the scripted multi-agent workflow.
Show workflow progress during development.
Handle retries and resumable steps.
Gate a demo workflow at human approval.
Call backend APIs in a controlled sequence.
Mirror workflow status into OrbitOps streams.
```

Do not use Smithers to:

```text
Store canonical world state.
Bypass the OrbitOps API.
Bypass the safety validator.
Let the LLM directly execute commands.
Send UI data that does not also exist in Redis/Postgres.
```

Smithers integration should look like:

```text
Smithers workflow step starts
  -> smithers_adapter publishes agent.status.updated
  -> agent or backend service executes domain logic
  -> result is persisted in Postgres
  -> result is published to Redis
  -> API WebSocket streams it to frontend
```

If Smithers is unavailable, `orbitops-agents` should still run the same workflow using plain Python async loops.

## 5. Folder Structure

Use this backend structure:

```text
backend/
  app/
    main.py
    config.py

    api/
      routes_health.py
      routes_world_state.py
      routes_satellite.py
      routes_agents.py
      routes_agent_status.py
      routes_incidents.py
      routes_mission_patches.py
      routes_commands.py
      routes_simulator.py
      websocket.py

    core/
      schemas.py
      enums.py
      safety.py
      events.py
      constants.py

    db/
      models.py
      session.py
      seed.py
      migrations/

    services/
      world_state.py
      agent_status.py
      orbit_calculator.py
      power_model.py
      radiation_model.py
      thermal_model.py
      downlink_model.py
      mission_patch_builder.py
      command_executor.py
      llm_client.py

    workflows/
      smithers_adapter.py
      demo_workflows.py

    agents/
      base.py
      workload_agent.py
      thermal_physical_agent.py
      power_orbit_agent.py
      radiation_integrity_agent.py
      checkpoint_downlink_agent.py
      vibration_health_agent.py
      commander_agent.py
      runner.py

    simulator/
      scenarios.py
      telemetry_generator.py
      state_machine.py
      mock_assets.py
      mock_jobs.py

  Dockerfile
  pyproject.toml

docker-compose.yml
```

## 6. Canonical World State

Maintain one canonical world state row in PostgreSQL and expose it through a world-state service. Services may cache the latest snapshot locally for reads, but all writes go through the DB transaction path described in Runtime Guarantees.

The API returns this shape from `GET /world-state`:

```json
{
  "timestamp": "2026-07-04T19:30:00Z",
  "satellite": {
    "id": "orbital-dc-01",
    "lat": 48.1,
    "lon": 2.3,
    "alt_km": 550,
    "velocity_km_s": 8.05,
    "orbit_phase": "approaching_eclipse",
    "time_to_eclipse_min": 11,
    "ground_link": "connected"
  },
  "power": {
    "battery_percent": 38,
    "solar_kw": 1.2,
    "compute_budget_kw": 7.5,
    "cooling_power_kw": 2.1,
    "comms_power_kw": 1.0,
    "mode": "degraded_safe"
  },
  "radiation": {
    "risk": "elevated",
    "region": "risk-zone-alpha",
    "ecc_errors_last_5min": 921
  },
  "thermal": {
    "highest_temp_c": 86,
    "hotspot_node": "node-c",
    "cooling_status": "degraded"
  },
  "downlink": {
    "window_open": true,
    "capacity_gb": 22,
    "used_gb": 0,
    "time_remaining_min": 18
  },
  "training": {
    "job_id": "llm-train-042",
    "status": "running",
    "current_step": 184920,
    "last_trusted_checkpoint": "ckpt-184500",
    "latest_checkpoint": "ckpt-184900",
    "latest_checkpoint_status": "suspect"
  },
  "nodes": [
    {
      "id": "node-a",
      "status": "hot_but_usable",
      "gpu_util": 94,
      "temp_c": 82,
      "power_w": 620
    },
    {
      "id": "node-b",
      "status": "integrity_risk",
      "gpu_util": 12,
      "temp_c": 62,
      "ecc_errors": 921
    },
    {
      "id": "node-c",
      "status": "thermal_physical_risk",
      "gpu_util": 5,
      "temp_c": 88,
      "vibration_score": 0.91
    }
  ],
  "latest_agent_findings": [],
  "active_mission_patch": null
}
```

## 7. Database Schema

Use PostgreSQL as source of truth, implemented through SQLAlchemy ORM models and Alembic migrations.

The SQL below describes required tables, constraints, and indexes. Implement these as SQLAlchemy models plus Alembic migration operations, not as direct SQL calls from app code.

Enable UUID generation in the first Alembic migration:

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

Use CHECK constraints for hackathon-safe enums instead of unconstrained strings. They can be migrated to real Postgres enums later.

### `assets`

```sql
CREATE TABLE assets (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  name TEXT NOT NULL,
  parent_id TEXT REFERENCES assets(id),
  status TEXT NOT NULL DEFAULT 'nominal',
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
```

Asset examples:

```text
satellite/orbital-dc-01
rack/rack-1
node/node-a
gpu/gpu-a-0
sensor/thermal-cam-1
sensor/vibration-loop-a
```

### `jobs`

```sql
CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  priority TEXT NOT NULL,
  status TEXT NOT NULL,
  current_step BIGINT DEFAULT 0,
  assigned_assets JSONB NOT NULL DEFAULT '[]',
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
```

### `checkpoints`

```sql
CREATE TABLE checkpoints (
  id TEXT PRIMARY KEY,
  job_id TEXT REFERENCES jobs(id),
  step BIGINT NOT NULL,
  size_gb NUMERIC NOT NULL,
  delta_size_gb NUMERIC NOT NULL,
  status TEXT NOT NULL,
  trusted BOOLEAN DEFAULT false,
  ground_confirmed BOOLEAN DEFAULT false,
  hash_verified BOOLEAN DEFAULT false,
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);
```

Checkpoint statuses:

```text
trusted
suspect
invalid
pending_verification
ground_confirmed
```

### `telemetry_events`

```sql
CREATE TABLE telemetry_events (
  id BIGSERIAL PRIMARY KEY,
  event_type TEXT NOT NULL,
  asset_id TEXT,
  severity TEXT DEFAULT 'INFO',
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

### `agent_findings`

```sql
CREATE TABLE agent_findings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_name TEXT NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('INFO', 'YELLOW', 'ORANGE', 'RED')),
  confidence NUMERIC NOT NULL,
  affected_assets JSONB NOT NULL DEFAULT '[]',
  finding TEXT NOT NULL,
  evidence JSONB NOT NULL DEFAULT '[]',
  risk TEXT,
  recommended_actions JSONB NOT NULL DEFAULT '[]',
  status TEXT DEFAULT 'open' CHECK (status IN ('open', 'superseded', 'resolved')),
  finding_signature TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX agent_findings_open_idx ON agent_findings (status, severity, created_at DESC);
CREATE UNIQUE INDEX agent_findings_dedupe_idx ON agent_findings (agent_name, finding_signature);
```

### `agent_status_events`

Agents must emit lifecycle status even when they have no new finding. The frontend uses these events to show that agents are actively monitoring, detecting, awaiting approval, or blocked.

```sql
CREATE TABLE agent_status_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_name TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('idle', 'starting', 'monitoring', 'detecting', 'explaining', 'proposing', 'awaiting_approval', 'approved', 'executing', 'verifying', 'verified', 'healthy', 'degraded', 'blocked', 'error')),
  phase TEXT NOT NULL CHECK (phase IN ('monitor', 'detect', 'explain', 'propose', 'approve', 'execute', 'verify')),
  severity TEXT DEFAULT 'INFO' CHECK (severity IN ('INFO', 'YELLOW', 'ORANGE', 'RED')),
  message TEXT NOT NULL,
  current_task TEXT,
  progress NUMERIC,
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX agent_status_latest_idx ON agent_status_events (agent_name, created_at DESC);
```

Recommended statuses:

```text
idle
starting
monitoring
detecting
explaining
proposing
awaiting_approval
executing
verifying
healthy
degraded
blocked
error
```

Recommended phases:

```text
monitor
detect
explain
propose
approve
execute
verify
```

### `incidents`

```sql
CREATE TABLE incidents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_key TEXT NOT NULL,
  title TEXT NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('INFO', 'YELLOW', 'ORANGE', 'RED')),
  status TEXT NOT NULL CHECK (status IN ('open', 'investigating', 'pending_approval', 'approved', 'executing', 'verified', 'resolved', 'rejected', 'failed')),
  finding_ids JSONB NOT NULL DEFAULT '[]',
  summary TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX incidents_active_idx ON incidents (status, severity, updated_at DESC);
CREATE UNIQUE INDEX incidents_one_active_key
  ON incidents (incident_key)
  WHERE status IN ('open', 'investigating', 'pending_approval');
```

### `mission_patches`

```sql
CREATE TABLE mission_patches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id UUID REFERENCES incidents(id),
  severity TEXT NOT NULL CHECK (severity IN ('INFO', 'YELLOW', 'ORANGE', 'RED')),
  status TEXT NOT NULL CHECK (status IN ('draft', 'pending_approval', 'approved', 'rejected', 'executing', 'verified', 'failed', 'rolled_back')),
  summary TEXT NOT NULL,
  evidence JSONB NOT NULL DEFAULT '[]',
  actions JSONB NOT NULL DEFAULT '[]',
  rollback_plan JSONB NOT NULL DEFAULT '{}',
  approval_required BOOLEAN DEFAULT true,
  created_by TEXT DEFAULT 'commander_agent',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX mission_patches_status_idx ON mission_patches (status, updated_at DESC);
CREATE UNIQUE INDEX mission_patches_one_active_incident
  ON mission_patches (incident_id)
  WHERE status IN ('draft', 'pending_approval', 'approved', 'executing');
```

Mission patch statuses:

```text
draft
pending_approval
approved
rejected
executing
verified
failed
rolled_back
```

### `commands`

```sql
CREATE TABLE commands (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  mission_patch_id UUID REFERENCES mission_patches(id),
  action_type TEXT NOT NULL CHECK (action_type IN ('collect_logs', 'snapshot_evidence', 'run_health_check', 'mark_node_suspect', 'mark_checkpoint_suspect', 'rollback_training', 'cordon_node', 'pause_job', 'kill_process', 'set_gpu_power_limit', 'increase_checkpoint_frequency', 'switch_cooling_loop', 'transfer_priority')),
  target_asset_id TEXT,
  status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'skipped')),
  input JSONB NOT NULL DEFAULT '{}',
  result JSONB NOT NULL DEFAULT '{}',
  idempotency_key TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX commands_queue_idx ON commands (status, created_at);
CREATE INDEX commands_patch_idx ON commands (mission_patch_id, status);
```

### `approvals`

```sql
CREATE TABLE approvals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  mission_patch_id UUID REFERENCES mission_patches(id),
  status TEXT NOT NULL CHECK (status IN ('approved', 'rejected')),
  operator_id TEXT,
  operator_note TEXT,
  idempotency_key TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ DEFAULT now(),
  decided_at TIMESTAMPTZ
);

CREATE INDEX approvals_patch_idx ON approvals (mission_patch_id, created_at DESC);
```

## 8. Redis Streams

Use these streams:

```text
telemetry:events
agent:status
agent:findings
commander:patches
command:requests
command:results
ui:events
```

Naming convention:

```text
Redis streams use colon names: agent:status.
WebSocket event types use dotted names: agent.status.updated.
Database tables use snake_case names: agent_status_events.
```

Canonical mapping:

| Meaning | Redis stream | WebSocket event type | Database table |
|---|---|---|---|
| Agent lifecycle status | `agent:status` | `agent.status.updated` | `agent_status_events` |
| Agent finding | `agent:findings` | `agent.finding.created` | `agent_findings` |
| Mission patch | `commander:patches` | `mission_patch.created` | `mission_patches` |
| Command request | `command:requests` | `command.started` | `commands` |
| Command result | `command:results` | `command.succeeded` / `command.failed` | `commands` |
| UI broadcast | `ui:events` | source event type | outbox/UI only |

Flow:

```text
simulator -> telemetry:events
agents -> agent:status
agents -> agent:findings
commander -> commander:patches
api approval -> command:requests
executor -> command:results
api/websocket -> ui:events
```

Example event:

```json
{
  "type": "radiation_update",
  "timestamp": "2026-07-04T19:30:00Z",
  "asset_id": "node-b",
  "payload": {
    "risk": "elevated",
    "ecc_correctable_count": 921,
    "xid_event": true
  }
}
```

Example agent status event:

```json
{
  "type": "agent_status",
  "timestamp": "2026-07-04T19:30:00Z",
  "agent": "power_orbit_agent",
  "status": "awaiting_approval",
  "phase": "approve",
  "severity": "ORANGE",
  "message": "Mission Patch patch-042 is waiting for operator approval.",
  "current_task": "checkpoint before eclipse",
  "progress": 0.82,
  "metadata": {
    "mission_patch_id": "patch-042",
    "time_to_eclipse_min": 11
  }
}
```

## 9. Mock Orbit Calculator

Do not implement precise orbital mechanics. Use deterministic demo math.

Constants:

```text
T_orbit = 5400 seconds
altitude = 550 km
inclination = 53 degrees
earth_rotation_period = 86164 seconds
earth_radius_km = 6371
```

Let:

```text
t = seconds since scenario start
theta = 2 * pi * (t mod T_orbit) / T_orbit
```

Latitude:

```text
lat(t) = inclination * sin(theta)
```

Longitude:

```text
lon(t) = wrap180(lon0 + 360 * t / T_orbit - 360 * t / 86164)
```

Altitude:

```text
alt(t) = 550 km
```

Velocity:

```text
v = 2 * pi * (6371 + 550) / 5400 = about 8.05 km/s
```

## 10. Ground Station and Downlink Model

Use one mock ground station:

```text
ground_station_lat = 48.8566
ground_station_lon = 2.3522
```

Angular distance:

```text
delta = arccos(
  sin(lat_s) * sin(lat_g)
  + cos(lat_s) * cos(lat_g) * cos(lon_s - lon_g)
)
```

Horizon visibility angle:

```text
alpha = arccos(R_earth / (R_earth + h))
```

Visible if:

```text
delta < alpha
```

Demo capacities:

```text
physical_estimate_capacity_gb = bandwidth_gbps * window_remaining_seconds / 8
scenario_limited_capacity_gb = 22
full_checkpoint_gb = 180
```

The UI should show the scenario-limited value because it creates the checkpoint conflict.

## 11. Sunlight and Eclipse Model

Use a simple phase model:

```text
orbit_phase_seconds = t mod 5400
sunlight if orbit_phase_seconds < 3300
eclipse if orbit_phase_seconds >= 3300
```

Durations:

```text
sunlight_duration = 55 minutes
eclipse_duration = 35 minutes
```

Power model gets:

```text
sun_factor = 1 if sunlight else 0
```

## 12. Power Model

Model:

```text
solar generation
battery state
GPU load
cooling load
downlink load
bus overhead
```

Solar:

```text
P_solar = P_solar_max * sun_factor * degradation_factor
P_solar_max = 12 kW
degradation_factor = 0.95
```

GPU power:

```text
P_gpu_i = P_idle + util_i * (P_max - P_idle) * derate_factor
P_idle = 80 W
P_max = 700 W
derate_factor = 1.0 normally, 0.7 in degraded mode
```

Cooling:

```text
P_cooling = P_cooling_base + k_cooling * max(0, T_hotspot - T_nominal)
P_cooling_base = 1.5 kW
k_cooling = 0.08 kW/C
T_nominal = 65 C
```

Total load:

```text
P_load = P_compute + P_cooling + P_downlink + P_bus
```

Battery:

```text
E_batt_next = clamp(
  E_batt + (P_solar - P_load) * dt_hours * eta,
  0,
  E_batt_max
)
SOC = 100 * E_batt / E_batt_max
```

Risk thresholds:

```text
SOC > 50%       GREEN
30%-50%         YELLOW
15%-30%         ORANGE
<15%            RED
```

Power Agent alert:

```text
if time_to_eclipse < 15 min and SOC < 45% and checkpoint_age > 30 min:
    recommend checkpoint_before_eclipse
```

## 13. Thermal Model

Do not model fans cooling air. In vacuum, treat heat rejection as radiation and conduction.

Simple model:

```text
T_next = T_current
       + alpha * P_gpu
       - beta * radiator_effectiveness * (T_current - T_radiator)
       - gamma * cooling_mode
       + anomaly_heat
```

Example values:

```text
alpha = 0.25 C per kW per tick
beta = 0.04
gamma = 0.4 if cooling normal, 0.1 if cooling degraded
T_radiator = 20 C
```

Thermal severity:

```text
T < 70 C       GREEN
70-80 C        YELLOW
80-88 C        ORANGE
>88 C          RED
```

Thermal anomaly score:

```text
thermal_score =
  0.45 * normalize(temp_c, 65, 95)
+ 0.25 * normalize(dT_dt, 0, 2)
+ 0.20 * hotspot_score
+ 0.10 * cooling_degradation_score
```

Thermal Agent:

```text
if thermal_score > 0.75:
    severity = RED
elif thermal_score > 0.55:
    severity = ORANGE
elif thermal_score > 0.35:
    severity = YELLOW
```

## 14. Vibration Health Model

Do not call this audio in space. Use structure-borne vibration from contact sensors.

Event:

```json
{
  "type": "vibration_metric",
  "asset_id": "coolant-loop-a",
  "payload": {
    "rms_vibration": 0.82,
    "dominant_frequency_hz": 147,
    "baseline_frequency_hz": 92,
    "spectral_anomaly_score": 0.91
  }
}
```

Score:

```text
frequency_shift = abs(f_current - f_baseline) / f_baseline

vibration_score =
  0.40 * normalize(rms_vibration, 0.2, 1.0)
+ 0.35 * normalize(frequency_shift, 0.05, 0.7)
+ 0.25 * spectral_anomaly_score
```

Agent:

```text
if vibration_score > 0.75 and thermal_score > 0.55:
    finding = "possible cooling loop mechanical fault"
```

Recommended actions:

```text
increase_checkpoint_frequency
reduce_gpu_power_limit
switch_to_backup_cooling_loop
mark_component_for_inspection
```

## 15. Radiation and Training Integrity Model

Do not simulate exact particle hits. Simulate risk and evidence.

Score:

```text
radiation_score =
  0.35 * zone_risk
+ 0.25 * ecc_rate_score
+ 0.20 * xid_score
+ 0.20 * training_integrity_score
```

Inputs:

```text
zone_risk = 0, 0.5, or 1
ecc_rate_score = normalize(ecc_errors_last_5min, 10, 1000)
xid_score = 1 if GPU Xid event occurred else 0
training_integrity_score = 1 if NaN/loss divergence/hash mismatch else 0
```

Severity:

```text
score < 0.3      GREEN
0.3-0.5          YELLOW
0.5-0.75         ORANGE
>0.75            RED
```

Integrity Agent conditions:

```text
if ecc_errors_last_5min > 500:
    recommend cordon_gpu_for_critical_training

if loss_is_nan:
    recommend increase_verification_level

if checkpoint_created_during_risk_window and ecc_errors_high:
    recommend mark_checkpoint_suspect

if checkpoint_hash_mismatch:
    recommend rollback_to_last_trusted_checkpoint
```

Key product framing:

```text
OrbitOps does not predict exact bit flips.
It detects corruption evidence and protects training integrity.
```

## 16. Workload and GPU Anomaly Model

Score:

```text
workload_mismatch_score =
  0.40 * gpu_busy_without_job
+ 0.25 * vram_leak_score
+ 0.20 * straggler_score
+ 0.15 * stuck_job_score
```

Inputs:

```text
gpu_busy_without_job = 1 if gpu_util > 80% and scheduler_job_count == 0 else 0
vram_leak_score = normalize(vram_allocated_after_job_end_min, 1, 15)
straggler_score = normalize(rank_step_lag, 0.05, 0.30)
stuck_job_score = 1 if no_step_progress_for_min > threshold else 0
```

Agent conditions:

```text
if gpu_util > 85% and no_active_job:
    finding = "GPU usage high with no scheduled job"
    recommend snapshot_evidence, cordon_node, kill_orphan_process_after_approval

if no_step_progress_for_min > 5 and gpu_util > 80:
    finding = "training job appears stuck"
    recommend restart_worker, run_distributed_health_check
```

## 17. Checkpoint and Downlink Model

Primary problem:

```text
full checkpoint may be larger than available downlink
latest checkpoint may be suspect
last trusted checkpoint must not be overwritten
```

Checkpoint freshness risk:

```text
checkpoint_age_score = normalize(checkpoint_age_min, 15, 90)
```

Downlink fit ratio:

```text
fit_ratio = available_downlink_gb / checkpoint_size_gb
```

If:

```text
fit_ratio < 1
```

then full checkpoint does not fit.

Transfer priority:

```text
priority_score(item) =
  0.40 * recovery_value
+ 0.25 * small_size_bonus
+ 0.20 * trust_value
+ 0.15 * urgency
```

For the demo:

```text
Full checkpoint = 180 GB
Available downlink = 22 GB
Manifest + hashes = 0.4 GB
Delta checkpoint = 14 GB
```

Recommendation:

```text
send manifest, hashes, logs, and delta checkpoint
defer full checkpoint
```

## 18. Agent Output Schema

All agents must output this shape:

```json
{
  "agent": "radiation_integrity_agent",
  "timestamp": "2026-07-04T19:30:00Z",
  "severity": "RED",
  "confidence": 0.86,
  "affected_assets": ["node-b", "gpu-b-3", "ckpt-184900"],
  "finding": "ECC errors spiked before checkpoint completion.",
  "evidence": [
    "ECC errors increased from 12 to 921",
    "loss became NaN on rank 17",
    "checkpoint ckpt-184900 completed during elevated radiation window"
  ],
  "risk": "Latest checkpoint may contain corrupted training state.",
  "recommended_actions": [
    "mark_checkpoint_suspect",
    "rollback_to_last_trusted_checkpoint",
    "cordon_gpu_for_critical_training"
  ]
}
```

This interface lets later teams replace mock agents with real agents without changing the backend.

## 18A. Agent Status Schema

Findings are not enough for the frontend. Every agent must also emit status updates so the UI can show live cards like:

```text
monitoring
detecting
awaiting approval
executing
verified
blocked
```

Status event schema:

```json
{
  "type": "agent.status.updated",
  "timestamp": "2026-07-04T19:30:00Z",
  "agent": "thermal_physical_agent",
  "display_name": "Thermal / Physical Agent",
  "phase": "detect",
  "status": "detecting",
  "severity": "RED",
  "message": "Node C hotspot confirmed by IR and rack telemetry.",
  "current_task": "thermal anomaly scoring",
  "progress": 0.74,
  "affected_assets": ["node-c", "thermal-cam-1"],
  "linked_finding_id": "optional-uuid",
  "linked_incident_id": "optional-uuid",
  "linked_mission_patch_id": "optional-uuid",
  "metadata": {
    "hotspot_temp_c": 88,
    "cooling_status": "degraded"
  }
}
```

Allowed `phase` values:

```text
monitor
detect
explain
propose
approve
execute
verify
```

Allowed `status` values:

```text
idle
starting
monitoring
detecting
explaining
proposing
awaiting_approval
approved
executing
verifying
verified
healthy
degraded
blocked
error
```

Frontend mapping:

| Status | UI label | UI meaning |
|---|---|---|
| `monitoring` | Monitoring | Agent is watching live telemetry. |
| `detecting` | Detecting | Agent is evaluating a possible anomaly. |
| `explaining` | Explaining | Agent is gathering evidence and building rationale. |
| `proposing` | Proposing | Agent has recommended actions for Commander. |
| `awaiting_approval` | Awaiting approval | Agent is blocked until operator approves the Mission Patch. |
| `executing` | Executing | Approved commands are running. |
| `verifying` | Verifying | Recovery checks are running. |
| `verified` | Verified | Recovery passed for this agent domain. |
| `blocked` | Blocked | Agent cannot proceed without operator or state change. |
| `error` | Error | Agent failed or produced invalid output. |

Status throttling:

```text
Emit immediately when status changes.
Emit heartbeat every 10 seconds while status is unchanged.
Do not emit more than 1 status update per agent per second.
```

The WebSocket should stream the latest status immediately on client connect, then stream incremental updates.

## 19. Commander Agent

The Commander consumes active findings and produces one mission patch.

Hackathon implementation:

```text
Rule-based action selection
+ Crusoe Managed Inference for explanation and final JSON polish
```

Do not let the LLM decide safety. Deterministic code decides safety and allowed actions.

Prompt structure:

```text
STATIC PREFIX:
- OrbitOps mission doctrine
- allowed commands
- safety rules
- mission patch JSON schema
- agent role definitions
- approval policy

DYNAMIC SUFFIX:
- latest world state
- latest agent findings
- current incident timeline
```

This structure is cache-friendly because stable context stays at the beginning.

## 20. Mission Patch Schema

```json
{
  "mission_patch_id": "patch-042",
  "incident_type": "training_continuity_risk",
  "severity": "RED",
  "summary": "Critical training job is at risk due to thermal stress, ECC escalation, approaching eclipse, and limited downlink.",
  "evidence": [
    {
      "agent": "thermal_physical_agent",
      "finding": "Node A temperature is rising into ORANGE range."
    },
    {
      "agent": "radiation_integrity_agent",
      "finding": "Checkpoint ckpt-184900 is suspect."
    },
    {
      "agent": "power_orbit_agent",
      "finding": "Eclipse begins in 11 minutes."
    },
    {
      "agent": "checkpoint_downlink_agent",
      "finding": "Full checkpoint exceeds current downlink capacity."
    }
  ],
  "actions": [
    {
      "type": "mark_checkpoint_suspect",
      "checkpoint_id": "ckpt-184900"
    },
    {
      "type": "rollback_training",
      "checkpoint_id": "ckpt-184500"
    },
    {
      "type": "set_gpu_power_limit",
      "node_id": "node-a",
      "power_percent": 70
    },
    {
      "type": "cordon_node",
      "node_id": "node-b",
      "scope": "critical_training"
    },
    {
      "type": "increase_checkpoint_frequency",
      "job_id": "llm-train-042",
      "interval_minutes": 15
    },
    {
      "type": "transfer_priority",
      "send_first": [
        "checkpoint_manifest",
        "checkpoint_hashes",
        "training_logs",
        "delta_checkpoint"
      ],
      "defer": [
        "full_checkpoint"
      ]
    }
  ],
  "approval_required": true,
  "rollback_plan": {
    "if_verification_fails": [
      "pause_training",
      "preserve_forensics",
      "resume_from_ground_confirmed_checkpoint"
    ]
  }
}
```

## 21. Safety Validator

Rules:

```text
Cannot execute without approval unless action is safe_autonomous.
Cannot rollback to suspect checkpoint.
Cannot promote suspect checkpoint as trusted.
Cannot schedule critical job on RED integrity node.
Cannot overwrite last trusted checkpoint.
Cannot reduce cooling below minimum.
Cannot delete artifact in demo mode.
Cannot hard reset node without approval.
```

Safe autonomous actions:

```text
collect_logs
snapshot_evidence
increase_monitoring
run_health_check
mark_node_suspect
increase_checkpoint_frequency
```

Approval-required actions:

```text
rollback_training
cordon_node
pause_job
kill_process
set_gpu_power_limit
switch_cooling_loop
transfer_checkpoint
```

Validator output:

```json
{
  "allowed": false,
  "reason": "Cannot rollback to ckpt-184900 because checkpoint status is suspect.",
  "safe_alternative": "rollback_to_ckpt-184500"
}
```

## 22. Command Executor

The executor listens only after approval.

The executor only accepts command types from the enum in Runtime Guarantees. Do not introduce alternate names in individual agents or mission patches.

### `set_gpu_power_limit`

Effects:

```text
derate_factor = power_percent / 100
P_gpu decreases
T_node trend decreases
training_throughput decreases
```

Verification:

```text
temperature_slope <= 0 after 30 seconds
```

### `mark_checkpoint_suspect`

Effects:

```text
checkpoint.status = "suspect"
checkpoint.trusted = false
```

Verification:

```text
checkpoint cannot be selected as recovery target
```

### `rollback_training`

Effects:

```text
training.current_step = checkpoint.step
training.status = "recovering"
latest_checkpoint remains quarantined
```

Verification:

```text
job resumes from trusted checkpoint
loss is finite
health check passes
```

### `cordon_node`

Effects:

```text
node.status = "cordoned"
node.allowed_for_critical_training = false
```

Verification:

```text
scheduler target set excludes node
```

### `transfer_priority`

Effects:

```text
downlink_queue = [
  manifest,
  hashes,
  logs,
  delta_checkpoint,
  full_checkpoint_deferred
]
```

Verification:

```text
critical metadata transferred first
used_gb <= capacity_gb
```

## 23. API Endpoints

Implement:

```text
GET /health

GET /world-state
GET /satellite/position
GET /satellite/orbit

GET /agents
GET /agents/status
GET /agents/findings

GET /incidents
GET /incidents/{id}

GET /mission-patches
GET /mission-patches/active
GET /mission-patches/{id}
POST /mission-patches/{id}/approve
POST /mission-patches/{id}/reject
POST /mission-patches/{id}/request-replan
PATCH /mission-patches/{id}/actions

GET /commands
GET /commands/{id}

POST /simulator/scenario/{scenario_name}
POST /simulator/pause
POST /simulator/resume
POST /simulator/reset

WS /ws/live
```

WebSocket event types:

```text
world_state.updated
telemetry.received
agent.status.updated
agent.finding.created
incident.created
mission_patch.created
mission_patch.awaiting_approval
mission_patch.approved
mission_patch.rejected
command.started
command.succeeded
command.failed
verification.completed
```

`GET /agents/status` should return the latest status per agent:

```json
{
  "agents": [
    {
      "agent": "workload_agent",
      "display_name": "Workload Agent",
      "status": "monitoring",
      "phase": "monitor",
      "severity": "INFO",
      "message": "Scheduler and GPU utilization are aligned.",
      "updated_at": "2026-07-04T19:30:00Z"
    },
    {
      "agent": "radiation_integrity_agent",
      "display_name": "Radiation / Integrity Agent",
      "status": "awaiting_approval",
      "phase": "approve",
      "severity": "RED",
      "message": "ckpt-184900 is suspect. Awaiting approval for rollback to ckpt-184500.",
      "linked_mission_patch_id": "patch-042",
      "updated_at": "2026-07-04T19:30:00Z"
    }
  ]
}
```

## 24. Main Demo Scenario

Use one scripted scenario.

```text
T+00:00
Normal training run.

T+00:20
Power / Orbit Agent: eclipse approaching.

T+00:40
Thermal Agent: Node A getting hot.

T+01:00
Radiation Agent: Node B ECC errors rising.

T+01:20
Training metric: loss becomes NaN on rank 17.

T+01:40
Checkpoint ckpt-184900 created during elevated risk.

T+02:00
Downlink Agent: full checkpoint 180 GB, available downlink 22 GB.

T+02:20
Vibration Agent: coolant loop anomaly.

T+02:40
Commander creates mission patch.

T+03:00
Operator approves.

T+03:20
Executor derates Node A, marks checkpoint suspect, rolls back to ckpt-184500, cordons Node B, prioritizes manifest/hash/delta transfer.

T+04:00
Verification succeeds.
```

This single scenario demonstrates the whole product loop.

## 25. Implementation Phases

### Phase 1: Backend skeleton

Build:

```text
FastAPI app
SQLAlchemy async session
Alembic migration setup
Redis connection
Docker Compose
health endpoint
world-state endpoint
agent status endpoint
WebSocket endpoint
```

Initial backend dependencies:

```text
fastapi
uvicorn[standard]
sqlalchemy[asyncio]
asyncpg
alembic
pydantic
pydantic-settings
redis
openai
python-dotenv
```

Acceptance criteria:

```text
docker compose up starts API, Postgres, and Redis.
GET /health returns ok.
Alembic migration creates initial ORM-backed tables.
GET /world-state returns seeded state.
GET /agents/status returns seeded status for all agents.
WS /ws/live emits a heartbeat or seeded state event.
WS /ws/live emits agent.status.updated events.
```

### Phase 2: Simulator

Build:

```text
mock orbit calculator
mock power model
mock thermal model
mock radiation model
mock downlink model
scenario state machine
```

Acceptance criteria:

```text
orbitops-simulator publishes telemetry:events.
world state changes over time.
satellite position and eclipse countdown update.
```

### Phase 3: First vertical agent slice

Build one complete path before adding the remaining agents:

```text
simulator event
-> Power / Orbit Agent
-> finding
-> Commander patch
-> approval
-> executor
-> verification
-> WebSocket UI event
```

Acceptance criteria:

```text
Power / Orbit Agent emits status transitions and one finding.
Commander creates one pending mission patch.
Approval endpoint transitions patch atomically.
Executor processes command requests once.
Verification completes and updates world state.
```

### Phase 4: Remaining mock agents

Then add independent workers:

```text
workload agent
thermal / physical agent
radiation / integrity agent
checkpoint / downlink agent
vibration health agent
```

Acceptance criteria:

```text
Each agent emits the shared finding schema.
Each agent emits status transitions and 10-second heartbeats.
Findings appear in Postgres and agent:findings.
Statuses appear in Postgres and agent:status.
UI receives agent.finding.created events.
UI receives agent.status.updated events.
```

### Phase 5: Commander hardening

Build:

```text
finding grouping
incident creation
mission patch builder
optional Crusoe Managed Inference call
```

Acceptance criteria:

```text
Commander groups active findings into one incident.
Commander creates patch-042 in pending_approval state.
Safety validator runs before patch becomes approvable.
```

### Phase 6: Approval flow

Build:

```text
pending approval state
approve endpoint
reject endpoint
patch status transitions
```

Acceptance criteria:

```text
POST /mission-patches/{id}/approve creates approval record.
Approved patch emits mission_patch.approved.
Rejected patch emits mission_patch.rejected or equivalent UI event.
```

### Phase 7: Executor

Build:

```text
command queue
mock command effects
verification events
world-state mutation
```

Acceptance criteria:

```text
Executor consumes command:requests.
Executor updates commands and world state.
Executor emits command.started, command.succeeded, and verification.completed.
Active patch reaches verified state.
```

### Phase 8: Polish

Build:

```text
scenario reset
demo seed data
better logs
WebSocket reconnect stability
frontend-friendly payloads
```

Acceptance criteria:

```text
POST /simulator/reset returns the demo to T+00:00.
The UI can run the same demo repeatedly.
No manual database cleanup is needed.
```

## 26. Minimal Docker Compose

```yaml
services:
  orbitops-api:
    build: ./backend
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://orbitops:orbitops@postgres:5432/orbitops
      REDIS_URL: redis://redis:6379/0
      CRUSOE_API_KEY: ${CRUSOE_API_KEY:-}
      CRUSOE_BASE_URL: https://api.inference.crusoecloud.com/v1/
      CRUSOE_MODEL: deepseek-ai/Deepseek-V4-Flash
      CRUSOE_ENABLED: ${CRUSOE_ENABLED:-false}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  orbitops-simulator:
    build: ./backend
    command: python -m app.simulator.telemetry_generator
    environment:
      DATABASE_URL: postgresql+asyncpg://orbitops:orbitops@postgres:5432/orbitops
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  orbitops-agents:
    build: ./backend
    command: python -m app.agents.runner
    environment:
      DATABASE_URL: postgresql+asyncpg://orbitops:orbitops@postgres:5432/orbitops
      REDIS_URL: redis://redis:6379/0
      CRUSOE_API_KEY: ${CRUSOE_API_KEY:-}
      CRUSOE_BASE_URL: https://api.inference.crusoecloud.com/v1/
      CRUSOE_MODEL: deepseek-ai/Deepseek-V4-Flash
      CRUSOE_ENABLED: ${CRUSOE_ENABLED:-false}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  orbitops-executor:
    build: ./backend
    command: python -m app.services.command_executor
    environment:
      DATABASE_URL: postgresql+asyncpg://orbitops:orbitops@postgres:5432/orbitops
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: orbitops
      POSTGRES_PASSWORD: orbitops
      POSTGRES_DB: orbitops
    ports:
      - "5432:5432"
    volumes:
      - orbitops_pg:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U orbitops -d orbitops"]
      interval: 5s
      timeout: 5s
      retries: 12

  redis:
    image: redis:7
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 12

volumes:
  orbitops_pg:
```

## 27. Immediate Next Step

Start implementation with Phase 1 only.

Do not build all agents first. Build the backend skeleton and one static seeded world state, then add simulator ticks, then add agents.

First pull request target:

```text
docker compose up
GET /health
alembic upgrade head
GET /world-state
WS /ws/live
backend folder structure
SQLAlchemy ORM models
seed world state
```

## 28. External References

Use these references when implementing:

- FastAPI WebSockets: https://fastapi.tiangolo.com/advanced/websockets/
- Redis Streams: https://redis.io/docs/latest/develop/data-types/streams/
- PostgreSQL JSON types: https://www.postgresql.org/docs/current/datatype-json.html
- Docker Compose: https://docs.docker.com/compose/
- Crusoe Managed Inference local reference: `../CRUSOE.md`
- NASA SmallSat power guidance: https://www.nasa.gov/smallsat-institute/sst-soa/power-subsystems/
- NASA SmallSat thermal guidance: https://www.nasa.gov/smallsat-institute/sst-soa/thermal-control/
- ESA space radiation overview: https://www.esa.int/Enabling_Support/Space_Engineering_Technology/Swarm_vs._space_radiation_the_first_10_years
- NASA radiation effects reference: https://ntrs.nasa.gov/citations/19890014178
