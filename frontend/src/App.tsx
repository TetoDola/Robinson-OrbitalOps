import { useEffect } from "react";

import {
  getActiveMissionPatch,
  getCommands,
  getTelemetrySnapshot,
  getWorldState,
} from "./api/client";
import { connectLiveSocket } from "./api/liveSocket";
import AssetConsole from "./components/AssetConsole";
import CommandBar from "./components/CommandBar";
import FleetView from "./components/FleetView";
import { useAppStore } from "./store/appStore";
import { useWorldStore } from "./store/worldStore";

export default function App() {
  useEffect(() => {
    const store = useWorldStore.getState();

    void Promise.allSettled([
      getWorldState(),
      getCommands(),
      getActiveMissionPatch(),
    ]).then(([worldResult, commandsResult, patchResult]) => {
      if (worldResult.status === "fulfilled") {
        store.setWorldState(
          worldResult.value.state,
          worldResult.value.version,
          worldResult.value.scenario_run_id,
        );
      }
      if (commandsResult.status === "fulfilled") {
        store.setCommands(commandsResult.value.commands);
      }
      if (patchResult.status === "fulfilled") {
        store.setMissionPatch(patchResult.value.mission_patch);
      }
    });

    const updateRadiationRisk = () => {
      void getTelemetrySnapshot()
        .then((snapshot) => {
          const activeSatelliteId = snapshot.mission?.activeSatelliteId;
          const satellite =
            snapshot.satellites.find((item) => item.id === activeSatelliteId) ??
            snapshot.satellites[0];
          store.setRadiationRisk(satellite?.radiationRisk ?? null);
        })
        .catch(() => {
          store.setRadiationRisk(null);
        });
    };
    updateRadiationRisk();
    const radiationPoll = window.setInterval(updateRadiationRisk, 60000);

    const disconnectLiveSocket = connectLiveSocket();
    return () => {
      window.clearInterval(radiationPoll);
      disconnectLiveSocket();
    };
  }, []);

  const view = useAppStore((state) => state.view);

  return (
    <div className="app-shell">
      <CommandBar />
      <div className="view">{view === "fleet" ? <FleetView /> : <AssetConsole />}</div>
    </div>
  );
}
