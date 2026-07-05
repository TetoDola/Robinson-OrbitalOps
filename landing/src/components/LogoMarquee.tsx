"use client";

import Image from "next/image";
import { useReveal } from "@/hooks/useReveal";

const BRANDS = [
  { src: "/images/brands/dsv.svg", alt: "DSV", w: 90 },
  { src: "/images/brands/lineage.svg", alt: "Lineage", w: 120 },
  { src: "/images/brands/goodyear.svg", alt: "Goodyear", w: 70 },
  { src: "/images/brands/ocean-spray.svg", alt: "Ocean Spray", w: 110 },
  { src: "/images/brands/culligan.svg", alt: "Culligan", w: 130 },
  { src: "/images/brands/nfi.svg", alt: "NFI", w: 80 },
  { src: "/images/brands/ryder.svg", alt: "Ryder", w: 100 },
  { src: "/images/brands/hp.svg", alt: "HP", w: 46 },
  { src: "/images/brands/tjx.svg", alt: "TJX", w: 110 },
  { src: "/images/brands/prologis.svg", alt: "Prologis", w: 130 },
  { src: "/images/brands/vince.png", alt: "Vince", w: 100 },
] as const;

export function LogoMarquee() {
  const ref = useReveal<HTMLElement>();
  const loop = [...BRANDS, ...BRANDS];

  return (
    <section ref={ref} className="reveal bg-white py-20 lg:py-24">
      <div className="site-container">
        <h2 className="mx-auto max-w-3xl text-center text-[clamp(1.5rem,2.6vw,2.125rem)] font-normal leading-tight tracking-[-0.02em] text-[var(--c-dark-green)]">
          Keeping compute alive for the teams building in orbit
        </h2>
      </div>

      <div className="relative mt-14 overflow-hidden [mask-image:linear-gradient(90deg,transparent,black_10%,black_90%,transparent)]">
        <div className="flex w-max animate-marquee items-center gap-16 pr-16">
          {loop.map((b, i) => (
            <div key={`${b.alt}-${i}`} className="flex h-12 shrink-0 items-center">
              <Image
                src={b.src}
                alt={b.alt}
                width={b.w}
                height={48}
                className="h-full w-auto max-w-none object-contain opacity-45 grayscale transition-all duration-300 hover:opacity-100 hover:grayscale-0"
                style={{ width: b.w }}
              />
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
