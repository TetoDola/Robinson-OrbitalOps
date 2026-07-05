import type { ChatMessage, EvidenceId, PatchDecision } from "../../lib/agentBriefing";
import { splitMessageParts } from "../../lib/chatMentions";
import ChatEvidencePanel from "./ChatEvidencePanel";
import ChatPatchCard from "./ChatPatchCard";

interface ChatMessageViewProps {
  msg: ChatMessage;
  labels: string[];
  expandedEvidence: EvidenceId | null;
  patchStatuses: Record<string, PatchDecision>;
  onToggleEvidence: (id: EvidenceId) => void;
  onApprovePatch: (patchId: string) => void;
  onRejectPatch: (patchId: string) => void;
  onOpenConsole: () => void;
}

function AgentBlocks({
  blocks,
  expandedEvidence,
  onToggleEvidence,
}: {
  blocks: NonNullable<ChatMessage["blocks"]>;
  expandedEvidence: EvidenceId | null;
  onToggleEvidence: (id: EvidenceId) => void;
}) {
  const activeInMessage = blocks.some((b) => b.kind === "evidence" && b.id === expandedEvidence);

  return (
    <>
      <div className="chat-bubble chat-bubble-agent">
        {blocks.map((block, index) =>
          block.kind === "text" ? (
            <span key={`t-${index}`}>{block.value}</span>
          ) : (
            <button
              key={`e-${block.id}-${index}`}
              className={`chat-evidence-link${expandedEvidence === block.id ? " is-open" : ""}`}
              onClick={() => onToggleEvidence(block.id)}
              type="button"
            >
              {block.label}
            </button>
          ),
        )}
      </div>
      {activeInMessage && expandedEvidence ? <ChatEvidencePanel id={expandedEvidence} /> : null}
    </>
  );
}

export default function ChatMessageView({
  msg,
  labels,
  expandedEvidence,
  patchStatuses,
  onToggleEvidence,
  onApprovePatch,
  onRejectPatch,
  onOpenConsole,
}: ChatMessageViewProps) {
  if (msg.role === "system") {
    return (
      <div className="chat-row chat-row-system">
        <p className="chat-system-msg">{msg.text}</p>
      </div>
    );
  }

  if (msg.role === "user") {
    const parts = splitMessageParts(msg.text ?? "", labels);
    return (
      <div className="chat-row chat-row-user">
        <div className="chat-bubble chat-bubble-user">
          {parts.map((part, index) =>
            part.type === "mention" ? (
              <span className="chat-mention" key={`${index}-${part.value}`}>
                {part.value}
              </span>
            ) : (
              <span key={`${index}-${part.value}`}>{part.value}</span>
            ),
          )}
        </div>
      </div>
    );
  }

  const patchStatus = msg.patchId ? (patchStatuses[msg.patchId] ?? "pending") : "pending";

  return (
    <div className="chat-row chat-row-agent">
      {msg.author ? <span className="chat-author">{msg.author}</span> : null}
      {msg.blocks ? (
        <AgentBlocks
          blocks={msg.blocks}
          expandedEvidence={expandedEvidence}
          onToggleEvidence={onToggleEvidence}
        />
      ) : (
        <div className="chat-bubble chat-bubble-agent">{msg.text}</div>
      )}
      {msg.patchId ? (
        <ChatPatchCard
          patchId={msg.patchId}
          status={patchStatus}
          onApprove={() => onApprovePatch(msg.patchId!)}
          onReject={() => onRejectPatch(msg.patchId!)}
          onOpenConsole={onOpenConsole}
        />
      ) : null}
    </div>
  );
}
