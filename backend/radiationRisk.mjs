import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const MOCK_ENV_PATH = join(__dirname, "data", "radiation-environment.mock.json");
const EARTH_RADIUS_KM = 6371;
const NOAA_TIMEOUT_MS = 2500;
const ENV_CACHE_MS = Number(process.env.ORBITOPS_RADIATION_CACHE_MS || 60000);
const POES_LAT_STEP_DEG = 8;
const POES_LON_STEP_DEG = 10;
let environmentCache = null;
const NOAA_ENDPOINTS = {
  solarWindPlasma: "https://services.swpc.noaa.gov/products/solar-wind/plasma-1-day.json",
  solarWindMag: "https://services.swpc.noaa.gov/products/solar-wind/mag-1-day.json",
  xrayFlux: "https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json",
  protonFlux: "https://services.swpc.noaa.gov/json/goes/primary/integral-protons-6-hour.json",
  kpIndex: "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
};

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function normalizeLon(lon) {
  return ((((lon + 180) % 360) + 360) % 360) - 180;
}

function numberFrom(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function latestTableRow(table) {
  if (!Array.isArray(table) || table.length < 2 || !Array.isArray(table[0])) {
    return null;
  }
  const headers = table[0].map((item) => String(item).toLowerCase());
  const rows = table.slice(1).filter((row) => Array.isArray(row));
  const row = rows.at(-1);
  if (!row) return null;
  return Object.fromEntries(headers.map((header, index) => [header, row[index]]));
}

function latestObject(records) {
  if (!Array.isArray(records)) return null;
  return records.filter((item) => item && typeof item === "object" && !Array.isArray(item)).at(-1) ?? null;
}

function tableRows(table) {
  if (!Array.isArray(table) || table.length < 2 || !Array.isArray(table[0])) {
    return [];
  }
  const headers = table[0].map((item) => String(item).toLowerCase());
  return table
    .slice(1)
    .filter((row) => Array.isArray(row))
    .map((row) => Object.fromEntries(headers.map((header, index) => [header, row[index]])));
}

function timeFromRecord(record) {
  const raw =
    record?.time_tag ??
    record?.time ??
    record?.timestamp ??
    record?.observed_at ??
    record?.date ??
    record?.[Object.keys(record ?? {}).find((key) => key.toLowerCase().includes("time"))];
  const ms = Date.parse(raw);
  return Number.isFinite(ms) ? ms : null;
}

function latestBefore(records, timestampMs) {
  let best = null;
  let bestMs = -Infinity;
  records.forEach((record) => {
    const ms = timeFromRecord(record);
    if (ms !== null && ms <= timestampMs && ms > bestMs) {
      best = record;
      bestMs = ms;
    }
  });
  return best ?? records.at(-1) ?? null;
}

async function fetchJson(url) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), NOAA_TIMEOUT_MS);
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) {
      throw new Error(`${url} returned ${response.status}`);
    }
    return await response.json();
  } finally {
    clearTimeout(timeout);
  }
}

async function readMockEnvironment(reason = "mock source") {
  const raw = await readFile(MOCK_ENV_PATH, "utf8");
  return {
    ...JSON.parse(raw),
    sourceMode: reason === "mock source" ? "mock" : "fallback",
    fallbackReason: reason === "mock source" ? undefined : reason,
  };
}

async function fetchLiveSource(name, url) {
  try {
    return { name, url, status: "fulfilled", data: await fetchJson(url) };
  } catch (error) {
    return {
      name,
      url,
      status: "rejected",
      reason: error instanceof Error ? error.message : "unknown ingest failure",
    };
  }
}

function parseSolarWind(plasma, mag) {
  const plasmaRow = latestTableRow(plasma);
  const magRow = latestTableRow(mag);
  return parseSolarWindRows(plasmaRow, magRow);
}

