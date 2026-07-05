import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";

import ChatMessageView from "./chat/ChatMessageView";
import {
  buildAgentBriefing,
  mockAgentReply,
  SUGGESTION_CHIPS,
  systemMessage,
  type ChatMessage,
  type EvidenceId,
  type PatchDecision,
} from "../lib/agentBriefing";
import {
  filterMentionCandidates,
  getActiveMentionQuery,
  insertMention,
  mentionLabels,
  mentionRoster,
  type MentionCandidate,
} from "../lib/chatMentions";
import { useAppStore } from "../store/appStore";
import { useWorldStore } from "../store/worldStore";
import { FLEET } from "../fleet/fleetData";

function formatUtcTime(): string {
  return new Date().toISOString().slice(11, 19);
}

export default function FleetAgentChat() {
  const assetId = useAppStore((s) => s.fleetChatAssetId);
  const closeFleetChat = useAppStore((s) => s.closeFleetChat);
  const openAsset = useAppStore((s) => s.openAsset);
  const agents = useWorldStore((s) => s.agents);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [cursor, setCursor] = useState(0);
  const [mentionIndex, setMentionIndex] = useState(0);
  const [visible, setVisible] = useState(false);
  const [expandedEvidence, setExpandedEvidence] = useState<EvidenceId | null>(null);
  const [patchStatuses, setPatchStatuses] = useState<Record<string, PatchDecision>>({});
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const roster = useMemo(() => mentionRoster(agents), [agents]);
  const labels = useMemo(() => mentionLabels(agents), [agents]);
  const activeMention = getActiveMentionQuery(draft, cursor);
  const mentionCandidates = activeMention ? filterMentionCandidates(roster, activeMention.query) : [];
  const mentionOpen = Boolean(activeMention && mentionCandidates.length > 0);

  useEffect(() => {
    if (!assetId) {
      setVisible(false);
      return undefined;
    }

    const state = useWorldStore.getState();
    const briefing = buildAgentBriefing(assetId, state.agents, state.telemetry);
    setMessages([]);
    setDraft("");
    setCursor(0);
    setMentionIndex(0);
    setExpandedEvidence(null);
    setPatchStatuses({});
    requestAnimationFrame(() => setVisible(true));

    let index = 0;
    const timers: number[] = [];

    const revealNext = () => {
      if (index >= briefing.length) return;
      const msg = briefing[index]!;
      setMessages((prev) => [...prev, msg]);
      index += 1;
      if (index < briefing.length) {
        const delay = briefing[index]!.delayMs ?? 800;
        timers.push(window.setTimeout(revealNext, delay));
      }
    };

    revealNext();

    return () => {
      timers.forEach((t) => window.clearTimeout(t));
    };
  }, [assetId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, messages[messages.length - 1]?.id]);

  useEffect(() => {
    setMentionIndex(0);
  }, [activeMention?.query, mentionCandidates.length]);

  if (!assetId) return null;

  const asset = FLEET.find((a) => a.id === assetId);

  function syncCursor() {
    const input = inputRef.current;
    if (input) {
      setCursor(input.selectionStart ?? draft.length);
    }
  }

  function applyMention(candidate: MentionCandidate) {
    if (!activeMention) return;
    const { next, nextCursor } = insertMention(draft, activeMention.start, cursor, candidate.label);
    setDraft(next);
    setCursor(nextCursor);
    requestAnimationFrame(() => {
      const input = inputRef.current;
      if (input) {
        input.focus();
        input.setSelectionRange(nextCursor, nextCursor);
      }
    });
  }

  function appendReply(text: string) {
    setMessages((prev) => [
      ...prev,
      { id: `u-${Date.now()}`, role: "user", text },
      mockAgentReply(text, assetId!, agents),
    ]);
  }

  function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;

    if (trimmed.toLowerCase().includes("open full ops console") || trimmed.toLowerCase().includes("ops console")) {
      openAsset(assetId!);
      return;
    }

    appendReply(trimmed);
    setDraft("");
    setCursor(0);
  }

  function toggleEvidence(id: EvidenceId) {
    setExpandedEvidence((current) => (current === id ? null : id));
  }

  function approvePatch(patchId: string) {
    setPatchStatuses((prev) => ({ ...prev, [patchId]: "approved" }));
    setMessages((prev) => [
      ...prev,
      systemMessage(`Operator approved ${patchId} · ${formatUtcTime()} UTC`),
    ]);
  }

  function rejectPatch(patchId: string) {
    setPatchStatuses((prev) => ({ ...prev, [patchId]: "rejected" }));
    setMessages((prev) => [
      ...prev,
      systemMessage(`Operator rejected ${patchId} · ${formatUtcTime()} UTC`),
    ]);
  }

  function onInputKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!mentionOpen) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setMentionIndex((i) => (i + 1) % mentionCandidates.length);
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      setMentionIndex((i) => (i - 1 + mentionCandidates.length) % mentionCandidates.length);
      return;
    }

    if (event.key === "Enter" || event.key === "Tab") {
      event.preventDefault();
      applyMention(mentionCandidates[mentionIndex]!);
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      setDraft((value) => value.slice(0, activeMention!.start) + value.slice(cursor));
    }
  }

  return (
    <>
      <button
        className={`fleet-chat-backdrop${visible ? " is-open" : ""}`}
        aria-label="Close agent chat"
        onClick={closeFleetChat}
        type="button"
      />
      <aside
        className={`fleet-chat${visible ? " is-open" : ""}`}
        aria-label={`Agent chat for ${assetId}`}
      >
        <header className="fleet-chat-head">
          <div>
            <span className="fleet-chat-kicker">Supervised agents</span>
            <h2>{assetId}</h2>
            {asset ? <p>{asset.note}</p> : null}
          </div>
          <button className="fleet-chat-close" onClick={closeFleetChat} type="button" aria-label="Close">
            ×
          </button>
        </header>

        <div className="fleet-chat-scroll" ref={scrollRef}>
          {messages.map((msg) => (
            <ChatMessageView
              key={msg.id}
              expandedEvidence={expandedEvidence}
              labels={labels}
              msg={msg}
              onApprovePatch={approvePatch}
              onOpenConsole={() => openAsset(assetId!)}
              onRejectPatch={rejectPatch}
              onToggleEvidence={toggleEvidence}
              patchStatuses={patchStatuses}
            />
          ))}
        </div>

        <div className="fleet-chat-chips">
          {SUGGESTION_CHIPS.map((chip) => (
            <button key={chip} className="chat-chip" onClick={() => send(chip)} type="button">
              {chip}
            </button>
          ))}
        </div>

        <div className="fleet-chat-compose-wrap">
          {mentionOpen ? (
            <ul className="chat-mention-menu" id="chat-mention-menu" role="listbox" aria-label="Mention an agent">
              {mentionCandidates.map((candidate, index) => (
                <li
                  key={candidate.id}
                  role="option"
                  aria-selected={index === mentionIndex}
                  className={index === mentionIndex ? "is-active" : undefined}
                  onMouseDown={(event) => {
                    event.preventDefault();
                    applyMention(candidate);
                  }}
                >
                  <span className="chat-mention-option">@{candidate.label}</span>
                  {candidate.severity ? (
                    <span className={`chat-mention-sev sev-${candidate.severity.toLowerCase()}`}>
                      {candidate.severity}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}

          <form
            className="fleet-chat-compose"
            onSubmit={(e) => {
              e.preventDefault();
              if (mentionOpen) {
                applyMention(mentionCandidates[mentionIndex]!);
                return;
              }
              send(draft);
            }}
          >
            <input
              ref={inputRef}
              className="chat-input"
              placeholder="Message agents — type @ to mention…"
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                setCursor(e.target.selectionStart ?? e.target.value.length);
              }}
              onClick={syncCursor}
              onKeyUp={syncCursor}
              onKeyDown={onInputKeyDown}
              aria-label="Message agents"
              aria-expanded={mentionOpen}
              aria-autocomplete="list"
              aria-controls={mentionOpen ? "chat-mention-menu" : undefined}
            />
            <button className="chat-send" type="submit" aria-label="Send">
              ↑
            </button>
          </form>
        </div>
      </aside>
    </>
  );
}
