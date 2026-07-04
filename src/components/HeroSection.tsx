"use client";

import { useEffect, useRef, useState } from "react";

const HEADLINES = [
  "We have reinvented the future of logistics through the yard.",
  "AI-native technology that turns manual tasks into connected missions.",
  "Moving the world by making goods flow.",
] as const;

// One clip per scroll segment — scrubbed (not autoplayed) so the whole
// hero feels like a single video driven by the scroll wheel.
const VIDEOS = [
  "/videos/hero-1.mp4",
  "/videos/hero-2.mp4",
  "/videos/hero-3.mp4",
] as const;

export function HeroSection() {
  const sectionRef = useRef<HTMLElement>(null);
  const videoRefs = useRef<(HTMLVideoElement | null)[]>([]);
  const [segment, setSegment] = useState(0);

  useEffect(() => {
    // Per-video target time we ease toward, for smooth scrubbing.
    const targets = new Array(VIDEOS.length).fill(0);
    let raf = 0;
    let running = true;

    const computeTargets = () => {
      const el = sectionRef.current;
      if (!el) return;
      const total = el.offsetHeight - window.innerHeight;
      const progress = Math.min(1, Math.max(0, -el.getBoundingClientRect().top / Math.max(1, total)));
      const scaled = progress * VIDEOS.length; // 0..N
      const seg = Math.min(VIDEOS.length - 1, Math.floor(scaled));
      setSegment(seg);

      VIDEOS.forEach((_, i) => {
        const local = Math.min(1, Math.max(0, scaled - i)); // this clip's progress
        const v = videoRefs.current[i];
        if (v && v.duration) targets[i] = local * v.duration;
      });
    };

    const onScroll = () => computeTargets();

    // Ease each video's currentTime toward its scroll-derived target.
    const tick = () => {
      if (!running) return;
      VIDEOS.forEach((_, i) => {
        const v = videoRefs.current[i];
        if (!v || !v.duration) return;
        const target = targets[i];
        const diff = target - v.currentTime;
        if (Math.abs(diff) > 0.01) {
          try {
            v.currentTime += diff * 0.2; // lerp toward target
          } catch {
            /* seeking not ready yet */
          }
        }
      });
      raf = requestAnimationFrame(tick);
    };

    computeTargets();
    raf = requestAnimationFrame(tick);
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      running = false;
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  return (
    <section ref={sectionRef} className="relative bg-[var(--c-dark-green)]" style={{ height: "300vh" }}>
      <div className="sticky top-0 flex h-screen flex-col overflow-hidden text-white">
        {/* Scroll-scrubbed video stack */}
        {VIDEOS.map((src, i) => (
          <video
            key={src}
            ref={(node) => {
              videoRefs.current[i] = node;
            }}
            className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-500 ${
              i === segment ? "opacity-100" : "opacity-0"
            }`}
            src={src}
            muted
            playsInline
            preload="auto"
          />
        ))}
        <div className="absolute inset-0 bg-gradient-to-b from-black/20 via-transparent to-[var(--c-dark-green)]/90" />

        {/* Scroll indicator */}
        <div className="pointer-events-none absolute right-6 top-1/2 z-10 hidden -translate-y-1/2 rotate-90 items-center gap-3 lg:flex">
          <span className="eyebrow text-white/70">Scroll to explore</span>
          <span className="h-px w-10 bg-white/50" />
        </div>

        {/* Headline (changes per segment) */}
        <div className="site-container relative z-10 mt-auto flex w-full items-end pb-16 lg:pb-[135px]">
          <div className="w-full max-w-[1100px]">
            {HEADLINES.map((line, i) => (
              <h1
                key={line}
                className={`font-normal leading-[0.95] tracking-[-0.045em] text-white transition-opacity duration-500 ease-in-out text-[clamp(2.5rem,7vw,4.375rem)] ${
                  i === segment ? "opacity-100" : "pointer-events-none absolute opacity-0"
                }`}
              >
                {line}
              </h1>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
