# BEHAVIORS — terminal-industries.com

Behavior bible from the interaction sweep (Playwright, 1440 / 768 / 390). Reference when building each component.

## Global

- **Framework:** Nuxt 3 (Vue). CSS split per component (`_nuxt/*.css`).
- **Smooth scroll:** **Lenis** is active — `<html class="lenis">`. Native scroll is replaced by Lenis inertia. Clone with the `lenis` npm package (or a CSS `scroll-behavior` fallback) so scrolling *feels* the same (eased, slightly heavy).
- **Fonts:** `SuisseIntl` (400/450/500/600, self-hosted woff2) for everything; `Geist Mono` (600) for eyebrow labels / button text / counters. Poppins is loaded but effectively unused.
- **Page bg:** white `#fff`; text default dark-green `#052424`. Hero + YOS + Quote sections are dark-green with white text (dark→light→dark alternation).
- **Section separators:** distinctive **"notch"** separators — a horizontal rule with a small rounded rectangular notch cut into it (`.notch-separator`, `.notch-section`). Sections meet with a subtle notch/tab shape rather than a flat edge.

## Header (`.site-header`)

- Fixed, `top: 46px`, `z-index: 10`, full width, transparent. Content is a **centered translucent pill** `.inner` (`background: rgba(0,0,0,.3)`, `backdrop-filter: blur(30px)`, `radius: 8px`, `padding: 18px 24px`, `height: 78px`).
- Pill holds: SVG logo (white, 112×25) · nav dropdown buttons · phone icon · DEMO (white) · CONTACT (lime).
- **Nav dropdowns:** System / Markets / Featured / Resources are click/hover triggers opening large mega-panels (About is a plain link). Each has a chevron.
- **Hover:** nav items → lime; a small lime dot indicator animates in under the item. CTA DEMO white→ (hover) and CONTACT lime→ subtle.
- Header stays translucent throughout scroll (no shrink observed; pill persists).

## Hero (`section.video-carousel`) — height ~2700 (≈3×100vh scroll region)

- **Interaction model:** scroll-driven video carousel + rotating headline. Full-bleed autoplaying muted looped `<video>` (truck at sunset, `vid_3-*.mp4`), dark-green base.
- Rotating H1 (3 messages, fade cross-transition ~every 4s or scroll-tied):
  1. "We have reinvented the future of logistics through the yard."
  2. "AI-native technology that turns manual tasks into connected missions."
  3. "Moving the world by making goods flow."
- H1: SuisseIntl 70px / weight 400 / line-height 66.5px / letter-spacing -3.6px / white (scales with vw).
- "SCROLL TO EXPLORE" indicator (Geist Mono, small, uppercase) top area.

## Logo Wall (`.logo-grid-wrapper.logo-wall`) — "brands you know"

- Heading centered: "Powering the yards behind the brands you know".
- Row(s) of monochrome brand SVGs; on the live site logos **auto-scroll (marquee)** and/or cross-flicker (`.cross-flicker`). Grayscale, low opacity, hover → full.

## Bridge intro (`.notch-section__wrapper`)

- Centered large statement: "Imagine the yard as an intelligent bridge seamlessly connecting highway to warehouse." Fade/slide-up on scroll into view.

## Features Steps (`section.features-steps`) — height ~3085 (sticky/pinned scroll)

- **Interaction model:** SCROLL-DRIVEN. A left **odometer counter** (`.padded-counter`, digits 01→06 rolling) advances as you scroll; the matching capability line highlights. Right side shows a video/visual that swaps per step.
- 6 capabilities:
  01 Autonomous, agentic AI-driven workflows from gate to dock
  02 Single pane of glass visibility of all yard operations
  03 Managed by a unified platform with AI computer vision
  04 Highly configurable to all yards in your network
  05 Unlocked value of your existing WMS/TMS
  06 Digitally transformed, data rich, and predictive

## YOS statement (`.notch-section__wrapper`) — dark green, height ~1800

- Big centered: "That's the **Yard Operating System.**" with large "YOS™" lockup. White on dark green.

## Fullscreen Features / Benefits (`section.fullscreen-features__wrapper`) — height ~3510 (pinned scroll)

- **Interaction model:** SCROLL-DRIVEN pinned panels. Odometer "Benefit 01/02/03…". Each benefit = eyebrow "Benefit 0X" + big title + paragraph + full-bleed video (`vid_4-*`, `vid_5-*`).
  - 01 "A single solution for maximum, automated throughput" — deep integrations, AI computer vision automates gate check-ins…
  - 02 "Easy, scalable operation" — designed for disruption-free ops, low IT lift, modern UI/UX…
  - 03 (+ more) …

## Built by the Industry + Investors grid

- Notch heading: "Built by the Industry / Built by logistics leaders who want a new industry standard in the yard".
- `.logo-grid` of investor/partner logos (rac, marc-jacobs, pods, foxconn, nine-west, kirkland, db-schenker, 8vc, kasper…). Grayscale.

## Quote (`.notch-section__wrapper`) — dark green

- Large quotation: "We have not seen this kind of accuracy with computer-vision technology… this is a significant milestone in the race to modernize the yard." — **Karen Jones, Head of New Product, Ryder System, Inc.** Background quote image (`quote-image.webp`).

## How it Works (`.notch-section__wrapper`)

- Eyebrow "How it Works" + statement "Revolutionary technology that transforms your yard from gate to dock" + link "Take a closer look".

## Contact / Form (`.form-reference`)

- Two-column: left copy "Contact us and we will be in touch same day, your way" + bullets (30-minute demo / Needs discovery call / Yard ROI assessment) + "Trusted by those in the know" mini logo stripe. Right: form (Full Name*, Role/position*, Phone, Email*, Company*, How Can We Help?* select) on a dark-green card.

## Footer (CTA + `.site-footer`)

- CTA band: "The yard of the future starts today." + "Take charge of your yard" button + Gartner badge.
- Footer columns: 2025 Market Guide, Yard Management, Featured, Homepage, YOS, Agentic AI Yard, Yard Efficiency Calculator, Company, About, Resources, Contact. "REACH US" +1 (737) 279-5032. Social: LinkedIn / X / YouTube. "Copyright Terminal Industries © 2025 All Rights Reserved".

## Responsive

- **1440:** full multi-column, centered pill nav with all items.
- **768:** nav collapses toward hamburger; grids reduce columns; hero text scales down.
- **390:** hamburger drawer nav (right slide-in); all grids single-column stack; hero H1 large but wrapping; form full width.
