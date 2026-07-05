import { useEffect, useMemo, useState } from "react";

import { fleetIrTarget } from "../fleet/fleetData";
import { useAppStore } from "../store/appStore";
import IRCamPopup from "./IRCamPopup";

const CHAT_WIDTH_RATIO = 2 / 3;

export default function FleetThermalIr() {
  const assetId = useAppStore((s) => s.fleetChatAssetId);
  const [open, setOpen] = useState(false);

  const target = assetId ? fleetIrTarget(assetId) : null;

  useEffect(() => {
    setOpen(Boolean(target));
  }, [assetId, target?.id]);

  const anchor = useMemo(() => {
    const chatW = window.innerWidth * CHAT_WIDTH_RATIO;
    return {
      x: window.innerWidth - chatW,
      y: window.innerHeight * 0.38,
    };
  }, [assetId]);

  if (!open || !target) {
    return null;
  }

  return (
    <IRCamPopup
      className="fleet-ir-popup"
      anchor={anchor}
      node={target}
      onClose={() => setOpen(false)}
    />
  );
}