function parseSolarWindRows(plasmaRow, magRow) {
  return {
    speedKms:
      numberFrom(plasmaRow?.speed) ??
      numberFrom(plasmaRow?.speed_km_s) ??
      numberFrom(plasmaRow?.bulk_speed) ??
      0,
    densityPcc:
      numberFrom(plasmaRow?.density) ??
      numberFrom(plasmaRow?.density_pcc) ??
      numberFrom(plasmaRow?.proton_density) ??
      0,
    btNt: numberFrom(magRow?.bt) ?? numberFrom(magRow?.bt_nt) ?? numberFrom(magRow?.total_field) ?? 0,
    bzNt: numberFrom(magRow?.bz_gsm) ?? numberFrom(magRow?.bz) ?? 0,
  };
}

function parseXrayFlux(records) {
  const values = Array.isArray(records)
    ? records
        .map((record) => numberFrom(record?.flux))
        .filter((value) => value !== null)
    : [];
  return Math.max(0, ...values);
}

function parseProtonFlux(records) {
  if (!Array.isArray(records)) return 0;
  const values = records
    .filter((record) => {
      const energy = String(record?.energy ?? record?.channel ?? "").toLowerCase();
      return !energy || energy.includes(">=10") || energy.includes(">10") || energy.includes("10 mev");
    })
    .map((record) => numberFrom(record?.flux))
    .filter((value) => value !== null);
  return Math.max(0, ...values);
}

function parseKpIndex(records) {
  const row = latestTableRow(records);
  if (row) {
    return (
      numberFrom(row.kp) ??
      numberFrom(row.kp_index) ??
      numberFrom(row.estimated_kp) ??
      numberFrom(Object.values(row).find((value) => numberFrom(value) !== null))
    );
  }
  const record = latestObject(records);
  if (!record) return null;
  return numberFrom(record.kp) ?? numberFrom(record.kp_index) ?? numberFrom(record.estimated_kp);
}

function parseXrayFluxForRecord(record) {
  return Math.max(0, numberFrom(record?.flux) ?? 0);
}

function parseProtonFluxForRecords(records) {
  if (!Array.isArray(records)) return 0;
  const values = records
    .filter((record) => {
      const energy = String(record?.energy ?? record?.channel ?? "").toLowerCase();
      return !energy || energy.includes(">=10") || energy.includes(">10") || energy.includes("10 mev");
    })
    .map((record) => numberFrom(record?.flux))
    .filter((value) => value !== null);
  return Math.max(0, ...values);
}

function buildLiveSamples(liveData, fallback) {
  const plasmaRows = tableRows(liveData.solarWindPlasma);
  const magRows = tableRows(liveData.solarWindMag);
  const xrayRows = Array.isArray(liveData.xrayFlux) ? liveData.xrayFlux : [];
  const protonRows = Array.isArray(liveData.protonFlux) ? liveData.protonFlux : [];
  const kpRows = tableRows(liveData.kpIndex);
  const kpObjects = Array.isArray(liveData.kpIndex)
    ? liveData.kpIndex.filter((item) => item && typeof item === "object" && !Array.isArray(item))
    : [];
  const timed = [...plasmaRows, ...magRows, ...xrayRows, ...protonRows, ...kpRows, ...kpObjects]
    .map(timeFromRecord)
    .filter((value) => value !== null);
  if (timed.length === 0) return [];

  const latestMs = Math.max(...timed);
  const protonWindow = protonRows.filter((record) => {
    const ms = timeFromRecord(record);
    return ms !== null && ms <= latestMs && ms >= latestMs - 15 * 60 * 1000;
  });
  const latestSample = {
    timestamp: new Date(latestMs).toISOString(),
    solarWind:
      plasmaRows.length || magRows.length
        ? parseSolarWindRows(latestBefore(plasmaRows, latestMs), latestBefore(magRows, latestMs))
        : fallback.solarWind,
    xrayFluxWattsM2: xrayRows.length ? parseXrayFluxForRecord(latestBefore(xrayRows, latestMs)) : fallback.xrayFluxWattsM2,
    protonFluxPfu: protonWindow.length ? parseProtonFluxForRecords(protonWindow) : fallback.protonFluxPfu,
    kpIndex:
      numberFrom(latestBefore(kpRows.length ? kpRows : kpObjects, latestMs)?.kp) ??
      numberFrom(latestBefore(kpRows.length ? kpRows : kpObjects, latestMs)?.kp_index) ??
      numberFrom(latestBefore(kpRows.length ? kpRows : kpObjects, latestMs)?.estimated_kp) ??
      fallback.kpIndex,
    protonEvent: protonWindow.length ? parseProtonFluxForRecords(protonWindow) >= 10 : fallback.protonEvent,
  };
  return [latestSample];
}

