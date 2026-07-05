import { useEffect, useMemo, useRef } from "react";
import { createPortal } from "react-dom";

import b200Url from "../../assets/b200.png";

export interface IrNodeTarget {
  id: string;
  status: string;
  tempC: number;
}

interface IRCamPopupProps {
  node: IrNodeTarget;
  anchor: { x: number; y: number };
  sourceImageUrl?: string | null;
  onClose: () => void;
}

interface IRCameraCanvasProps {
  node: IrNodeTarget;
  sourceImageUrl?: string | null;
  className?: string;
}

const IR_W = 320;
const IR_H = 262;
const POPUP_W = 344;
const POPUP_H = 396;
const AMBIENT_C = 21.5;
const FRAME_MS = 110;

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
  if (ironbowLut) {
    return ironbowLut;
  }
  const lut = new Uint8ClampedArray(256 * 3);
  for (let i = 0; i < 256; i += 1) {
    const t = i / 255;
    let hi = 1;
    while (hi < PALETTE_STOPS.length - 1 && PALETTE_STOPS[hi][0] < t) {
      hi += 1;
    }
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

const imagePromises = new Map<string, Promise<HTMLImageElement | null>>();

function loadImage(source: string): Promise<HTMLImageElement | null> {
  const cached = imagePromises.get(source);
  if (cached) {
    return cached;
  }
  const promise = new Promise<HTMLImageElement | null>((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = source;
  });
  imagePromises.set(source, promise);
  return promise;
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
  const vrmAmp = 0.3 * (0.45 + 0.55 * severity);
  let max = 0;

  for (let yPx = 0; yPx < IR_H; yPx += 1) {
    const y = yPx / IR_H;
    for (let xPx = 0; xPx < IR_W; xPx += 1) {
      const x = xPx / IR_W;
      const i = yPx * IR_W + xPx;
      let v = 0.05 + (lum ? lum[i] * 0.24 : 0.1);
      v += gauss(x, y, 0.5, 0.47, 0.17, 0.15) * dieAmp;
      v += gauss(x, y, 0.5, 0.47, 0.34, 0.3) * 0.24;
      v += gauss(x, y, 0.085, 0.5, 0.055, 0.34) * vrmAmp;
      v += gauss(x, y, 0.915, 0.5, 0.055, 0.34) * vrmAmp;
      v += gauss(x, y, 0.5, 0.96, 0.3, 0.045) * 0.16;
      heat[i] = v;
      if (v > max) {
        max = v;
      }
    }
  }

  for (let i = 0; i < heat.length; i += 1) {
    heat[i] = Math.min(1, heat[i] / max);
  }
  return heat;
}

function drawOverlay(ctx: CanvasRenderingContext2D, spotTempC: number, elapsedS: number) {
  const cx = IR_W * 0.5;
  const cy = IR_H * 0.47;

  const sweepY = ((elapsedS * 34) % (IR_H + 40)) - 20;
  ctx.fillStyle = "rgba(255, 255, 255, 0.045)";
  ctx.fillRect(0, sweepY, IR_W, 3);

  ctx.strokeStyle = "rgba(255, 255, 255, 0.92)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(cx - 14, cy);
  ctx.lineTo(cx - 5, cy);
  ctx.moveTo(cx + 5, cy);
  ctx.lineTo(cx + 14, cy);
  ctx.moveTo(cx, cy - 14);
  ctx.lineTo(cx, cy - 5);
  ctx.moveTo(cx, cy + 5);
  ctx.lineTo(cx, cy + 14);
  ctx.stroke();
  ctx.strokeRect(cx - 2.5, cy - 2.5, 5, 5);

  ctx.font = "11px 'Geist Mono', Consolas, monospace";
  const label = `${spotTempC.toFixed(1)}\u00b0C MAX`;
  const textWidth = ctx.measureText(label).width;
  ctx.fillStyle = "rgba(0, 0, 0, 0.55)";
  ctx.fillRect(cx + 16, cy - 19, textWidth + 10, 16);
  ctx.fillStyle = "#ffffff";
  ctx.fillText(label, cx + 21, cy - 7);

  ctx.strokeStyle = "rgba(255, 255, 255, 0.5)";
  for (const [bx, by, dx, dy] of [
    [6, 6, 1, 1],
    [IR_W - 6, 6, -1, 1],
    [6, IR_H - 6, 1, -1],
    [IR_W - 6, IR_H - 6, -1, -1],
  ]) {
    ctx.beginPath();
    ctx.moveTo(bx + dx * 10, by);
    ctx.lineTo(bx, by);
    ctx.lineTo(bx, by + dy * 10);
    ctx.stroke();
  }

  ctx.fillStyle = "rgba(255, 255, 255, 0.6)";
  ctx.fillText("IR-01 9Hz NR", 12, 20);
}

export function IRCameraCanvas({ node, sourceImageUrl, className = "ir-canvas" }: IRCameraCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) {
      return undefined;
    }

    const severity = Math.min(1, Math.max(0, (node.tempC - 45) / 50));
    const lut = getIronbowLut();
    const frame = ctx.createImageData(IR_W, IR_H);
    const px = frame.data;
    let heat: Float32Array | null = null;
    let timer = 0;
    let cancelled = false;
    const startedAt = performance.now();

    const render = () => {
      if (!heat) {
        return;
      }
      const elapsedS = (performance.now() - startedAt) / 1000;
      const flicker = Math.sin(elapsedS * 2.4) * 0.012;
      for (let i = 0; i < heat.length; i += 1) {
        const v = heat[i] + (Math.random() - 0.5) * 0.045 + flicker;
        const idx = (v <= 0 ? 0 : v >= 1 ? 255 : (v * 255) | 0) * 3;
        const p = i * 4;
        px[p] = lut[idx];
        px[p + 1] = lut[idx + 1];
        px[p + 2] = lut[idx + 2];
        px[p + 3] = 255;
      }
      ctx.putImageData(frame, 0, 0);
      const spotTemp = node.tempC + Math.sin(elapsedS * 1.7) * 0.3 + (Math.random() - 0.5) * 0.2;
      drawOverlay(ctx, spotTemp, elapsedS);
    };

    void loadImage(sourceImageUrl || b200Url).then((image) => {
      if (cancelled) {
        return;
      }
      heat = buildHeatField(image, severity);
      render();
      timer = window.setInterval(render, FRAME_MS);
    });

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [node.id, node.tempC, sourceImageUrl]);

  return <canvas className={className} height={IR_H} ref={canvasRef} width={IR_W} />;
}

