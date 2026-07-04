"use client";

import Image from "next/image";
import { TerminalLogo, ArrowRightIcon } from "@/components/icons";

const COLUMNS = [
  {
    heading: "Product",
    links: [
      "Yard Operating System",
      "The Agentic AI Yard",
      "SmartYard™ YMS",
      "Yard Efficiency Calculator",
    ],
  },
  {
    heading: "Featured",
    links: ["2025 Market Guide", "Yard Management", "Vendor Technology"],
  },
  {
    heading: "Company",
    links: ["About", "Resources", "Contact"],
  },
] as const;

const SOCIALS = [
  { src: "/images/social/linkedin.svg", alt: "LinkedIn", href: "#" },
  { src: "/images/social/x.svg", alt: "X", href: "#" },
  { src: "/images/social/youtube.svg", alt: "YouTube", href: "#" },
] as const;

export function Footer() {
  return (
    <footer className="bg-[var(--c-dark-green)] text-white">
      {/* CTA band */}
      <div className="site-container border-b border-white/10 py-24 lg:py-32">
        <div className="flex flex-col items-start justify-between gap-10 lg:flex-row lg:items-end">
          <h2 className="max-w-2xl text-[clamp(2.25rem,5.5vw,4.5rem)] font-normal leading-[0.98] tracking-[-0.04em]">
            The yard of the future starts today.
          </h2>
          <a
            href="#contact"
            className="group inline-flex shrink-0 items-center gap-3 rounded-lg bg-[var(--c-lime)] px-8 py-4 font-mono text-[11px] font-semibold uppercase tracking-[1.5px] text-[var(--c-dark-green)] transition-colors hover:bg-white"
          >
            Take charge of your yard
            <ArrowRightIcon className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
          </a>
        </div>

        <div className="mt-14 flex items-center gap-4 text-white/60">
          <Image src="/images/gartner.svg" alt="Gartner" width={110} height={25} className="h-6 w-auto opacity-80" />
          <span className="max-w-xs text-xs leading-relaxed">
            Recognized by Gartner as a representative vendor in yard management.
          </span>
        </div>
      </div>

      {/* Links */}
      <div className="site-container py-16">
        <div className="grid gap-12 lg:grid-cols-[1.5fr_repeat(3,1fr)_1.2fr]">
          <div>
            <TerminalLogo className="h-6 w-auto text-white" />
            <p className="mt-6 max-w-xs text-sm leading-relaxed text-white/50">
              The Yard Operating System — AI-native technology from gate to dock.
            </p>
          </div>

          {COLUMNS.map((col) => (
            <nav key={col.heading} aria-label={col.heading}>
              <h3 className="eyebrow text-white/40">{col.heading}</h3>
              <ul className="mt-5 flex flex-col gap-3">
                {col.links.map((link) => (
                  <li key={link}>
                    <a href="#" className="text-sm text-white/75 transition-colors hover:text-[var(--c-lime)]">
                      {link}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          ))}

          <div>
            <h3 className="eyebrow text-white/40">Reach us</h3>
            <p className="mt-5 text-sm text-white/75">Ready for your yard of the future?</p>
            <a href="tel:+17372795032" className="mt-2 block text-lg text-white transition-colors hover:text-[var(--c-lime)]">
              +1 (737) 279-5032
            </a>
            <p className="mt-1 text-xs text-white/50">Give us a call today.</p>

            <div className="mt-6 flex items-center gap-4">
              {SOCIALS.map((s) => (
                <a
                  key={s.alt}
                  href={s.href}
                  aria-label={s.alt}
                  className="flex h-9 w-9 items-center justify-center rounded-full border border-white/20 transition-colors hover:border-[var(--c-lime)]"
                >
                  <Image src={s.src} alt={s.alt} width={16} height={16} className="h-4 w-4 [filter:invert(1)]" />
                </a>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-16 flex flex-col justify-between gap-3 border-t border-white/10 pt-8 text-xs text-white/40 sm:flex-row">
          <span>Copyright Terminal Industries © 2025 All Rights Reserved</span>
          <a href="#" className="transition-colors hover:text-white/70">Technical Index</a>
        </div>
      </div>
    </footer>
  );
}
