"use client";

import { useState } from "react";
import { RobinsonLogo, ChevronDownIcon, PhoneIcon } from "@/components/icons";

const NAV_ITEMS = [
  { label: "Platform", hasDropdown: true },
  { label: "Fleet", hasDropdown: true },
  { label: "How it works", hasDropdown: true },
  { label: "Resources", hasDropdown: true },
  { label: "About", hasDropdown: false },
] as const;

export function Header() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <>
      <header className="pointer-events-none fixed inset-x-0 top-[46px] z-50 text-white">
        <div className="site-container">
          <div className="pointer-events-auto mx-auto flex h-[78px] w-full max-w-[944px] items-center justify-between gap-6 rounded-lg bg-black/30 px-6 py-[18px] backdrop-blur-[30px]">
            <a
              href="/"
              aria-label="Robinson — home"
              className="group flex shrink-0 items-center gap-2.5 text-white transition-colors hover:text-[var(--c-lime)]"
            >
              <RobinsonLogo className="h-[26px] w-auto" />
              <span className="text-[22px] font-semibold leading-none tracking-[-0.02em]">Robinson</span>
            </a>

            <nav aria-label="Main navigation" className="hidden lg:block">
              <ul className="flex items-center gap-7">
                {NAV_ITEMS.map((item) => (
                  <li key={item.label}>
                    <button
                      type="button"
                      className="group relative flex items-center gap-1.5 py-2 text-sm font-[450] text-white transition-colors hover:text-[var(--c-lime)]"
                    >
                      <span>{item.label}</span>
                      {item.hasDropdown && (
                        <ChevronDownIcon className="h-3 w-3 opacity-70 transition-transform duration-300 group-hover:-rotate-180" />
                      )}
                      <span
                        aria-hidden
                        className="absolute -bottom-0.5 left-1/2 h-[5px] w-[5px] -translate-x-1/2 scale-0 rounded-full bg-[var(--c-lime)] opacity-0 transition-all duration-300 group-hover:scale-100 group-hover:opacity-100"
                      />
                    </button>
                  </li>
                ))}
              </ul>
            </nav>

            <div className="flex items-center gap-3">
              <button
                type="button"
                aria-label="Call us"
                className="hidden h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-white/30 text-white transition-colors hover:border-[var(--c-lime)] hover:text-[var(--c-lime)] sm:flex"
              >
                <PhoneIcon className="h-[18px] w-[18px]" />
              </button>
              <a
                href="/demo"
                className="hidden items-center rounded-lg bg-white px-8 py-3 font-mono text-[11px] font-semibold tracking-[1.5px] text-[var(--c-dark-green)] transition-colors hover:bg-[var(--c-lime)] sm:inline-flex"
              >
                DEMO
              </a>
              <a
                href="/contact"
                className="hidden items-center rounded-lg bg-[var(--c-lime)] px-8 py-3 font-mono text-[11px] font-semibold tracking-[1.5px] text-[var(--c-dark-green)] transition-colors hover:bg-white sm:inline-flex"
              >
                CONTACT
              </a>

              <button
                type="button"
                aria-label="Toggle menu"
                aria-expanded={mobileOpen}
                onClick={() => setMobileOpen((o) => !o)}
                className="relative flex h-6 w-6 flex-col justify-center gap-[5px] lg:hidden"
              >
                <span className={`block h-0.5 w-full bg-white transition-all duration-300 ${mobileOpen ? "translate-y-[7px] rotate-45" : ""}`} />
                <span className={`block h-0.5 w-full bg-white transition-all duration-300 ${mobileOpen ? "opacity-0" : "opacity-100"}`} />
                <span className={`block h-0.5 w-full bg-white transition-all duration-300 ${mobileOpen ? "-translate-y-[7px] -rotate-45" : ""}`} />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Mobile drawer */}
      <div className={`fixed inset-0 z-40 lg:hidden ${mobileOpen ? "pointer-events-auto" : "pointer-events-none"}`} aria-hidden={!mobileOpen}>
        <button
          type="button"
          aria-label="Close menu"
          className={`absolute inset-0 bg-black/50 transition-opacity duration-300 ${mobileOpen ? "opacity-100" : "opacity-0"}`}
          onClick={() => setMobileOpen(false)}
        />
        <div
          className={`absolute bottom-0 right-0 top-0 flex w-[min(20rem,85vw)] flex-col bg-[var(--c-dark-green)]/95 backdrop-blur-[30px] transition-transform duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] ${mobileOpen ? "translate-x-0" : "translate-x-full"}`}
        >
          <div className="flex min-h-[78px] items-center gap-2.5 border-b border-white/15 px-6 text-white">
            <RobinsonLogo className="h-6 w-auto" />
            <span className="text-[20px] font-semibold leading-none tracking-[-0.02em]">Robinson</span>
          </div>
          <nav aria-label="Mobile navigation" className="flex-1 overflow-y-auto p-6">
            <ul className="flex flex-col gap-1">
              {NAV_ITEMS.map((item) => (
                <li key={item.label}>
                  <button
                    type="button"
                    className="flex w-full items-center justify-between py-4 text-base text-white transition-colors hover:text-[var(--c-lime)]"
                  >
                    <span>{item.label}</span>
                    {item.hasDropdown && <ChevronDownIcon className="h-4 w-4 -rotate-90" />}
                  </button>
                </li>
              ))}
            </ul>
          </nav>
          <div className="flex flex-col gap-3 border-t border-white/15 p-6">
            <a href="/demo" className="inline-flex justify-center rounded-lg bg-white px-8 py-3 font-mono text-[11px] font-semibold tracking-[1.5px] text-[var(--c-dark-green)]">
              DEMO
            </a>
            <a href="/contact" className="inline-flex justify-center rounded-lg bg-[var(--c-lime)] px-8 py-3 font-mono text-[11px] font-semibold tracking-[1.5px] text-[var(--c-dark-green)]">
              CONTACT
            </a>
          </div>
        </div>
      </div>
    </>
  );
}
