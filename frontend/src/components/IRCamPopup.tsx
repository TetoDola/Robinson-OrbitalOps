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

interface ThermalField {
  heat: Float32Array;
  hotspotX: number;
  hotspotY: number;
}

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

function smoothstep(edge0: number, edge1: number, value: number) {
  const t = Math.max(0, Math.min(1, (value - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}

function rectInfluence(x: number, y: number, cx: number, cy: number, halfW: number, halfH: number, feather: number) {
  const dx = Math.abs(x - cx) - halfW;
  const dy = Math.abs(y - cy) - halfH;
  const outside = Math.hypot(Math.max(dx, 0), Math.max(dy, 0));
  return 1 - smoothstep(0, feather, outside);
}

function isGoldContact(r: number, g: number, b: number) {
  return r > 138 && g > 92 && b < 82 && r > b * 1.55;
}

function componentHeat(x: number, y: number) {
  const centralDie = rectInfluence(x, y, 0.5, 0.49, 0.15, 0.16, 0.07);
  const packageSubstrate = rectInfluence(x, y, 0.5, 0.49, 0.23, 0.23, 0.08) * 0.44;
  const coldFrame = rectInfluence(x, y, 0.5, 0.49, 0.28, 0.29, 0.025) - rectInfluence(x, y, 0.5, 0.49, 0.24, 0.24, 0.025);

  let memory = 0;
  memory = Math.max(memory, rectInfluence(x, y, 0.5, 0.09, 0.31, 0.08, 0.045));
  memory = Math.max(memory, rectInfluence(x, y, 0.5, 0.87, 0.31, 0.08, 0.045));
  memory = Math.max(memory, rectInfluence(x, y, 0.19, 0.49, 0.07, 0.28, 0.045));
  memory = Math.max(memory, rectInfluence(x, y, 0.81, 0.49, 0.07, 0.28, 0.045));

  const leftPower = rectInfluence(x, y, 0.08, 0.47, 0.08, 0.41, 0.07);
  const rightPower = rectInfluence(x, y, 0.92, 0.47, 0.08, 0.41, 0.07);
  const connector = rectInfluence(x, y, 0.5, 0.985, 0.49, 0.02, 0.03);

  return (
    centralDie * 0.78 +
    packageSubstrate +
    memory * 0.38 +
    Math.max(leftPower, rightPower) * 0.3 +
    connector * 0.12 -
    coldFrame * 0.2
  );
}

function drawBoardBase(ctx: CanvasRenderingContext2D, image: HTMLImageElement | null) {
  ctx.clearRect(0, 0, IR_W, IR_H);
  if (image) {
    ctx.save();
    ctx.filter = "grayscale(0.25) contrast(1.2) brightness(0.78)";
    ctx.drawImage(image, 0, 0, IR_W, IR_H);
    ctx.restore();
  } else {
    ctx.fillStyle = "rgb(7, 12, 18)";
    ctx.fillRect(0, 0, IR_W, IR_H);
  }

  ctx.globalCompositeOperation = "source-over";
  ctx.fillStyle = "rgba(0, 0, 0, 0.12)";
  ctx.fillRect(0, 0, IR_W, IR_H);
}

function stampBoardDetail(ctx: CanvasRenderingContext2D, image: HTMLImageElement | null) {
  if (!image) {
    return;
  }
  ctx.save();
  ctx.globalAlpha = 0.34;
  ctx.filter = "grayscale(1) contrast(1.75) brightness(1.08)";
  ctx.drawImage(image, 0, 0, IR_W, IR_H);
  ctx.restore();
}

function buildHeatField(image: HTMLImageElement | null, severity: number): ThermalField {
  const heat = new Float32Array(IR_W * IR_H);
  let sourceData: Uint8ClampedArray | null = null;
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
        sourceData = data;
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

  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  let hotspotX = IR_W * 0.5;
  let hotspotY = IR_H * 0.49;

  for (let yPx = 0; yPx < IR_H; yPx += 1) {
    const y = yPx / IR_H;
    for (let xPx = 0; xPx < IR_W; xPx += 1) {
      const x = xPx / IR_W;
      const i = yPx * IR_W + xPx;
      const p = i * 4;
      const r = sourceData?.[p] ?? 18;
      const g = sourceData?.[p + 1] ?? 22;
      const b = sourceData?.[p + 2] ?? 28;
      const l = lum?.[i] ?? 0.12;
      const darkComponent = smoothstep(0.34, 0.08, l);
      const metal = smoothstep(0.46, 0.8, l);
      const copper = isGoldContact(r, g, b) ? 1 : 0;
      const edgeTexture = Math.abs((lum?.[Math.max(0, i - 1)] ?? l) - l) + Math.abs((lum?.[Math.max(0, i - IR_W)] ?? l) - l);
      const regionHeat = componentHeat(x, y);
      let v = 0.11 + regionHeat * (0.52 + severity * 0.58);
      v += darkComponent * regionHeat * 0.42;
      v += edgeTexture * 0.58;
      v += gauss(x, y, 0.5, 0.49, 0.12, 0.12) * severity * 0.22;
      v -= metal * 0.16;
      v -= copper * 0.08;
      v += Math.sin((x * 18 + y * 11) * Math.PI) * 0.012;
      heat[i] = v;
      min = Math.min(min, v);
      if (v > max) {
        max = v;
        hotspotX = xPx;
        hotspotY = yPx;
      }
    }
  }

  const range = Math.max(0.001, max - min);
  for (let i = 0; i < heat.length; i += 1) {
    heat[i] = Math.max(0, Math.min(1, (heat[i] - min) / range));
  }
  return { heat, hotspotX, hotspotY };
}

function drawOverlay(ctx: CanvasRenderingContext2D, spotTempC: number, elapsedS: number, hotspotX: number, hotspotY: number) {
  const cx = hotspotX;
  const cy = hotspotY;
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
  const labelX = Math.min(cx + 21, IR_W - textWidth - 12);
  const labelY = Math.max(18, cy - 7);
  ctx.fillStyle = "rgba(0, 0, 0, 0.55)";
  ctx.fillRect(labelX - 5, labelY - 12, textWidth + 10, 16);
  ctx.fillStyle = "#ffffff";
  ctx.fillText(label, labelX, labelY);

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

export async function renderIrFrameDataUrl(node: IrNodeTarget, sourceImageUrl?: string | null): Promise<string | null> {
  const canvas = document.createElement("canvas");
  canvas.width = IR_W;
  canvas.height = IR_H;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  const boardSourceUrl = sourceImageUrl?.startsWith("data:image/") ? b200Url : sourceImageUrl || b200Url;
  const image = await loadImage(boardSourceUrl);
  const severity = Math.min(1, Math.max(0, (node.tempC - 45) / 50));
  const field = buildHeatField(image, severity);
  const lut = getIronbowLut();

  const overlay = document.createElement("canvas");
  overlay.width = IR_W;
  overlay.height = IR_H;
  const overlayCtx = overlay.getContext("2d");
  if (!overlayCtx) return null;
  const frame = overlayCtx.createImageData(IR_W, IR_H);
  const px = frame.data;
  for (let i = 0; i < field.heat.length; i += 1) {
    const v = field.heat[i];
    const idx = (v <= 0 ? 0 : v >= 1 ? 255 : (v * 255) | 0) * 3;
    const p = i * 4;
    px[p] = lut[idx];
    px[p + 1] = lut[idx + 1];
    px[p + 2] = lut[idx + 2];
    px[p + 3] = Math.max(122, Math.min(232, 142 + v * 86));
  }

  drawBoardBase(ctx, image);
  overlayCtx.putImageData(frame, 0, 0);
  ctx.drawImage(overlay, 0, 0);
  stampBoardDetail(ctx, image);
  drawOverlay(ctx, node.tempC, 0, field.hotspotX, field.hotspotY);

  try {
    return canvas.toDataURL("image/png");
  } catch {
    return null;
  }
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
    const overlay = document.createElement("canvas");
    overlay.width = IR_W;
    overlay.height = IR_H;
    const overlayCtx = overlay.getContext("2d");
    if (!overlayCtx) {
      return undefined;
    }

    const lut = getIronbowLut();
    const frame = overlayCtx.createImageData(IR_W, IR_H);
    const px = frame.data;
    let baseImage: HTMLImageElement | null = null;
    let thermalField: ThermalField | null = null;
    let timer = 0;
    let cancelled = false;
    const startedAt = performance.now();
    const boardSourceUrl = sourceImageUrl?.startsWith("data:image/") ? b200Url : sourceImageUrl || b200Url;

    const render = () => {
      if (!thermalField) {
        return;
      }
      const { heat, hotspotX, hotspotY } = thermalField;
      const elapsedS = (performance.now() - startedAt) / 1000;
      const flicker = Math.sin(elapsedS * 2.4) * 0.012;
      for (let i = 0; i < heat.length; i += 1) {
        const v = heat[i] + (Math.random() - 0.5) * 0.045 + flicker;
        const idx = (v <= 0 ? 0 : v >= 1 ? 255 : (v * 255) | 0) * 3;
        const p = i * 4;
        px[p] = lut[idx];
        px[p + 1] = lut[idx + 1];
        px[p + 2] = lut[idx + 2];
        px[p + 3] = Math.max(122, Math.min(232, 142 + v * 86));
      }
      drawBoardBase(ctx, baseImage);
      overlayCtx.putImageData(frame, 0, 0);
      ctx.globalCompositeOperation = "source-over";
      ctx.drawImage(overlay, 0, 0);
      ctx.globalCompositeOperation = "source-over";
      stampBoardDetail(ctx, baseImage);
      const spotTemp = node.tempC + Math.sin(elapsedS * 1.7) * 0.3 + (Math.random() - 0.5) * 0.2;
      drawOverlay(ctx, spotTemp, elapsedS, hotspotX, hotspotY);
    };

    void loadImage(boardSourceUrl).then((image) => {
      if (cancelled) {
        return;
      }
      baseImage = image;
      thermalField = buildHeatField(image, severity);
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
