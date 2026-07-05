import { useEffect, useRef } from "react";

import b200Url from "../../../assets/b200.png";

const IR_W = 200;
const IR_H = 164;
const FRAME_MS = 120;

const PALETTE_STOPS: Array<[number, [number, number, number]]> = [
  [0.0, [4, 2, 36]],
  [0.18, [48, 8, 108]],
  [0.38, [150, 22, 118]],
  [0.55, [214, 82, 24]],
  [0.72, [244, 154, 12]],
  [0.88, [252, 216, 84]],
  [1.0, [255, 255, 255]],
];

let ironbowLut: Uint8ClampedArray | null = null;

function getIronbowLut(): Uint8ClampedArray {
  if (ironbowLut) return ironbowLut;
  const lut = new Uint8ClampedArray(256 * 3);
  for (let i = 0; i < 256; i += 1) {
    const t = i / 255;
    let hi = 1;
    while (hi < PALETTE_STOPS.length - 1 && PALETTE_STOPS[hi][0] < t) hi += 1;
    const [t0, c0] = PALETTE_STOPS[hi - 1];
    const [t1, c1] = PALETTE_STOPS[hi];
    const f = (t - t0) / (t1 - t0);
    lut[i * 3] = c0[0] + (c1[0] - c0[0]) * f;
    lut[i * 3 + 1] = c0[1] + (c1[1] - c0[1]) * f;
    lut[i * 3 + 2] = c0[2] + (c1[2] - c0[2]) * f;
  }
  ironbowLut = lut;
  return lut;
}

let boardImagePromise: Promise<HTMLImageElement | null> | null = null;

function loadBoardImage(): Promise<HTMLImageElement | null> {
  if (!boardImagePromise) {
    boardImagePromise = new Promise((resolve) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => resolve(null);
      img.src = b200Url;
    });
  }
  return boardImagePromise;
}

function gauss(x: number, y: number, cx: number, cy: number, sx: number, sy: number) {
  const dx = (x - cx) / sx;
  const dy = (y - cy) / sy;
  return Math.exp(-(dx * dx + dy * dy));
}

function buildHeatField(image: HTMLImageElement | null, severity: number): Float32Array {
  const heat = new Float32Array(IR_W * IR_H);
  let lum: Float32Array | null = null;

  if (image) {
    try {
      const off = document.createElement("canvas");
      off.width = IR_W;
      off.height = IR_H;
      const ctx = off.getContext("2d");
      if (ctx) {
        ctx.drawImage(image, 0, 0, IR_W, IR_H);
        const data = ctx.getImageData(0, 0, IR_W, IR_H).data;
        lum = new Float32Array(IR_W * IR_H);
        for (let i = 0; i < lum.length; i += 1) {
          const p = i * 4;
          lum[i] = (data[p] * 0.2126 + data[p + 1] * 0.7152 + data[p + 2] * 0.0722) / 255;
        }
      }
    } catch {
      lum = null;
    }
  }

  const dieAmp = 0.55 + 0.45 * severity;
  let max = 0;
  for (let yPx = 0; yPx < IR_H; yPx += 1) {
    const y = yPx / IR_H;
    for (let xPx = 0; xPx < IR_W; xPx += 1) {
      const x = xPx / IR_W;
      const i = yPx * IR_W + xPx;
      let v = 0.05 + (lum ? lum[i]! * 0.24 : 0.1);
      v += gauss(x, y, 0.5, 0.47, 0.17, 0.15) * dieAmp;
      v += gauss(x, y, 0.5, 0.47, 0.34, 0.3) * 0.24;
      heat[i] = v;
      if (v > max) max = v;
    }
  }
  for (let i = 0; i < heat.length; i += 1) {
    heat[i] = Math.min(1, heat[i]! / max);
  }
  return heat;
}

interface InlineIrCanvasProps {
  tempC: number;
  className?: string;
}

export default function InlineIrCanvas({ tempC, className }: InlineIrCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return undefined;

    const severity = Math.min(1, Math.max(0, (tempC - 45) / 50));
    const lut = getIronbowLut();
    const frame = ctx.createImageData(IR_W, IR_H);
    const px = frame.data;
    let heat: Float32Array | null = null;
    let timer = 0;
    let cancelled = false;
    const startedAt = performance.now();

    const render = () => {
      if (!heat) return;
      const elapsedS = (performance.now() - startedAt) / 1000;
      const flicker = Math.sin(elapsedS * 2.4) * 0.012;
      for (let i = 0; i < heat.length; i += 1) {
        const v = heat[i]! + (Math.random() - 0.5) * 0.045 + flicker;
        const idx = (v <= 0 ? 0 : v >= 1 ? 255 : (v * 255) | 0) * 3;
        const p = i * 4;
        px[p] = lut[idx]!;
        px[p + 1] = lut[idx + 1]!;
        px[p + 2] = lut[idx + 2]!;
        px[p + 3] = 255;
      }
      ctx.putImageData(frame, 0, 0);
      const spot = tempC + Math.sin(elapsedS * 1.7) * 0.3;
      ctx.font = "10px 'Geist Mono', Consolas, monospace";
      const label = `${spot.toFixed(1)}°C MAX`;
      const tw = ctx.measureText(label).width;
      ctx.fillStyle = "rgba(0,0,0,0.55)";
      ctx.fillRect(IR_W * 0.5 + 8, IR_H * 0.47 - 14, tw + 8, 14);
      ctx.fillStyle = "#fff";
      ctx.fillText(label, IR_W * 0.5 + 12, IR_H * 0.47 - 4);
    };

    void loadBoardImage().then((image) => {
      if (cancelled) return;
      heat = buildHeatField(image, severity);
      render();
      timer = window.setInterval(render, FRAME_MS);
    });

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [tempC]);

  return (
    <canvas
      className={className ?? "chat-evidence-ir-canvas"}
      height={IR_H}
      ref={canvasRef}
      width={IR_W}
    />
  );
}
