"use client";

import { useEffect, useRef, useState } from "react";

const BENEFITS = [
  {
    eyebrow: "Benefit 01",
    title: "A single solution for maximum, automated throughput",
    body: "Deep integrations anticipate incoming loads, enabling our AI computer vision technology to automate gate check-ins and all critical yard operations: from assigning locations and maintaining real-time visibility to coordinating spotters for efficient load movement. It then closes the loop by validating assets before exit, providing comprehensive performance supervision across your entire yard network.",
    video: "/videos/benefit-1-wide.mp4",
  },
  {
    eyebrow: "Benefit 02",
    title: "Easy, scalable operation",
    body: "Terminal was designed from the ground up for disruption-free operations. Easy to deploy and support, the system has a low IT lift with no 3rd party devices to support, and a modern UI/UX that's super-easy for operators to use from day one. Configurable to your yard, Terminal YOS integrates seamlessly with most TMS and WMS systems.",
    video: "/videos/benefit-2-vert.mp4",
  },
  {
    eyebrow: "Benefit 03",
    title: "Cost-effective, priced as a service",
    body: "We know that yard operations run on lean budgets, which is why we price our all-inclusive solution as a service with terms that won't bust the bank. Ready to deploy right away, and rapid to scale over time.",
    video: "/videos/benefit-3-wide.mp4",
  },
] as const;

export function BenefitsSection() {
  const sectionRef = useRef<HTMLElement>(null);
  const [active, setActive] = useState(0);

  useEffect(() => {
    const onScroll = () => {
      const el = sectionRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const total = el.offsetHeight - window.innerHeight;
      const progress = Math.min(1, Math.max(0, -rect.top / Math.max(1, total)));
      const idx = Math.min(BENEFITS.length - 1, Math.floor(progress * BENEFITS.length));
      setActive(idx);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  return (
    <section
      ref={sectionRef}
      className="relative bg-[var(--c-dark-green)]"
      style={{ height: `${BENEFITS.length * 100}vh` }}
    >
      <div className="sticky top-0 h-screen overflow-hidden">
        {/* Background videos */}
        {BENEFITS.map((b, i) => (
          <video
            key={b.video}
            className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-700 ${
              i === active ? "opacity-100" : "opacity-0"
            }`}
            src={b.video}
            autoPlay
            muted
            loop
            playsInline
          />
        ))}
        <div className="absolute inset-0 bg-gradient-to-t from-[var(--c-dark-green)] via-[var(--c-dark-green)]/70 to-[var(--c-dark-green)]/30" />

        {/* Text overlay */}
        <div className="site-container relative z-10 flex h-full items-end pb-20 lg:pb-28">
          <div className="max-w-2xl text-white">
            <div className="flex items-center gap-4">
              <span className="eyebrow text-[var(--c-lime)]">
                {BENEFITS[active].eyebrow}
              </span>
              <span className="font-mono text-sm text-white/40">
                {String(active + 1).padStart(2, "0")} / {String(BENEFITS.length).padStart(2, "0")}
              </span>
            </div>
            <h3 className="mt-5 text-[clamp(1.75rem,4vw,3rem)] font-normal leading-[1.05] tracking-[-0.03em]">
              {BENEFITS[active].title}
            </h3>
            <p className="mt-6 max-w-xl text-base leading-relaxed text-white/70 lg:text-lg">
              {BENEFITS[active].body}
            </p>
          </div>
        </div>

        {/* Progress dots */}
        <div className="absolute bottom-10 right-6 z-10 flex flex-col gap-2 lg:right-12">
          {BENEFITS.map((b, i) => (
            <span
              key={b.eyebrow}
              className={`h-8 w-1 rounded-full transition-colors duration-500 ${
                i === active ? "bg-[var(--c-lime)]" : "bg-white/25"
              }`}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
