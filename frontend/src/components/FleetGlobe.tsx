import { useEffect, useRef } from "react";

import { useAppStore } from "../store/appStore";
import { createFleetGlobe, type FleetGlobe as FleetScene } from "../scene/fleetGlobe";

export default function FleetGlobe() {
  const ref = useRef<HTMLDivElement | null>(null);
  const sceneRef = useRef<FleetScene | null>(null);
  const openFleetChat = useAppStore((s) => s.openFleetChat);
  const fleetChatAssetId = useAppStore((s) => s.fleetChatAssetId);

  useEffect(() => {
    if (!ref.current) return undefined;
    const scene = createFleetGlobe(ref.current, { onAssetClick: openFleetChat });
    sceneRef.current = scene;
    scene.start();
    return () => {
      scene.destroy();
      sceneRef.current = null;
    };
  }, [openFleetChat]);

  useEffect(() => {
    sceneRef.current?.focusAsset(fleetChatAssetId);
  }, [fleetChatAssetId]);

  return <div className="fleet-scene" ref={ref} aria-label="Fleet constellation" />;
}
