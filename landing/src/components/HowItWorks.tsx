"use client";

import { useReveal } from "@/hooks/useReveal";
import { ArrowRightIcon } from "@/components/icons";

export function HowItWorks() {
  const ref = useReveal<HTMLElement>();

  return (
    <section ref={ref} className="reveal bg-white py-24 lg:py-36">
      <div className="site-container">
        <div className="mx-auto max-w-4xl text-center">
          <span className="eyebrow text-[var(--c-dark-gray)]">How it Works</span>
          <h2 className="mt-6 text-[clamp(1.75rem,4vw,3.25rem)] font-normal leading-[1.08] tracking-[-0.03em] text-[var(--c-dark-green)]">
            Revolutionary technology that transforms your yard from gate to dock
          </h2>
          <a
            href="/system"
            className="group mt-10 inline-flex items-center gap-3 rounded-lg bg-[var(--c-dark-green)] px-8 py-4 font-mono text-[11px] font-semibold uppercase tracking-[1.5px] text-white transition-colors hover:bg-[var(--c-lime)] hover:text-[var(--c-dark-green)]"
          >
            Take a closer look
            <ArrowRightIcon className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
          </a>
        </div>
      </div>
    </section>
  );
}
