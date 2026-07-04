import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiTarget = process.env.VITE_PROXY_API_TARGET ?? "http://localhost:8000";
const wsTarget = process.env.VITE_PROXY_WS_TARGET ?? "ws://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/world-state": apiTarget,
      "/agents": apiTarget,
      "/commands": apiTarget,
      "/incidents": apiTarget,
      "/mission-patches": apiTarget,
      "/simulator": apiTarget,
      "/health": apiTarget,
      "/ws": {
        target: wsTarget,
        ws: true,
      },
    },
  },
});
