"use client";

import Image from "next/image";
import { useReveal } from "@/hooks/useReveal";

const BULLETS = ["30-minute live demo", "Architecture deep-dive", "Mission fit assessment"] as const;

const HELP_OPTIONS = [
  "Book a live Robinson demo",
  "Talk to a mission engineer",
  "Discuss our orbital fleet",
  "Set up a proof of concept",
  "Something else",
] as const;

function Field({
  label,
  type = "text",
  required,
}: {
  label: string;
  type?: string;
  required?: boolean;
}) {
  return (
    <label className="flex flex-col gap-2">
      <span className="text-sm text-white/70">
        {label}
        {required && <span className="text-[var(--c-lime)]"> *</span>}
      </span>
      <input
        type={type}
        required={required}
        className="h-12 rounded-lg border border-white/15 bg-white/5 px-4 text-white outline-none transition-colors placeholder:text-white/30 focus:border-[var(--c-lime)]"
      />
    </label>
  );
}

export function ContactSection() {
  const ref = useReveal<HTMLElement>();

  return (
    <section ref={ref} id="contact" className="reveal bg-white py-24 lg:py-32">
      <div className="site-container grid gap-14 lg:grid-cols-2 lg:gap-20">
        {/* Left copy */}
        <div>
          <h2 className="text-[clamp(1.75rem,3.4vw,2.75rem)] font-normal leading-[1.1] tracking-[-0.025em] text-[var(--c-dark-green)]">
            Talk to the team keeping compute alive in orbit
          </h2>
          <p className="mt-6 max-w-md text-[var(--c-gray)]">
            Fill out the form and we&apos;ll show you how Robinson keeps orbital datacenters running through radiation, eclipse and lost downlink windows:
          </p>
          <ul className="mt-8 flex flex-col gap-4">
            {BULLETS.map((b) => (
              <li key={b} className="flex items-center gap-3 text-[var(--c-dark-green)]">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[var(--c-lime)] text-[var(--c-dark-green)]">
                  <svg viewBox="0 0 16 16" className="h-3 w-3" fill="none">
                    <path d="M3 8.5L6.5 12L13 4.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </span>
                <span className="text-lg">{b}</span>
              </li>
            ))}
          </ul>

          <div className="mt-12">
            <p className="eyebrow text-[var(--c-dark-gray)]">Powered by</p>
            <div className="mt-5">
              <Image
                src="/images/crusoe.webp"
                alt="Crusoe"
                width={635}
                height={157}
                className="h-9 w-auto object-contain"
              />
            </div>
          </div>
        </div>

        {/* Right form */}
        <form
          className="rounded-2xl bg-[var(--c-dark-green)] p-8 lg:p-10"
          onSubmit={(e) => e.preventDefault()}
        >
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Full Name" required />
            <Field label="Role or position" required />
            <Field label="Phone number" type="tel" />
            <Field label="Email" type="email" required />
          </div>
          <div className="mt-5">
            <Field label="Company name" required />
          </div>
          <label className="mt-5 flex flex-col gap-2">
            <span className="text-sm text-white/70">
              How Can We Help?<span className="text-[var(--c-lime)]"> *</span>
            </span>
            <select
              required
              defaultValue=""
              className="h-12 rounded-lg border border-white/15 bg-white/5 px-4 text-white outline-none transition-colors focus:border-[var(--c-lime)]"
            >
              <option value="" disabled className="text-black">
                Select options
              </option>
              {HELP_OPTIONS.map((o) => (
                <option key={o} value={o} className="text-black">
                  {o}
                </option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            className="mt-8 w-full rounded-lg bg-[var(--c-lime)] px-8 py-4 font-mono text-[11px] font-semibold uppercase tracking-[1.5px] text-[var(--c-dark-green)] transition-colors hover:bg-white"
          >
            Submit
          </button>
        </form>
      </div>
    </section>
  );
}