export default function IRCamPopup({ node, anchor, sourceImageUrl, onClose }: IRCamPopupProps) {
  const popupRef = useRef<HTMLDivElement | null>(null);

  const style = useMemo(() => {
    let left = anchor.x - POPUP_W - 18;
    if (left < 12) {
      left = Math.min(anchor.x + 18, window.innerWidth - POPUP_W - 12);
    }
    const top = Math.min(
      Math.max(anchor.y - POPUP_H * 0.4, 12),
      Math.max(12, window.innerHeight - POPUP_H - 12),
    );
    return { left: `${left}px`, top: `${top}px` };
  }, [anchor]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
      }
    };
    // Capture phase so Escape closes only the popup, not the scene's inspection panel.
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [onClose]);

  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (popupRef.current?.contains(target)) {
        return;
      }
      // Node rows manage the popup themselves (toggle / switch node).
      if (target instanceof Element && target.closest(".node-row.is-clickable")) {
        return;
      }
      onClose();
    };
    document.addEventListener("pointerdown", onPointerDown, true);
    return () => document.removeEventListener("pointerdown", onPointerDown, true);
  }, [onClose]);

  return createPortal(
    <>
      <div className="ir-popup" ref={popupRef} style={style} role="dialog" aria-label={`IR thermal view of ${node.id}`}>
        <div className="ir-head">
          <div>
            <div className="eyebrow">ir thermal cam</div>
            <strong className="ir-title">{node.id.replace(/[_-]+/g, " ")}</strong>
          </div>
          <span className="ir-live">
            <span className="ir-live-dot" />
            live
          </span>
          <button className="close-btn" aria-label="Close IR view" onClick={onClose} type="button">
            &times;
          </button>
        </div>
        <IRCameraCanvas node={node} sourceImageUrl={sourceImageUrl} />
        <div className="ir-scale" aria-label="Temperature scale">
          <span>{AMBIENT_C.toFixed(0)}&deg;C</span>
          <span className="ir-scale-bar" />
          <span>{node.tempC.toFixed(1)}&deg;C</span>
        </div>
        <div className="ir-foot">
          <span>{node.status.replace(/[_-]+/g, " ")}</span>
          <span>&epsilon; 0.95 &middot; B200 SXM</span>
        </div>
      </div>
    </>,
    document.body,
  );
}
