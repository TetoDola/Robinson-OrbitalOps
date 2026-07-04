"use client";

import { useReveal } from "@/hooks/useReveal";

export function BridgeSection() {
  const ref = useReveal<HTMLElement>();

  return (
    <section ref={ref} className="reveal bg-white py-24 lg:py-36">
      <div className="site-container">
        <p className="mx-auto max-w-[62.5rem] text-center text-[clamp(1.75rem,4.2vw,3.25rem)] font-normal leading-[1.08] tracking-[-0.03em] text-[var(--c-dark-green)]">
          Imagine the yard as an intelligent bridge{" "}
          <span className="text-[var(--c-dark-gray)]">
            seamlessly connecting highway to warehouse.
          </span>
        </p>
      </div>
    </section>
  );
}
