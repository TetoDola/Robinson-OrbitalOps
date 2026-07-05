import { FLEET, FLEET_QUEUE } from "../../fleet/fleetData";
import type { PatchDecision } from "../../lib/agentBriefing";

interface ChatPatchCardProps {
  patchId: string;
  status: PatchDecision;
  onApprove: () => void;
  onReject: () => void;
  onOpenConsole: () => void;
}

export default function ChatPatchCard({
  patchId,
  status,
  onApprove,
  onReject,
  onOpenConsole,
}: ChatPatchCardProps) {
  const patch = FLEET_QUEUE.find((p) => p.id === patchId);
  if (!patch) return null;

  const asset = FLEET.find((a) => a.id === patch.asset);
  const resolved = status !== "pending";

  return (
    <div className={`chat-patch-card is-${patch.severity}${resolved ? ` is-${status}` : ""}`}>
      <div className="chat-patch-head">
        <span className="chat-patch-kicker">Mission Patch</span>
        <strong>{patch.label}</strong>
      </div>
      <p className="chat-patch-detail">{patch.detail}</p>
      <div className="chat-patch-meta">
        {asset?.eclipseMin != null ? <span>{asset.eclipseMin} min to eclipse</span> : null}
        {asset?.battery != null ? <span>Battery {asset.battery}%</span> : null}
        {!resolved ? <span className="chat-patch-badge">Requires approval</span> : null}
      </div>
      {status === "approved" ? (
        <p className="chat-patch-status is-approved">Approved — queued for execution</p>
      ) : status === "rejected" ? (
        <p className="chat-patch-status is-rejected">Rejected — agents standing by</p>
      ) : (
        <div className="chat-patch-actions">
          <button className="chat-patch-btn is-primary" onClick={onApprove} type="button">
            Approve
          </button>
          <button className="chat-patch-btn" onClick={onReject} type="button">
            Reject
          </button>
          <button className="chat-patch-btn is-ghost" onClick={onOpenConsole} type="button">
            Open console
          </button>
        </div>
      )}
    </div>
  );
}
