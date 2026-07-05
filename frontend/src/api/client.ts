import type {
  ActiveMissionPatchResponse,
  AgentsStatusResponse,
  CommandsResponse,
  IncidentsResponse,
  MissionPatch,
  OrbitalOpsTelemetryResponse,
  WorldStateResponse,
} from "../types/backend";

const API_BASE_URL = import.meta.env?.VITE_API_BASE_URL ?? "";

function apiUrl(path: string): string {
  if (!API_BASE_URL) {
    return path;
  }
  return `${API_BASE_URL.replace(/\/$/, "")}${path}`;
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`${init?.method ?? "GET"} ${path} failed with ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function getWorldState(): Promise<WorldStateResponse> {
  return fetchJson<WorldStateResponse>("/world-state");
}

export function getTelemetrySnapshot(): Promise<OrbitalOpsTelemetryResponse> {
  return fetchJson<OrbitalOpsTelemetryResponse>("/api/telemetry");
}

export function getAgentsStatus(): Promise<AgentsStatusResponse> {
  return fetchJson<AgentsStatusResponse>("/agents/status");
}

export function getCommands(): Promise<CommandsResponse> {
  return fetchJson<CommandsResponse>("/commands");
}

export function getIncidents(): Promise<IncidentsResponse> {
  return fetchJson<IncidentsResponse>("/incidents");
}

export function getActiveMissionPatch(): Promise<ActiveMissionPatchResponse> {
  return fetchJson<ActiveMissionPatchResponse>("/mission-patches/active");
}

export async function approveMissionPatch(patchId: string): Promise<MissionPatch> {
  const response = await fetchJson<{ mission_patch: MissionPatch }>(`/mission-patches/${patchId}/approve`, {
    method: "POST",
    body: JSON.stringify({
      operator_id: "demo-operator",
      operator_note: "Approved from OrbitOps frontend",
    }),
  });

  return response.mission_patch;
}