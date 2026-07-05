# AstroOps Live Architecture

AstroOps Live is a human-in-the-loop operations agent. The UI is not the product by itself; the product is the loop from live state to prediction to recommended action to operator decision.

## Backend Modules

- `app/models.py`: Pydantic schemas for telemetry, racks, GPUs, jobs, risks, actions, advisories, overrides, and UI state.
- `app/simulator.py`: deterministic GPU cluster simulator and scenario progression.
- `app/risk_engine.py`: Python-only scoring, slopes, ETAs, forecasts, and findings.
- `app/action_generator.py`: deterministic candidate remediation actions.
- `app/advisory_agent.py`: Crusoe structured recommendation path plus fallback.
- `app/crusoe_client.py`: exact Crusoe endpoint, model strings, and reasoning-disable flags.
- `app/action_executor.py`: applies accepted action effects to the simulation.
- `app/state.py`: in-memory runtime state.
- `app/main.py`: FastAPI endpoints and SSE.

## Frontend Modules

- `ClusterMap`: rack-level risk, thermal, power, and capacity view.
- `SituationalModel`: top findings, risk forecast, ETAs, and domain risk scores.
- `AgentRecommendation`: selected action, impact estimate, evidence, Accept, Ask Why, Override.
- `CandidateActions`: actions considered by the agent.
- `OutcomeTimeline`: accepted actions and overrides.
- `LiveFeed`: streaming telemetry feed.
- `CrusoeStatus`: real vs mock mode indicator.

## Request Flow

```mermaid
sequenceDiagram
  participant UI as React UI
  participant API as FastAPI
  participant Sim as Simulator
  participant Risk as Risk Engine
  participant Acts as Action Generator
  participant C as Crusoe

  UI->>API: POST /api/tick
  API->>Sim: advance_cluster()
  API->>Risk: analyze_cluster()
  API->>Acts: generate_candidate_actions()
  API-->>UI: UIState
  UI->>API: POST /api/recommend
  API->>C: Nemotron Ultra structured advisory
  C-->>API: AgentRecommendation
  API-->>UI: UIState with recommendation
  UI->>API: POST /api/actions/{id}/accept
  API->>Sim: apply accepted action
  API->>Risk: recompute risk
  API-->>UI: updated state and timeline
```

## Risk Engine

The LLM does not calculate slopes, ETAs, or raw scores. Python computes:

- `thermal_risk`
- `cooling_risk`
- `power_risk`
- `queue_sla_risk`
- `network_risk`
- `gpu_health_risk`
- `memory_risk`
- `storage_risk`
- `placement_risk`
- `inference_service_risk`
- `operator_policy_risk`
- `cascade_risk`

Composite risk uses weighted scoring plus a cascade bonus when multiple domains exceed 70/100.

## Crusoe Integration

Crusoe is called only for high-value reasoning moments:

- high/critical recommendation generation
- Ask Why explanation
- optional operator chat

The structured advisory path uses `nvidia/NVIDIA-Nemotron-3-Ultra-550B` with thinking disabled for Pydantic parsing. If Crusoe is unavailable, the deterministic local advisor returns a clearly marked mock/fallback advisory.