export async function fetchRadiationEnvironment() {
  const mode = process.env.ORBITOPS_RADIATION_SOURCE || "auto";
  const now = Date.now();
  if (environmentCache && environmentCache.mode === mode && now - environmentCache.createdAt < ENV_CACHE_MS) {
    return environmentCache.environment;
  }

  if (mode === "mock") {
    const environment = await readMockEnvironment();
    environmentCache = { mode, createdAt: now, environment };
    return environment;
  }

  const liveResults = await Promise.all(
    Object.entries(NOAA_ENDPOINTS).map(([name, url]) => fetchLiveSource(name, url)),
  );
  const liveData = Object.fromEntries(
    liveResults
      .filter((result) => result.status === "fulfilled")
      .map((result) => [result.name, result.data]),
  );
  const successfulSources = liveResults.filter((result) => result.status === "fulfilled");
  const failedSources = liveResults.filter((result) => result.status === "rejected");

  if (successfulSources.length > 0) {
    const fallback = await readMockEnvironment("partial live ingest");
    const environment = {
      sourceMode: "live",
      generatedAt: new Date().toISOString(),
      ingestStatus: failedSources.length > 0 ? "partial_live" : "live",
      solarWind:
        liveData.solarWindPlasma || liveData.solarWindMag
          ? parseSolarWind(liveData.solarWindPlasma, liveData.solarWindMag)
          : fallback.solarWind,
      xrayFluxWattsM2: liveData.xrayFlux ? parseXrayFlux(liveData.xrayFlux) : fallback.xrayFluxWattsM2,
      protonFluxPfu: liveData.protonFlux ? parseProtonFlux(liveData.protonFlux) : fallback.protonFluxPfu,
      kpIndex: liveData.kpIndex ? parseKpIndex(liveData.kpIndex) ?? fallback.kpIndex : fallback.kpIndex,
      protonEvent: liveData.protonFlux ? parseProtonFlux(liveData.protonFlux) >= 10 : fallback.protonEvent,
      liveSamples: buildLiveSamples(liveData, fallback),
      sources: successfulSources.map((result) => result.url),
      failedSources: failedSources.map((result) => ({
        name: result.name,
        url: result.url,
        reason: result.reason,
      })),
    };
    environmentCache = { mode, createdAt: now, environment };
    return environment;
  }

  if (mode === "live") {
    throw new Error("All live radiation sources failed.");
  }

  const environment = await readMockEnvironment("live radiation ingest failed");
  environment.failedSources = failedSources.map((result) => ({
    name: result.name,
    url: result.url,
    reason: result.reason,
  }));
  environmentCache = { mode, createdAt: now, environment };
  return environment;
}

export function buildTrajectory(satellite, generatedAt) {
  const position = satellite?.orbit?.position ?? {};
  const lat = numberFrom(position.latDeg) ?? 0;
  const lon = numberFrom(position.lonDeg) ?? 0;
  const altitudeKm = numberFrom(position.altitudeKm) ?? 420;
  const velocityKms = numberFrom(satellite?.orbit?.velocityKms) ?? 7.67;
  const circumferenceKm = 2 * Math.PI * (EARTH_RADIUS_KM + altitudeKm);
  const degPerSec = (velocityKms / circumferenceKm) * 360;
  const epoch = Date.parse(generatedAt) || Date.now();

  return Array.from({ length: 13 }, (_, index) => index * 300).map((offsetSec) => {
    const phase = (offsetSec / 3600) * Math.PI * 2;
    return {
      timestamp: new Date(epoch + offsetSec * 1000).toISOString(),
      latDeg: clamp(lat + Math.sin(phase) * 12, -90, 90),
      lonDeg: normalizeLon(lon + degPerSec * offsetSec),
      altitudeKm,
    };
  });
}

