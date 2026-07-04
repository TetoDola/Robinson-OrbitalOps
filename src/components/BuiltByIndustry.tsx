"use client";

import Image from "next/image";
import { useReveal } from "@/hooks/useReveal";

const INVESTORS = [
  { src: "/images/investors/8vc.svg", alt: "8VC" },
  { src: "/images/investors/rac.svg", alt: "RAC" },
  { src: "/images/investors/pods.svg", alt: "PODS" },
  { src: "/images/investors/foxconn.svg", alt: "Foxconn" },
  { src: "/images/investors/db-schenker.svg", alt: "DB Schenker" },
  { src: "/images/investors/nine-west.svg", alt: "Nine West" },
  { src: "/images/investors/marc-jacobs.svg", alt: "Marc Jacobs" },
  { src: "/images/investors/kirkland.svg", alt: "Kirkland" },
] as const;

export function BuiltByIndustry() {
  const ref = useReveal<HTMLElement>();

  return (
    <section ref={ref} className="reveal bg-white py-24 lg:py-32">
      <div className="site-container">
        <div className="mx-auto max-w-3xl text-center">
          <span className="eyebrow text-[var(--c-dark-gray)]">
            Built by the Industry
          </span>
          <h2 className="mt-5 text-[clamp(1.75rem,3.4vw,2.75rem)] font-normal leading-[1.1] tracking-[-0.025em] text-[var(--c-dark-green)]">
            Built by logistics leaders who want a new industry standard in the yard
          </h2>
        </div>

        <div className="mx-auto mt-16 grid max-w-5xl grid-cols-2 items-center gap-x-10 gap-y-12 sm:grid-cols-3 lg:grid-cols-4">
          {INVESTORS.map((inv) => (
            <div key={inv.alt} className="flex h-16 items-center justify-center">
              <Image
                src={inv.src}
                alt={inv.alt}
                width={150}
                height={64}
                className="h-full max-h-12 w-auto object-contain opacity-50 grayscale transition-all duration-300 hover:opacity-100 hover:grayscale-0"
              />
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
