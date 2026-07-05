export type AssetHealth = "critical" | "caution" | "nominal";

export interface FleetAsset {
  id: string;
  health: AssetHealth;
  note: string;
  gpu: string;
  battery: number;
  eclipseMin: number | null;
  /** constellation placement */
  orbit: number;
  angle: number;
  speed: number;
}

// 2 critical · 3 caution · 7 nominal = 12 orbital datacenters
export const FLEET: FleetAsset[] = [
  { id: "AKJA-03", health: "critical", note: "thermal excursion · ckpt at risk", gpu: "40/48", battery: 31, eclipseMin: 6.1, orbit: 0, angle: 200, speed: 0.05 },
  { id: "AKJA-07", health: "critical", note: "downlink 18/180 GB · rollback pending", gpu: "44/48", battery: 46, eclipseMin: null, orbit: 1, angle: 120, speed: 0.04 },
  { id: "AKJA-01", health: "caution", note: "battery 34% · approaching eclipse", gpu: "48/48", battery: 34, eclipseMin: 9.8, orbit: 2, angle: 20, speed: 0.05 },
  { id: "AKJA-05", health: "caution", note: "power reserve low · shedding compute", gpu: "38/48", battery: 29, eclipseMin: 12, orbit: 0, angle: 320, speed: 0.05 },
  { id: "AKJA-09", health: "caution", note: "rank lag on 2 nodes", gpu: "46/48", battery: 62, eclipseMin: null, orbit: 1, angle: 250, speed: 0.04 },
  { id: "AKJA-02", health: "nominal", note: "nominal · training on track", gpu: "48/48", battery: 71, eclipseMin: null, orbit: 2, angle: 150, speed: 0.05 },
  { id: "AKJA-04", health: "nominal", note: "nominal", gpu: "48/48", battery: 68, eclipseMin: 22, orbit: 0, angle: 90, speed: 0.05 },
  { id: "AKJA-06", health: "nominal", note: "nominal", gpu: "48/48", battery: 80, eclipseMin: null, orbit: 1, angle: 40, speed: 0.04 },
  { id: "AKJA-08", health: "nominal", note: "nominal", gpu: "48/48", battery: 77, eclipseMin: null, orbit: 2, angle: 300, speed: 0.05 },
  { id: "AKJA-10", health: "nominal", note: "nominal", gpu: "48/48", battery: 64, eclipseMin: 14, orbit: 0, angle: 150, speed: 0.05 },
  { id: "AKJA-11", health: "nominal", note: "nominal · headroom for migration", gpu: "20/48", battery: 83, eclipseMin: null, orbit: 1, angle: 330, speed: 0.04 },
  { id: "AKJA-12", health: "nominal", note: "nominal", gpu: "48/48", battery: 59, eclipseMin: null, orbit: 2, angle: 80, speed: 0.05 },
];

/** Ellipse params (design space 800×460, centre 400,230) for the constellation. */
export const ORBITS = [
  { rx: 320, ry: 150, tilt: -18 },
  { rx: 250, ry: 210, tilt: 24 },
  { rx: 342, ry: 96, tilt: 8 },
];

export const HEALTH_LABEL: Record<AssetHealth, string> = {
  critical: "Critical",
  caution: "Caution",
  nominal: "Nominal",
};

export const HEALTH_TOKEN: Record<AssetHealth, string> = {
  critical: "var(--red)",
  caution: "var(--amber)",
  nominal: "var(--green)",
};

export interface FleetDecision {
  id: string;
  kind: "patch" | "migration";
  asset: string;
  target?: string;
  severity: AssetHealth;
  label: string;
  detail: string;
}

export const FLEET_QUEUE: FleetDecision[] = [
  { id: "patch-042", kind: "patch", asset: "AKJA-03", severity: "critical", label: "patch-042 · AKJA-03", detail: "Roll back to ckpt-184500 & cordon Node C before eclipse." },
  { id: "migrate-118", kind: "migration", asset: "AKJA-03", target: "AKJA-11", severity: "critical", label: "migrate-118", detail: "Evacuate the 14-day training job off the failing datacenter onto healthy capacity." },
  { id: "patch-039", kind: "patch", asset: "AKJA-05", severity: "caution", label: "patch-039 · AKJA-05", detail: "Shed non-critical compute to hold power reserve through eclipse." },
];

export function problemTitle(note: string): string {
  return note.split("·")[0]?.trim() || note;
}

export interface FleetIrTarget {
  id: string;
  status: string;
  tempC: number;
}

/** IR thermal cam target for fleet satellites with a thermal issue. */
export function fleetIrTarget(assetId: string): FleetIrTarget | null {
  const asset = FLEET.find((a) => a.id === assetId);
  if (!asset || asset.health === "nominal") {
    return null;
  }
  const note = asset.note.toLowerCase();
  if (!note.includes("thermal")) {
    return null;
  }
  return { id: "Node C", status: "unsafe", tempC: 96.4 };
}

/** Satellites with an active issue, most severe first. */
export function fleetAlerts() {
  const rank = { critical: 0, caution: 1, nominal: 2 };
  return FLEET.filter((a) => a.health !== "nominal").sort(
    (a, b) => rank[a.health] - rank[b.health],
  );
}

export const FLEET_AGG = {
  total: 12,
  critical: 2,
  caution: 3,
  eclipsing: 3,
  gpuOnline: 428,
  gpuTotal: 576,
  decisions: 3,
};
