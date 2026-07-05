import { useState } from "react";

import MissionPatchPanel from "./MissionPatchPanel";
import OpsSpine from "./OpsSpine";
import SceneViewport from "./SceneViewport";
import VitalsStrip from "./VitalsStrip";
import { useWorldStore } from "../store/worldStore";

export default function AssetConsole() {
  const [open, setOpen] = useState(false);
  const patchMode = useWorldStore((s) => s.patchMode);
  const missionPatch = useWorldStore((s) => s.missionPatch);
  const demoResetAt = useWorldStore((s) => s.demoResetAt);
  const pending = !(demoResetAt && !missionPatch) && patchMode === "pending";

  return (
    <div className="asset-console layout-drawer">
      <OpsSpine />
      <div className="stage">
        <SceneViewport />
        <VitalsStrip />
        <aside className={`drawer${open ? " open" : ""}`} aria-label="Agents and decision">
          <button
            className={`drawer-tab${pending && !open ? " alert" : ""}`}
            onClick={() => setOpen((o) => !o)}
            type="button"
            aria-expanded={open}
          >
            {open ? "close ▸" : "◂ decide"}
          </button>
          <div className="drawer-body">
            <MissionPatchPanel />
          </div>
        </aside>
      </div>
    </div>
  );
}
