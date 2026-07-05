import type {
  ActiveMissionPatchResponse,
  AiStatusResponse,
  AgentFindingsResponse,
  AgentsRuntimeResponse,
  AgentsStatusResponse,
  ChatTurn,
  CommandsResponse,
  IncidentsResponse,
  MissionPatch,
  OperatorChatResponse,
  RadiationRiskResponse,
  SimulatorInjectRequest,
  SimulatorInjectResponse,
  WorldStateResponse,
} from "../types/backend";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

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

export function getRadiationRisk(): Promise<RadiationRiskResponse> {
  return fetchJson<RadiationRiskResponse>("/radiation-risk");
}

export function getAgentsStatus(): Promise<AgentsStatusResponse> {
  return fetchJson<AgentsStatusResponse>("/agents/status");
}

export function getAgentsRuntime(): Promise<AgentsRuntimeResponse> {
  return fetchJson<AgentsRuntimeResponse>("/agents/runtime");
}

export function getAiStatus(): Promise<AiStatusResponse> {
  return fetchJson<AiStatusResponse>("/agents/ai-status");
}

export function sendChatMessage(message: string, history: ChatTurn[] = []): Promise<OperatorChatResponse> {
  return fetchJson<OperatorChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({ message, history }),
  });
}

export function getAgentFindings(): Promise<AgentFindingsResponse> {
  return fetchJson<AgentFindingsResponse>("/agents/findings");
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

export interface LocalToolCall {
  tool: string;
  action: string;
  command?: string;
  reason?: string;
}

export interface LocalToolResult {
  ok: boolean;
  action?: string;
  stdout?: string;
  stderr?: string;
  error?: string;
}

export interface MissionPatchDecision {
  patch: MissionPatch;
  localToolCalls: LocalToolCall[];
}

export async function approveMissionPatch(patchId: string): Promise<MissionPatchDecision> {
  const response = await fetchJson<{ mission_patch: MissionPatch; local_tool_calls?: LocalToolCall[] }>(
    `/mission-patches/${patchId}/approve`,
    {
      method: "POST",
      body: JSON.stringify({
        operator_id: "demo-operator",
        operator_note: "Approved from Robinson frontend",
      }),
    },
  );

  return { patch: response.mission_patch, localToolCalls: response.local_tool_calls ?? [] };
}

export async function rejectMissionPatch(patchId: string): Promise<MissionPatchDecision> {
  const response = await fetchJson<{ mission_patch: MissionPatch; local_tool_calls?: LocalToolCall[] }>(
    `/mission-patches/${patchId}/reject`,
    {
      method: "POST",
      body: JSON.stringify({
        operator_id: "demo-operator",
        operator_note: "Rejected from Robinson frontend",
      }),
    },
  );

  return { patch: response.mission_patch, localToolCalls: response.local_tool_calls ?? [] };
}

// Local tool calls run on the operator's machine via the Vite dev-server
// endpoint (see localCoolerBoostPlugin in vite.config.ts) because the
// containerized backend cannot touch demo hardware.
export async function runLocalToolCall(call: LocalToolCall): Promise<LocalToolResult> {
  if (call.tool !== "cooler_boost") {
    return { ok: false, error: `Unknown local tool: ${call.tool}` };
  }
  try {
    const response = await fetch("/__local/cooler-boost", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: call.action }),
    });
    return (await response.json()) as LocalToolResult;
  } catch {
    return { ok: false, error: "Local tool endpoint unreachable (only available under the Vite dev server)." };
  }
}

export function injectSimulatorIssue(issue: string, payload: SimulatorInjectRequest = {}): Promise<SimulatorInjectResponse> {
  return fetchJson<SimulatorInjectResponse>(`/simulator/inject/${issue}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
