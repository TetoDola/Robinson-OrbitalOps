"use client";

import { useReveal } from "@/hooks/useReveal";

export function YosStatement() {
  const ref = useReveal<HTMLElement>();

  return (
    <section
      ref={ref}
      className="reveal relative overflow-hidden bg-[var(--c-dark-green)] py-28 text-white lg:py-44"
    >
      <div className="site-container relative z-10 text-center">
        <p className="mx-auto max-w-4xl text-[clamp(2rem,5vw,3.75rem)] font-normal leading-[1.05] tracking-[-0.03em]">
          That&apos;s the{" "}
          <span className="text-[var(--c-lime)]">Yard Operating System.</span>
        </p>

        <div
          aria-hidden
          className="mt-14 select-none text-[clamp(5rem,22vw,20rem)] font-medium leading-none tracking-[-0.04em] text-white/[0.06]"
        >
          YOS<sup className="text-[0.35em] align-super">™</sup>
        </div>
      </div>
    </section>
  );
}
