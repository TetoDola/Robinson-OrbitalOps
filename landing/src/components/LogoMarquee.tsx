"use client";

import Image from "next/image";
import { useReveal } from "@/hooks/useReveal";

export function LogoMarquee() {
  const ref = useReveal<HTMLElement>();

  return (
    <section ref={ref} className="reveal bg-white py-20 lg:py-24">
      <div className="site-container flex flex-col items-center gap-7">
        <p className="eyebrow text-[var(--c-dark-gray)]">Powered by</p>
        <Image
          src="/images/crusoe.webp"
          alt="Crusoe"
          width={635}
          height={157}
          className="h-9 w-auto object-contain lg:h-11"
          priority={false}
        />
      </div>
    </section>
  );
}
