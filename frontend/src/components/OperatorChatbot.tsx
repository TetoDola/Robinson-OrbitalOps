import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";

import { sendChatMessage } from "../api/client";
import { useWorldStore } from "../store/worldStore";
import type { ChatTurn, OperatorChatResponse } from "../types/backend";
import { IRCameraCanvas, type IrNodeTarget } from "./IRCamPopup";

interface ChatMessage extends ChatTurn {
  id: string;
  source?: OperatorChatResponse["source"];
  model?: string | null;
  visual?: "ir";
}

const SUGGESTIONS = [
  "Which agent is most critical?",
  "Explain the eclipse risk",
  "Show IR camera",
  "Summarize the active patch",
];

function makeMessage(role: ChatTurn["role"], content: string, meta: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    role,
    content,
    ...meta,
  };
}

function humanize(value: string | null | undefined): string {
  return value ? value.replace(/[_-]+/g, " ") : "unknown";
}

function wantsIrPreview(value: string): boolean {
  return /\b(ir|thermal|hotspot|camera|temperature|temp|cooling|b200)\b/i.test(value);
}

export default function OperatorChatbot() {
  const aiStatus = useWorldStore((state) => state.aiStatus);
  const agentCount = useWorldStore((state) => state.agents.length);
  const openFindings = useWorldStore((state) => state.agentFindings.filter((finding) => finding.status === "open").length);
  const missionPatch = useWorldStore((state) => state.missionPatch);
  const worldState = useWorldStore((state) => state.worldState);
  const [isOpen, setIsOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([
    makeMessage(
      "assistant",
      "Ask about current agents, mission patch status, orbit, radiation, downlink, or thermal risk.",
      { source: "deterministic" },
    ),
  ]);
  const logRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const latestThermalInput = worldState?.thermal.latest_visual_input ?? null;
  const preferredNodeId =
    latestThermalInput?.asset_id ??
    (worldState?.thermal.hotspot_node && worldState.thermal.hotspot_node !== "none"
      ? worldState.thermal.hotspot_node
      : "node-c");
  const thermalNode = worldState?.nodes.find((node) => node.id === preferredNodeId);
  const irNode: IrNodeTarget = {
    id: preferredNodeId,
    status: thermalNode?.status ?? worldState?.thermal.cooling_status ?? "simulated",
    tempC: thermalNode?.temp_c ?? worldState?.thermal.highest_temp_c ?? 91,
  };

  const statusLabel = useMemo(() => {
    if (aiStatus?.connected) return `${aiStatus.provider} connected`;
    if (aiStatus?.enabled && !aiStatus.configured) return "missing API key";
    return "deterministic fallback";
  }, [aiStatus]);

  useEffect(() => {
    if (!isOpen) return;
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [isOpen, messages.length, isSending]);

  useEffect(() => {
    if (isOpen) {
      window.setTimeout(() => inputRef.current?.focus(), 80);
    }
  }, [isOpen]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || isSending) return;

    const history = messages.slice(-10).map(({ role, content }) => ({ role, content }));
    const userMessage = makeMessage("user", trimmed);
    setMessages((current) => [...current, userMessage]);
    setDraft("");
    setError(null);
    setIsSending(true);

    try {
      const response = await sendChatMessage(trimmed, history);
      setMessages((current) => [
        ...current,
        makeMessage("assistant", response.message.content, {
          source: response.source,
          model: response.model,
          visual: wantsIrPreview(trimmed) || wantsIrPreview(response.message.content) ? "ir" : undefined,
        }),
      ]);
    } catch {
      setError("Chat backend is unavailable.");
      setMessages((current) => [
        ...current,
        makeMessage("assistant", "I cannot reach the backend chat endpoint right now. Check that the API container is running.", {
          visual: wantsIrPreview(trimmed) ? "ir" : undefined,
        }),
      ]);
    } finally {
      setIsSending(false);
    }
  }

  function onInputKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void send(draft);
    }
  }

  return (
    <div className="operator-chat-root">
      {isOpen ? (
        <section className="operator-chat-panel" aria-label="Operator chatbot">
          <header className="operator-chat-header">
            <div>
              <span className="eyebrow">operator chat</span>
              <strong>Robinson assistant</strong>
              <small>{statusLabel}</small>
            </div>
            <button className="operator-chat-close" type="button" aria-label="Close operator chat" onClick={() => setIsOpen(false)}>
              x
            </button>
          </header>

          <div className="operator-chat-context" aria-label="Current chat context">
            <span>{agentCount} agents</span>
            <span>{openFindings} open findings</span>
            <span>{missionPatch ? humanize(missionPatch.status) : "no active patch"}</span>
          </div>

          <div className="operator-chat-log" ref={logRef}>
            {messages.map((message) => (
              <article className={`operator-chat-message is-${message.role}`} key={message.id}>
                <div className="operator-chat-bubble">
                  <p>{message.content}</p>
                  {message.role === "assistant" && message.source ? (
                    <small>{message.source === "crusoe" ? message.model ?? "crusoe" : "deterministic"}</small>
                  ) : null}
                </div>
                {message.visual === "ir" ? (
                  <div className="operator-chat-ir-card" aria-label={`Simulated IR camera for ${irNode.id}`}>
                    <div className="operator-chat-ir-head">
                      <span>IR camera</span>
                      <strong>{humanize(irNode.id)}</strong>
                    </div>
                    <IRCameraCanvas
                      className="operator-chat-ir-canvas"
                      node={irNode}
                      sourceImageUrl={latestThermalInput?.image_data_url}
                    />
                    <div className="operator-chat-ir-meta">
                      <span>{latestThermalInput?.source ?? "b200.png simulation"}</span>
                      <span>{irNode.tempC.toFixed(1)}&deg;C max</span>
                    </div>
                  </div>
                ) : null}
              </article>
            ))}
            {isSending ? (
              <article className="operator-chat-message is-assistant">
                <div className="operator-chat-bubble is-pending">
                  <p>Reading backend context...</p>
                </div>
              </article>
            ) : null}
          </div>

          <div className="operator-chat-suggestions" aria-label="Suggested prompts">
            {SUGGESTIONS.map((suggestion) => (
              <button key={suggestion} type="button" onClick={() => void send(suggestion)} disabled={isSending}>
                {suggestion}
              </button>
            ))}
          </div>

          <form
            className="operator-chat-compose"
            onSubmit={(event) => {
              event.preventDefault();
              void send(draft);
            }}
          >
            <textarea
              ref={inputRef}
              aria-label="Message Robinson assistant"
              placeholder="Ask a mission question..."
              rows={2}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={onInputKeyDown}
            />
            <button type="submit" disabled={!draft.trim() || isSending} aria-label="Send chat message">
              &gt;
            </button>
          </form>
          {error ? <div className="operator-chat-error">{error}</div> : null}
        </section>
      ) : (
        <button className="operator-chat-launcher" type="button" onClick={() => setIsOpen(true)} aria-label="Open operator chat">
          AI
        </button>
      )}
    </div>
  );
}
