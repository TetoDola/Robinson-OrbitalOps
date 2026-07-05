import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { getRadiationRiskForSatellite } from "./radiationRisk.mjs";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const PORT = Number(process.env.PORT || 4000);
const MOCK_PATH = join(__dirname, "data", "telemetry.mock.json");

function sendJson(res, status, payload) {
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET, OPTIONS",
    "access-control-allow-headers": "content-type",
    "cache-control": "no-store",
  });
  res.end(JSON.stringify(payload));
}

async function getTelemetrySnapshot() {
  const raw = await readFile(MOCK_PATH, "utf8");
  const snapshot = JSON.parse(raw);
  const generatedAt = new Date().toISOString();
  const activeSatelliteId = snapshot.mission?.activeSatelliteId;
  const satellites = await Promise.all(
    (snapshot.satellites ?? []).map(async (satellite) => {
      if (activeSatelliteId && satellite.id !== activeSatelliteId) {
        return satellite;
      }
      const radiationRisk = await getRadiationRiskForSatellite(satellite, generatedAt);
      return {
        ...satellite,
        radiationRisk,
        telemetry: {
          ...satellite.telemetry,
          radiationRisk: radiationRisk.legacyRadiationRisk,
        },
      };
    }),
  );

  return {
    ...snapshot,
    generatedAt,
    source: {
      ...snapshot.source,
      mode: process.env.ORBITOPS_DATA_MODE || snapshot.source.mode,
      provider: process.env.ORBITOPS_DATA_PROVIDER || snapshot.source.provider,
    },
    satellites,
  };
}

async function getActiveRadiationRisk() {
  const snapshot = await getTelemetrySnapshot();
  const activeSatelliteId = snapshot.mission?.activeSatelliteId;
  const satellite =
    snapshot.satellites.find((item) => item.id === activeSatelliteId) ?? snapshot.satellites[0];

  return {
    generatedAt: snapshot.generatedAt,
    satelliteId: satellite?.id ?? null,
    radiationRisk: satellite?.radiationRisk ?? null,
  };
}

const server = createServer(async (req, res) => {
  if (req.method === "OPTIONS") {
    res.writeHead(204, {
      "access-control-allow-origin": "*",
      "access-control-allow-methods": "GET, OPTIONS",
      "access-control-allow-headers": "content-type",
    });
    res.end();
    return;
  }

  if (req.method === "GET" && req.url === "/health") {
    sendJson(res, 200, { ok: true });
    return;
  }

  if (req.method === "GET" && req.url === "/api/telemetry") {
    try {
      sendJson(res, 200, await getTelemetrySnapshot());
    } catch (error) {
      sendJson(res, 500, {
        error: "telemetry_unavailable",
        message: error instanceof Error ? error.message : "Unknown error",
      });
    }
    return;
  }

  if (req.method === "GET" && req.url === "/api/radiation-risk") {
    try {
      sendJson(res, 200, await getActiveRadiationRisk());
    } catch (error) {
      sendJson(res, 500, {
        error: "radiation_risk_unavailable",
        message: error instanceof Error ? error.message : "Unknown error",
      });
    }
    return;
  }

  sendJson(res, 404, { error: "not_found" });
});

server.listen(PORT, () => {
  console.log(`OrbitOps backend listening on http://localhost:${PORT}`);
  console.log("Telemetry endpoint: /api/telemetry");
  console.log("Radiation endpoint: /api/radiation-risk");
});
