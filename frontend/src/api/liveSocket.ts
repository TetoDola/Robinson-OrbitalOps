import { useWorldStore } from "../store/worldStore";
import type { BackendLiveEvent } from "../types/backend";

const WS_URL = import.meta.env.VITE_WS_URL ?? "";

function defaultWsUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws/live`;
}

export function connectLiveSocket(): () => void {
  let socket: WebSocket | null = null;
  let reconnectTimer: number | null = null;
  let closedByClient = false;

  const store = useWorldStore.getState();

  function scheduleReconnect() {
    if (closedByClient) {
      return;
    }
    useWorldStore.getState().setConnectionStatus("offline");
    reconnectTimer = window.setTimeout(connect, 1500);
  }

  function connect() {
    useWorldStore.getState().setConnectionStatus("connecting");
    socket = new WebSocket(WS_URL || defaultWsUrl());

    socket.addEventListener("open", () => {
      useWorldStore.getState().setConnectionStatus("live");
    });

    socket.addEventListener("message", (message) => {
      try {
        const event = JSON.parse(message.data as string) as BackendLiveEvent;
        store.ingestLiveEvent(event);
      } catch {
        useWorldStore.getState().setConnectionStatus("error");
      }
    });

    socket.addEventListener("close", scheduleReconnect);
    socket.addEventListener("error", () => {
      useWorldStore.getState().setConnectionStatus("error");
      socket?.close();
    });
  }

  connect();

  return () => {
    closedByClient = true;
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer);
    }
    socket?.close();
  };
}