function southAtlanticAnomalyFactor(position) {
  const lat = numberFrom(position.latDeg) ?? 0;
  const lon = numberFrom(position.lonDeg) ?? 0;
  const altitudeKm = numberFrom(position.altitudeKm) ?? 0;
  const latDistance = Math.abs(lat + 25) / 28;
  const lonDistance = Math.abs(normalizeLon(lon + 45)) / 45;
  const locationFactor = clamp(1 - Math.max(latDistance, lonDistance), 0, 1);
  const altitudeFactor = altitudeKm >= 300 && altitudeKm <= 900 ? 0.75 : altitudeKm > 900 ? 0.4 : 0.15;
  return locationFactor * altitudeFactor;
}

function vanAllenFactor(position) {
  const altitudeKm = numberFrom(position.altitudeKm) ?? 0;
  let beltFactor = 0;
  if (altitudeKm >= 1000 && altitudeKm <= 12000) {
    beltFactor = 0.55 + 0.45 * clamp(1 - Math.abs(altitudeKm - 5000) / 5000, 0, 1);
  } else if (altitudeKm > 12000 && altitudeKm <= 60000) {
    beltFactor = 0.35 + 0.35 * clamp(1 - Math.abs(altitudeKm - 20000) / 20000, 0, 1);
  }
  return clamp(Math.max(beltFactor, southAtlanticAnomalyFactor(position)), 0, 1);
}

function solarFactor(environment) {
  const wind = environment.solarWind ?? {};
  const speed = numberFrom(wind.speedKms) ?? 0;
  const density = numberFrom(wind.densityPcc) ?? 0;
  const bzSouth = Math.max(0, -(numberFrom(wind.bzNt) ?? 0));
  const xray = numberFrom(environment.xrayFluxWattsM2) ?? 0;
  const protons = numberFrom(environment.protonFluxPfu) ?? 0;

  const xrayFactor = clamp(Math.log10(Math.max(xray, 1e-9) / 1e-6) / 2.2, 0, 1);
  const protonFactor = clamp(Math.log10(Math.max(protons, 1) / 10) / 2, 0, 1);
  const windFactor = clamp((speed - 450) / 450, 0, 1) * 0.65 + clamp((density - 8) / 25, 0, 1) * 0.2 + clamp(bzSouth / 15, 0, 1) * 0.15;
  return clamp(Math.max(xrayFactor, protonFactor, windFactor), 0, 1);
}

function geomagneticFactor(environment) {
  const kp = numberFrom(environment.kpIndex) ?? 0;
  return clamp((kp - 3) / 6, 0, 1);
}

function levelForScore(score) {
  if (score >= 75) return "CRITICAL";
  if (score >= 50) return "HIGH";
  if (score >= 25) return "MEDIUM";
  return "LOW";
}

function actionForLevel(level) {
  if (level === "CRITICAL") return "shutdown sensitive tasks";
  if (level === "HIGH") return "migrate workload";
  if (level === "MEDIUM") return "delay compute";
  return "continue";
}

function legacyRisk(level) {
  if (level === "CRITICAL") return "critical";
  if (level === "HIGH") return "high";
  if (level === "MEDIUM") return "elevated";
  return "low";
}

function buildBandPoints({ latitudeDeg, phaseDeg = 0, amplitudeDeg = 2.5, stepDeg = 8 }) {
  const points = [];
  for (let lonDeg = -180; lonDeg <= 180; lonDeg += stepDeg) {
    points.push({
      latDeg: clamp(latitudeDeg + Math.sin(((lonDeg + phaseDeg) * Math.PI) / 45) * amplitudeDeg, -88, 88),
      lonDeg,
    });
  }
  return points;
}

