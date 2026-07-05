import { useEffect, useState } from "react";

import { fleetAlerts, problemTitle } from "../fleet/fleetData";
import { useAppStore } from "../store/appStore";

const ALERT_DELAY_MS = 20_000;

export default function FleetAlerts() {
  const openFleetChat = useAppStore((s) => s.openFleetChat);
  const activeId = useAppStore((s) => s.fleetChatAssetId);
  const [visible, setVisible] = useState(false);

  const alerts = fleetAlerts();
  const asset = alerts[0] ?? null;

  useEffect(() => {
    if (!asset) {
      setVisible(false);
      return undefined;
    }

    setVisible(false);
    const timer = window.setTimeout(() => setVisible(true), ALERT_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [asset?.id]);

  if (!asset || !visible) return null;

  return (
    <div className="fleet-alerts is-visible" aria-label="Datacenter alert" aria-live="polite">
      <button
        type="button"
        className={`fleet-alert is-${asset.health}${asset.id === activeId ? " is-active" : ""}`}
        onClick={() => openFleetChat(asset.id)}
      >
        <span className="fleet-alert-id">{asset.id}</span>
        <span className="fleet-alert-sep" aria-hidden="true">
          ·
        </span>
        <span className="fleet-alert-problem">{problemTitle(asset.note)}</span>
      </button>
    </div>
  );
}
