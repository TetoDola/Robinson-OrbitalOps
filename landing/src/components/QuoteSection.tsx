"use client";

import { useReveal } from "@/hooks/useReveal";
import { QuoteMarkIcon } from "@/components/icons";

export function QuoteSection() {
  const ref = useReveal<HTMLElement>();

  return (
    <section ref={ref} className="reveal relative overflow-hidden bg-[var(--c-dark-green)] text-white">
      {/* Background image */}
      <div
        aria-hidden
        className="absolute inset-0 bg-cover bg-center opacity-25"
        style={{ backgroundImage: "url(/images/sections/quote-image.webp)" }}
      />
      <div className="absolute inset-0 bg-[var(--c-dark-green)]/60" />

      <div className="site-container relative z-10 py-28 lg:py-40">
        <div className="mx-auto max-w-4xl text-center">
          <QuoteMarkIcon className="mx-auto h-9 w-12 text-[var(--c-lime)]" />
          <blockquote className="mt-8 text-[clamp(1.5rem,3.4vw,2.75rem)] font-normal leading-[1.15] tracking-[-0.02em]">
            We have not seen this kind of accuracy with computer-vision technology&hellip; this is a significant milestone in the race to modernize the yard.
          </blockquote>
          <figcaption className="mt-10">
            <div className="text-lg font-medium">Karen Jones</div>
            <div className="mt-1 text-sm text-white/60">
              Head of New Product, Ryder System, Inc.
            </div>
          </figcaption>
        </div>
      </div>
    </section>
  );
}
