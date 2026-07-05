import { runLocalToolCall, type LocalToolCall } from "../api/client";
import { useWorldStore } from "../store/worldStore";

const MIN_DEMO_BASELINE_TEMP_C = 84;
const COOLING_SAMPLE_INTERVAL_MS = 1000;
const COOLING_SAMPLE_LIMIT = 16;

let coolingTimer: ReturnType<typeof setInterval> | null = null;

function humanizeTool(call: LocalToolCall): string {
  return `${call.tool.replace(/_/g, " ")} ${call.action}`;
}

function isCoolerBoost(call: LocalToolCall, action?: string): boolean {
  return call.tool === "cooler_boost" && (!action || call.action === action);
}

function currentThermalBaseline(): number {
  const worldState = useWorldStore.getState().worldState;
  const thermalTemp = worldState?.thermal.highest_temp_c ?? 0;
  const nodeTemp = worldState?.nodes.reduce((max, node) => Math.max(max, node.temp_c ?? 0), 0) ?? 0;
  return Math.max(MIN_DEMO_BASELINE_TEMP_C, thermalTemp, nodeTemp);
}

function coolingTargetFor(baselineTempC: number): number {
  return Math.max(58, Math.min(64, baselineTempC - 27));
}

function stopCoolingSamples(): void {
  if (coolingTimer) {
    clearInterval(coolingTimer);
    coolingTimer = null;
  }
}

function beginCoolingSamples(): void {
  stopCoolingSamples();
  let tick = 0;

  coolingTimer = setInterval(() => {
    const store = useWorldStore.getState();
    const trend = store.coolingTrend;
    if (!["activating", "active"].includes(trend.status)) {
      stopCoolingSamples();
      return;
    }

    const previous = trend.samples[trend.samples.length - 1]?.tempC ?? trend.baselineTempC;
    const remaining = Math.max(0, previous - trend.targetTempC);
    const coolingStep = Math.max(0.45, remaining * 0.2);
    const sensorRipple = Math.sin((tick + 1) * 1.4) * 0.08;
    const nextTemp = Math.max(trend.targetTempC, previous - coolingStep + sensorRipple);
    const fanPct = Math.max(72, Math.round(100 - tick * 1.8));

    store.appendCoolingTrendSample({
      time: new Date().toISOString(),
      tempC: nextTemp,
      fanPct,
    });

    tick += 1;
    if (tick >= COOLING_SAMPLE_LIMIT || nextTemp <= trend.targetTempC + 0.4) {
      store.setCoolingTrendStatus("settled", "Cooling stabilized");
      stopCoolingSamples();
    }
  }, COOLING_SAMPLE_INTERVAL_MS);
}

function prepareCoolingTrend(call: LocalToolCall): void {
  const baselineTempC = currentThermalBaseline();
  useWorldStore.getState().startCoolingTrend({
    baselineTempC,
    targetTempC: coolingTargetFor(baselineTempC),
    message: call.reason ?? "Cooling system activating",
  });
}

function markCoolingActivated(): void {
  const store = useWorldStore.getState();
  store.setCoolingTrendStatus("active", "Cooling system activated");
  beginCoolingSamples();
}

function markCoolingFailed(detail: string): void {
  stopCoolingSamples();
  useWorldStore.getState().setCoolingTrendStatus("failed", detail);
}

function markCoolingOff(): void {
  stopCoolingSamples();
  const store = useWorldStore.getState();
  if (store.coolingTrend.samples.length > 0) {
    store.setCoolingTrendStatus("off", "Cooling profile restored");
  }
}

/** Execute backend-issued local tool calls on the operator's machine and log
 *  the outcome to the live workflow rail. Fire-and-forget from approval flows. */
export async function runHardwareToolCalls(calls: LocalToolCall[]): Promise<void> {
  const store = useWorldStore.getState();
  for (const call of calls) {
    if (isCoolerBoost(call, "on")) {
      prepareCoolingTrend(call);
    }

    store.pushWorkflowEvent({
      id: `local-tool-${call.tool}-${call.action}-${Date.now()}`,
      time: new Date().toISOString(),
      label: isCoolerBoost(call, "on") ? "Cooling system activating" : `Hardware: ${humanizeTool(call)}`,
      detail: call.reason ?? call.command ?? "",
      status: "running",
    });

    const result = await runLocalToolCall(call);
    if (isCoolerBoost(call, "on") && result.ok) {
      markCoolingActivated();
    } else if (isCoolerBoost(call, "on")) {
      markCoolingFailed(result.error ?? result.stderr ?? "Cooler Boost command failed.");
    } else if (isCoolerBoost(call, "off") && result.ok) {
      markCoolingOff();
    }

    const coolingStartTemp = useWorldStore.getState().coolingTrend.samples[0]?.tempC;
    store.pushWorkflowEvent({
      id: `local-tool-result-${call.tool}-${call.action}-${Date.now()}`,
      time: new Date().toISOString(),
      label:
        isCoolerBoost(call, "on") && result.ok
          ? "Cooling system activated"
          : `Hardware: ${humanizeTool(call)} ${result.ok ? "done" : "failed"}`,
      detail:
        isCoolerBoost(call, "on") && result.ok && typeof coolingStartTemp === "number"
          ? `Cooler Boost online, thermal trace started at ${coolingStartTemp.toFixed(1)} C.`
          : result.ok
            ? result.stdout || "Command completed."
            : result.error ?? result.stderr ?? "Command failed.",
      status: result.ok ? "complete" : "blocked",
    });
  }
}
