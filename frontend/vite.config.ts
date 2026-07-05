import { execFile } from "node:child_process";
import type { Plugin } from "vite";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiTarget = process.env.VITE_PROXY_API_TARGET ?? "http://localhost:8000";
const wsTarget = process.env.VITE_PROXY_WS_TARGET ?? "ws://localhost:8000";

// The backend runs in a container and cannot touch demo hardware, so approve/
// reject responses return declarative local_tool_calls and this dev-server
// endpoint executes them on the host. The MSI WMI ACPI write needs elevation,
// so the actual msi-fan-cli calls live in pre-registered elevated Scheduled
// Tasks ("OrbitOps Cooler Boost On/Off"); schtasks /run triggers them from
// this non-elevated process without a UAC prompt. On machines without those
// tasks, fall back to a simulated success so the demo cooling trace still runs.
const COOLER_BOOST_TASKS: Record<string, string> = {
  on: "OrbitOps Cooler Boost On",
  off: "OrbitOps Cooler Boost Off",
};

function isMissingScheduledTask(errorText: string): boolean {
  return /cannot find the file specified/i.test(errorText) || /the system cannot find/i.test(errorText);
}

function localCoolerBoostPlugin(): Plugin {
  return {
    name: "local-cooler-boost",
    configureServer(server) {
      server.middlewares.use("/__local/cooler-boost", (req, res) => {
        if (req.method !== "POST") {
          res.statusCode = 405;
          res.end(JSON.stringify({ ok: false, error: "POST only" }));
          return;
        }
        let body = "";
        req.on("data", (chunk) => {
          body += chunk;
        });
        req.on("end", () => {
          let action = "";
          try {
            action = String(JSON.parse(body || "{}").action ?? "");
          } catch {
            action = "";
          }
          res.setHeader("Content-Type", "application/json");
          const taskName = COOLER_BOOST_TASKS[action];
          if (!taskName) {
            res.statusCode = 400;
            res.end(JSON.stringify({ ok: false, error: `action must be one of: ${Object.keys(COOLER_BOOST_TASKS).join(", ")}` }));
            return;
          }
          execFile(
            "schtasks",
            ["/run", "/tn", taskName],
            { windowsHide: true, timeout: 20000 },
            (error, stdout, stderr) => {
              if (error) {
                const detail = [String(error.message ?? error), stderr, stdout].filter(Boolean).join("\n");
                if (isMissingScheduledTask(detail)) {
                  res.end(
                    JSON.stringify({
                      ok: true,
                      action,
                      simulated: true,
                      stdout: `Cooler Boost ${action} simulated; scheduled task "${taskName}" is not installed on this machine.`,
                      stderr: stderr?.trim(),
                    }),
                  );
                  return;
                }
                res.statusCode = 500;
                res.end(
                  JSON.stringify({
                    ok: false,
                    action,
                    error: String(error.message ?? error),
                    stdout: stdout?.trim(),
                    stderr: stderr?.trim(),
                  }),
                );
                return;
              }
              res.end(JSON.stringify({ ok: true, action, stdout: `Cooler Boost ${action} task started.` }));
            },
          );
        });
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), localCoolerBoostPlugin()],
  server: {
    port: 5173,
    proxy: {
      "/world-state": apiTarget,
      "/agents": apiTarget,
      "/chat": apiTarget,
      "/commands": apiTarget,
      "/incidents": apiTarget,
      "/mission-patches": apiTarget,
      "/radiation-risk": apiTarget,
      "/simulator": apiTarget,
      "/api": apiTarget,
      "/health": apiTarget,
      "/ws": {
        target: wsTarget,
        ws: true,
      },
    },
  },
});
