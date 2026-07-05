"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";

const STEPS = [
  "Autonomous multi-agent operations across the whole datacenter",
  "Real-time adaptation to radiation, heat, power and downlink",
  "Human approval on every critical action",
  "One command center for the entire orbital fleet",
] as const;

// One image per capacity, shown in the masked right panel (same order as STEPS).
const STEP_IMAGES = [
  "/images/features/capacity-1.jpg",
  "/images/features/capacity-2.jpg",
  "/images/features/capacity-3.jpg",
  "/images/features/capacity-4.jpg",
] as const;

// Panel geometry for the concave notch cut into the LEFT edge (viewBox 0 0 687 830).
const PANEL_W = 687;
const PANEL_H = 830;
const NOTCH_DEPTH = 30; // how far the notch indents from the left edge
const NOTCH_T = 44; // length of the smooth S-transition in/out of the notch

/**
 * Builds the mask path for progress `p` (0..1). The notch center travels from
 * ~12% to ~88% of the height, and its size peaks in the middle (sine curve),
 * shrinking near the top and bottom — matching the original's scroll animation.
 */
function notchMaskUrl(p: number) {
  const cy = 100 + 630 * p; // center Y: 12% → 88%
  const hh = 35 + 145 * Math.sin(Math.PI * p); // half-height: 35 (ends) → 180 (middle)
  const bot = cy + hh;
  const topN = cy - hh;
  const D = NOTCH_DEPTH;
  const T = NOTCH_T;
  const f = (n: number) => n.toFixed(1);
  const path =
    `M 0 0 L ${PANEL_W} 0 L ${PANEL_W} ${PANEL_H} L 0 ${PANEL_H} ` +
    `L 0 ${f(bot + T)} C 0 ${f(bot + T * 0.45)} ${D} ${f(bot + T * 0.55)} ${D} ${f(bot)} ` +
    `L ${D} ${f(topN)} C ${D} ${f(topN - T * 0.55)} 0 ${f(topN - T * 0.45)} 0 ${f(topN - T)} Z`;
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 ${PANEL_W} ${PANEL_H}' preserveAspectRatio='none'><path d='${path}' fill='#fff'/></svg>`;
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
}

const STEP = 30; // vh between phrase blocks
const ALIGN = 30; // vh offset of the active phrase from the top of the window (clears the fixed header)

export function FeaturesSteps() {
  const sectionRef = useRef<HTMLElement>(null);
  const [progress, setProgress] = useState(0); // continuous 0..STEPS-1

  useEffect(() => {
    let raf = 0;
    const onScroll = () => {
      const el = sectionRef.current;
      if (!el) return;
      const total = el.offsetHeight - window.innerHeight;
      const raw = Math.min(1, Math.max(0, -el.getBoundingClientRect().top / Math.max(1, total)));
      // Complete the animation by ~88% of the scroll, then hold the final
      // state so the notch-at-bottom + last step are fully visible before the
      // next section slides in.
      const p = Math.min(1, raw / 0.88);
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => setProgress(p * (STEPS.length - 1)));
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  const active = Math.round(progress);
  const stepNum = active + 1;
  const maskP = STEPS.length > 1 ? progress / (STEPS.length - 1) : 0;
  const maskUrl = notchMaskUrl(maskP);
  const maskStyle = {
    maskImage: maskUrl,
    WebkitMaskImage: maskUrl,
    maskSize: "100% 100%",
    WebkitMaskSize: "100% 100%",
    maskRepeat: "no-repeat",
    WebkitMaskRepeat: "no-repeat",
  } as const;

  return (
    <section ref={sectionRef} className="relative bg-white" style={{ height: "280vh" }}>
      <div className="sticky top-0 flex h-screen items-center overflow-hidden">
        <div className="site-container flex w-full items-center justify-between gap-10">
          {/* Left: odometer + scrolling phrases */}
          <div className="relative h-screen flex-1">
            {/* Odometer (small, light-gray, far left) */}
            <div className="absolute left-0 top-[44vh] font-mono text-[10px] leading-none tracking-[0.1em] text-[var(--c-light-gray)]">
              <div className="flex h-[10px] items-center overflow-hidden">
                <span>0</span>
                <span className="relative inline-block h-[10px] w-[6px] overflow-hidden">
                  <span
                    className="absolute left-0 top-0 flex flex-col transition-transform duration-500 ease-[cubic-bezier(0.16,1,0.3,1)]"
                    style={{ transform: `translateY(-${(stepNum % 10) * 10}px)` }}
                  >
                    {Array.from({ length: 10 }).map((_, d) => (
                      <span key={d} className="block h-[10px] leading-[10px]">
                        {d}
                      </span>
                    ))}
                  </span>
                </span>
              </div>
              <span className="mt-1 block text-[var(--c-light-light-gray)]">/04</span>
            </div>

            {/* Phrase window with fade mask */}
            <div
              className="ml-[64px] h-screen"
              style={{
                maskImage:
                  "linear-gradient(to bottom, transparent 20%, #000 34%, #000 56%, transparent 76%)",
                WebkitMaskImage:
                  "linear-gradient(to bottom, transparent 20%, #000 34%, #000 56%, transparent 76%)",
              }}
            >
              <div
                className="transition-transform duration-100 ease-linear"
                style={{ transform: `translateY(calc(${ALIGN}vh - ${progress * STEP}vh))` }}
              >
                {STEPS.map((step) => (
                  <div key={step} className="flex items-center" style={{ height: `${STEP}vh` }}>
                    <p className="max-w-[430px] text-[clamp(1.5rem,2.4vw,2.156rem)] font-[450] leading-[1.2] tracking-[-0.018em] text-[var(--c-dark-green)]">
                      {step}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Right: notch-masked video panel */}
          <div
            className="relative hidden aspect-[687/830] w-[687px] max-w-[48%] shrink-0 self-start bg-[var(--c-dark-green)] lg:block"
            style={{ marginTop: "35px", ...maskStyle }}
          >
            {STEP_IMAGES.map((src, i) => (
              <Image
                key={src}
                src={src}
                alt=""
                fill
                sizes="687px"
                priority={i === 0}
                className={`object-cover transition-opacity duration-700 ${
                  i === active ? "opacity-100" : "opacity-0"
                }`}
              />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