function buildEllipsePoints({ centerLatDeg, centerLonDeg, radiusLatDeg, radiusLonDeg, stepDeg = 10, wobbleDeg = 0 }) {
  const points = [];
  for (let deg = 0; deg <= 360; deg += stepDeg) {
    const angle = (deg * Math.PI) / 180;
    const wobble = Math.sin(angle * 3 + (wobbleDeg * Math.PI) / 180) * 0.08;
    points.push({
      latDeg: clamp(centerLatDeg + Math.sin(angle) * radiusLatDeg * (1 + wobble), -88, 88),
      lonDeg: normalizeLon(centerLonDeg + Math.cos(angle) * radiusLonDeg * (1 - wobble)),
    });
  }
  return points;
}

function angularDistanceDeg(a, b) {
  return Math.abs(normalizeLon(a - b));
}

function gaussian(distance, sigma) {
  return Math.exp(-(distance * distance) / (2 * sigma * sigma));
}

function fluxColorForLog10(logFlux) {
  if (logFlux >= 5.2) return "#ff2f1f";
  if (logFlux >= 4.5) return "#ff9d1e";
  if (logFlux >= 3.8) return "#ffe443";
  if (logFlux >= 3.1) return "#48e85f";
  if (logFlux >= 2.4) return "#22d7d9";
  if (logFlux >= 1.7) return "#1a74ff";
  return "#3b25d6";
}

function buildPoesFluxCells({ solar, geomagnetic, timestamp }) {
  const timestampMs = Date.parse(timestamp) || Date.now();
  const phaseDeg = (timestampMs / 240000) % 360;
  const auroraLatitude = 66 - geomagnetic * 13;
  const stormBoost = 0.6 + geomagnetic * 3.2;
  const protonBoost = solar * 2.4;
  const cells = [];

  for (let latMin = -88; latMin < 88; latMin += POES_LAT_STEP_DEG) {
    const latMax = Math.min(88, latMin + POES_LAT_STEP_DEG);
    const lat = (latMin + latMax) / 2;
    for (let lonMin = -180; lonMin < 180; lonMin += POES_LON_STEP_DEG) {
      const lonMax = lonMin + POES_LON_STEP_DEG;
      const lon = normalizeLon((lonMin + lonMax) / 2);
      const northOval = gaussian(Math.abs(lat - auroraLatitude), 7 + geomagnetic * 5);
      const southOval = gaussian(Math.abs(lat + auroraLatitude), 7 + geomagnetic * 5);
      const longitudeTexture =
        0.72 +
        0.28 * Math.sin(((lon + phaseDeg) * Math.PI) / 45) +
        0.16 * Math.cos(((lon * 2 - phaseDeg) * Math.PI) / 60);
      const auroralFlux = Math.max(northOval, southOval) * stormBoost * longitudeTexture;

      const saaDistance =
        Math.hypot((lat + 25) / 19, angularDistanceDeg(lon, -45 + Math.sin((phaseDeg * Math.PI) / 180) * 4) / 42);
      const saaFlux = gaussian(saaDistance, 0.95) * (2.1 + protonBoost * 0.8);

      const polarCap = gaussian(Math.abs(Math.abs(lat) - 78), 12) * geomagnetic * 0.9;
      const solarPatch =
        gaussian(Math.abs(lat - Math.sin((phaseDeg * Math.PI) / 180) * 10), 24) *
        gaussian(angularDistanceDeg(lon, normalizeLon(phaseDeg - 120)), 58) *
        protonBoost;

      const logFlux = clamp(1 + auroralFlux + saaFlux + polarCap + solarPatch, 1, 6);
      if (logFlux < 1.22) continue;

      cells.push({
        latMinDeg: latMin,
        latMaxDeg: latMax,
        lonMinDeg: lonMin,
        lonMaxDeg: lonMax,
        log10Flux: Number(logFlux.toFixed(2)),
        normalizedFlux: Number(((logFlux - 1) / 5).toFixed(3)),
        color: fluxColorForLog10(logFlux),
      });
    }
  }

  return cells;
}

