import { useEffect } from "react";

import {
  getActiveMissionPatch,
  getAiStatus,
  getAgentFindings,
  getAgentsRuntime,
  getAgentsStatus,
  getCommands,
  getIncidents,
  getRadiationRisk,
  getWorldState,
} from "./api/client";
import { connectLiveSocket } from "./api/liveSocket";
import MissionPatchPanel from "./components/MissionPatchPanel";
import OperatorChatbot from "./components/OperatorChatbot";
import SceneViewport from "./components/SceneViewport";
import TelemetryPanel from "./components/TelemetryPanel";
import { useWorldStore } from "./store/worldStore";

export default function App() {
  useEffect(() => {
    const store = useWorldStore.getState();

    void Promise.allSettled([
      getWorldState(),
      getAgentsStatus(),
      getAgentsRuntime(),
      getAiStatus(),
      getAgentFindings(),
      getCommands(),
      getIncidents(),
      getActiveMissionPatch(),
    ]).then(([worldResult, agentsResult, runtimeResult, aiResult, findingsResult, commandsResult, incidentsResult, patchResult]) => {
      if (worldResult.status === "fulfilled") {
        store.setWorldState(
          worldResult.value.state,
          worldResult.value.version,
          worldResult.value.scenario_run_id,
        );
      }
      if (agentsResult.status === "fulfilled") {
        store.setAgents(agentsResult.value.agents);
      }
      if (runtimeResult.status === "fulfilled") {
        store.setAgentRuntime(runtimeResult.value.agents);
      }
      if (aiResult.status === "fulfilled") {
        store.setAiStatus(aiResult.value);
      }
      if (findingsResult.status === "fulfilled") {
        store.setAgentFindings(findingsResult.value.findings);
      }
      if (commandsResult.status === "fulfilled") {
        store.setCommands(commandsResult.value.commands);
      }
      if (incidentsResult.status === "fulfilled") {
        store.setIncidents(incidentsResult.value.incidents);
      }
      if (patchResult.status === "fulfilled") {
        store.setMissionPatch(patchResult.value.mission_patch);
      }
    });

    const updateRadiationRisk = () => {
      void getRadiationRisk()
        .then((response) => {
          store.setRadiationRisk(response.radiationRisk);
        })
        .catch(() => {
          store.setRadiationRisk(null);
        });
    };
    updateRadiationRisk();
    const radiationPoll = window.setInterval(updateRadiationRisk, 60000);

    // Runtime data (next heartbeat countdown, run state) has no websocket
    // event, so refresh it on the backend's heartbeat cadence.
    const agentPoll = window.setInterval(() => {
      void getAgentsStatus()
        .then((response) => store.setAgents(response.agents))
        .catch(() => {});
      void getAgentsRuntime()
        .then((response) => store.setAgentRuntime(response.agents))
        .catch(() => {});
    }, 10000);

    const disconnectLiveSocket = connectLiveSocket();
    return () => {
      window.clearInterval(radiationPoll);
      window.clearInterval(agentPoll);
      disconnectLiveSocket();
    };
  }, []);

  return (
    <div className="app-shell">
      <TelemetryPanel />
      <SceneViewport />
      <MissionPatchPanel />
      <OperatorChatbot />
    </div>
  );
}
