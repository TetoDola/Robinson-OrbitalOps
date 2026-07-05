import MissionPatchPanel from "./MissionPatchPanel";
import OpsSpine from "./OpsSpine";
import SceneViewport from "./SceneViewport";
import TelemetryPanel from "./TelemetryPanel";

export default function AssetConsole() {
  return (
    <div className="asset-console">
      <OpsSpine />
      <TelemetryPanel />
      <SceneViewport />
      <MissionPatchPanel />
    </div>
  );
}