function pointRiskScore({ solar, geomagnetic, point }) {
  return Math.round(clamp(solar * 42 + geomagnetic * 30 + vanAllenFactor(point) * 38, 0, 100));
}

function buildRadiationZones({ solar, geomagnetic, timestamp }) {
  const phaseDeg = ((Date.parse(timestamp) || Date.now()) / 60000) % 360;
  const auroraLatitude = 66 - geomagnetic * 12;
  const auroraScore = Math.round(clamp(geomagnetic * 100, 0, 100));
  const solarScore = Math.round(clamp(solar * 100, 0, 100));
  const zones = [
    {
      id: "aurora-north",
      type: "auroral_curtain",
      cause: "geomagnetic storm",
      level: levelForScore(auroraScore),
      riskScore: auroraScore,
      color: "#65f5c8",
      opacity: Number((0.18 + geomagnetic * 0.45).toFixed(2)),
      altitudeScale: 1.055,
      widthDeg: Number((7 + geomagnetic * 16).toFixed(1)),
      thickness: Number((0.004 + geomagnetic * 0.006).toFixed(4)),
      pulseRate: 0.8,
      points: buildBandPoints({ latitudeDeg: auroraLatitude, phaseDeg }),
    },
    {
      id: "aurora-south",
      type: "auroral_curtain",
      cause: "geomagnetic storm",
      level: levelForScore(auroraScore),
      riskScore: auroraScore,
      color: "#7db7ff",
      opacity: Number((0.16 + geomagnetic * 0.42).toFixed(2)),
      altitudeScale: 1.055,
      widthDeg: Number((7 + geomagnetic * 15).toFixed(1)),
      thickness: Number((0.004 + geomagnetic * 0.006).toFixed(4)),
      pulseRate: 0.72,
      points: buildBandPoints({ latitudeDeg: -auroraLatitude, phaseDeg: phaseDeg + 70 }),
    },
    {
      id: "south-atlantic-anomaly",
      type: "particle_hotspot",
      cause: "Van Allen",
      level: "HIGH",
      riskScore: 72,
      color: "#f0b35a",
      opacity: 0.5,
      altitudeScale: 1.045,
      widthDeg: 18,
      thickness: 0.008,
      pulseRate: 0.45,
      points: buildEllipsePoints({
        centerLatDeg: -25,
        centerLonDeg: normalizeLon(-45 + Math.sin((phaseDeg * Math.PI) / 180) * 4),
        radiusLatDeg: 18,
        radiusLonDeg: 38,
        wobbleDeg: phaseDeg,
      }),
    },
  ];

  if (solar > 0.08) {
    zones.push({
      id: "solar-particle-wash",
      type: "solar_particle_wash",
      cause: "solar",
      level: levelForScore(solarScore),
      riskScore: solarScore,
      color: "#ffda7a",
      opacity: Number((0.12 + solar * 0.38).toFixed(2)),
      altitudeScale: 1.07,
      widthDeg: Number((16 + solar * 30).toFixed(1)),
      thickness: Number((0.006 + solar * 0.008).toFixed(4)),
      pulseRate: 1.2,
      points: buildBandPoints({
        latitudeDeg: 8,
        phaseDeg: phaseDeg + 120,
        amplitudeDeg: 18,
        stepDeg: 10,
      }),
    });
  }
  return zones;
}

