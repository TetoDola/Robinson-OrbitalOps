import type { EvidenceId } from "../../lib/agentBriefing";
import InlineIrCanvas from "./InlineIrCanvas";

interface ChatEvidencePanelProps {
  id: EvidenceId;
}

export default function ChatEvidencePanel({ id }: ChatEvidencePanelProps) {
  if (id === "node-c-ir") {
    return (
      <div className="chat-evidence-panel chat-evidence-thermal">
        <div className="chat-evidence-head">
          <span className="chat-evidence-kicker">IR-01 · live</span>
          <strong>Node C · B200 SXM</strong>
        </div>
        <InlineIrCanvas tempC={96.4} />
        <p className="chat-evidence-caption">Hotspot confirmed while idle — rack telemetry agrees.</p>
      </div>
    );
  }

  if (id === "ckpt-lineage") {
    return (
      <div className="chat-evidence-panel chat-evidence-ckpt">
        <div className="chat-evidence-head">
          <span className="chat-evidence-kicker">Checkpoint lineage</span>
          <strong>ckpt-184900 suspect</strong>
        </div>
        <ol className="chat-ckpt-chain">
          <li className="is-good">
            <span>ckpt-184500</span>
            <b>rollback target</b>
          </li>
          <li className="is-warn">
            <span>ckpt-184720</span>
            <b>ECC rising</b>
          </li>
          <li className="is-bad">
            <span>ckpt-184900</span>
            <b>suspect · NaN loss</b>
          </li>
        </ol>
        <p className="chat-evidence-caption">Integrity Agent flagged after GPU 3 ECC spike on Node B.</p>
      </div>
    );
  }

  return (
    <div className="chat-evidence-panel chat-evidence-downlink">
      <div className="chat-evidence-head">
        <span className="chat-evidence-kicker">Ground pass · T+8 min</span>
        <strong>Downlink window</strong>
      </div>
      <div className="chat-downlink-bar" aria-label="18 of 180 GB">
        <div className="chat-downlink-fill" style={{ width: "10%" }} />
      </div>
      <div className="chat-downlink-labels">
        <span>18 GB available</span>
        <span>180 GB required</span>
      </div>
      <p className="chat-evidence-caption">Full checkpoint cannot ship — delta + manifest only.</p>
    </div>
  );
}