function buildRadiationVisualization({ trajectory, solar, geomagnetic, generatedAt, environment }) {
  const latestSample =
    Array.isArray(environment.liveSamples) && environment.liveSamples.length
      ? environment.liveSamples.at(-1)
      : { ...environment, timestamp: generatedAt };
  const latestSolar = solarFactor(latestSample);
  const latestGeomagnetic = geomagneticFactor(latestSample);
  const latestAsset = {
    id: "latest-poes-style-p6-flux",
    index: 0,
    timestamp: latestSample.timestamp ?? latestSample.generatedAt ?? generatedAt,
    solarExposure: Number(latestSolar.toFixed(3)),
    geomagneticStorm: Number(latestGeomagnetic.toFixed(3)),
    fluxCells: buildPoesFluxCells({
      solar: latestSolar,
      geomagnetic: latestGeomagnetic,
      timestamp: latestSample.timestamp ?? generatedAt,
    }),
    zones: [],
  };

  return {
    mode: "latest_poes_style_particle_flux_asset",
    generatedAt: new Date().toISOString(),
    assetCount: 1,
    refreshCadenceSeconds: Math.round(ENV_CACHE_MS / 1000),
    particleProduct: {
      style: "NOAA POES MEPED cylindrical particle flux",
      channel: "P6",
      species: "protons",
      energy: "> 6900 keV",
      detector: "zenith 0 deg",
      scale: "log10 protons/cm2/s/ster",
      grid: {
        latitudeStepDeg: POES_LAT_STEP_DEG,
        longitudeStepDeg: POES_LON_STEP_DEG,
      },
    },
    liveImageAvailability: {
      exactPoesCylindricalImageFeed: false,
      reason:
        "NOAA/NCEI POES cylindrical maps are archive/browse products; this app generates the latest POES-style asset from live NOAA/SWPC drivers.",
    },
    note: "Latest backend-modeled POES-style particle flux asset from live NOAA/SWPC drivers; not a direct POES archive image.",
    latestAsset,
    zones: [],
    frames: [latestAsset],
    trajectory: [],
  };
}

export function computeRadiationRisk({ satellite, generatedAt, trajectory, environment }) {
  const position = satellite?.orbit?.position ?? {};
  const solar = solarFactor(environment);
  const geomagnetic = geomagneticFactor(environment);
  const currentVanAllen = vanAllenFactor(position);
  const trajectoryVanAllen = Math.max(currentVanAllen, ...trajectory.map(vanAllenFactor));
  const score = Math.round(clamp(solar * 42 + geomagnetic * 30 + trajectoryVanAllen * 38, 0, 100));
  const radiationLevel = levelForScore(score);
  const causes = [
    ["solar", solar],
    ["geomagnetic storm", geomagnetic],
    ["Van Allen", trajectoryVanAllen],
  ].sort((a, b) => b[1] - a[1]);
  const mainCause = causes[0][0];
  const sourceText =
    environment.sourceMode === "live"
      ? environment.ingestStatus === "partial_live"
        ? "NOAA/SWPC partial live ingest"
        : "NOAA/SWPC live ingest"
      : "backend fallback ingest";

  return {
    radiationRiskScore: score,
    radiationLevel,
    mainCause,
    recommendedAction: actionForLevel(radiationLevel),
    explanation: `${sourceText}: solar ${Math.round(solar * 100)}%, Van Allen ${Math.round(trajectoryVanAllen * 100)}%, geomagnetic ${Math.round(geomagnetic * 100)}%.`,
    components: {
      solarExposure: Number(solar.toFixed(3)),
      vanAllenBelt: Number(trajectoryVanAllen.toFixed(3)),
      geomagneticStorm: Number(geomagnetic.toFixed(3)),
    },
    inputs: {
      position,
      solarWind: environment.solarWind,
      xrayFluxWattsM2: environment.xrayFluxWattsM2,
      protonFluxPfu: environment.protonFluxPfu,
      kpIndex: environment.kpIndex,
      protonEvent: Boolean(environment.protonEvent),
      ingestStatus: environment.ingestStatus,
    },
    trajectory,
    visualization: buildRadiationVisualization({ trajectory, solar, geomagnetic, generatedAt, environment }),
    sources: environment.sources ?? [],
    sourceMode: environment.sourceMode,
    generatedAt: new Date().toISOString(),
    legacyRadiationRisk: legacyRisk(radiationLevel),
  };
}

export async function getRadiationRiskForSatellite(satellite, generatedAt) {
  const environment = await fetchRadiationEnvironment();
  const trajectory = buildTrajectory(satellite, generatedAt);
  return computeRadiationRisk({ satellite, generatedAt, trajectory, environment });
}
