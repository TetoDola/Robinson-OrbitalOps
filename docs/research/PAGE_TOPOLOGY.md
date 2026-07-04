# Page Topology — terminal-industries.com

Source: https://terminal-industries.com/ · Nuxt 3 site · Lenis smooth scroll.
Full page height ≈ 17,150px (desktop 1440). Sections top→bottom (measured):

| # | Component | Class | top (px) | height | model | bg |
|---|-----------|-------|---------:|-------:|-------|----|
| — | Header | `.site-header` | fixed 46 | 78 | static (fixed overlay, translucent pill) | transparent |
| 0 | Hero / video carousel | `section.video-carousel` | 0 | 2700 | scroll-driven video + rotating H1 | dark-green + video |
| 1 | Logo Wall | `.logo-grid-wrapper.logo-wall` | 2700 | 641 | marquee / cross-flicker | white |
| 2 | Bridge intro | `.notch-section__wrapper` | 3341 | 570 | scroll fade-in | white |
| 3 | Features Steps | `section.features-steps` | 3911 | 3085 | **scroll-driven, pinned, odometer 01–06** | white |
| 4 | YOS statement | `.notch-section__wrapper` | 6996 | 1800 | scroll fade | **dark-green** |
| 5 | Fullscreen Features (Benefits) | `section.fullscreen-features__wrapper` | 8796 | 3510 | **scroll-driven pinned panels + odometer** | dark / video |
| 6 | Built by the Industry | `.notch-section__wrapper` | 12306 | 621 | scroll fade | white |
| 7 | Investors logo grid | `.logo-grid-wrapper` | 12927 | 621 | static grid | white |
| 8 | Quote | `.notch-section__wrapper` | 13548 | 900 | scroll fade + bg image | **dark-green** |
| 9 | How it Works | `.notch-section__wrapper` | 14321 | 810 | scroll fade | white |
| 10 | Contact / Form | `.form-reference` | 15131 | 924 | static form | white / dark card |
| 11 | Footer (CTA + links) | `.footer__height-holder` / `.site-footer` | 16055 | 1102 | sticky reveal | dark-green |

Separators between many sections use the **notch** motif (`.notch-separator`, `.notch-section`).

## Component → target file map (src/components/)

- `Header.tsx` · `HeroSection.tsx` · `LogoMarquee.tsx` · `BridgeSection.tsx` ·
  `FeaturesSteps.tsx` (was YosFeatures) · `YosStatement.tsx` · `BenefitsSection.tsx` (fullscreen) ·
  `BuiltByIndustry.tsx` + `InvestorsGrid.tsx` · `QuoteSection.tsx` · `HowItWorks.tsx` ·
  `ContactSection.tsx` · `Footer.tsx` (CTA banner + footer) · shared `icons.tsx`.

## Design Tokens (from getComputedStyle)

| Token | Value |
|-------|-------|
| --c-dark-green | #052424 (rgb 5,36,36) |
| --c-lime | #abff02 (rgb 171,255,2) |
| --c-white | #fff |
| --c-orange | #fb6b3c |
| --c-gray | #454742 |
| --c-dark-gray | #7f7f7f |
| --c-light-gray | #c2c2c2 |
| --c-dirty-white | #f0f0f0 |
| font body/head | SuisseIntl 400/450/500/600 |
| font mono/eyebrow | Geist Mono 600 |

## Key measurements

- Header pill: rgba(0,0,0,.3) + blur(30px), radius 8, padding 18/24, height 78, centered.
- H1 hero: 70px / 400 / lh 66.5 / ls -3.6px / white.
- CTA buttons: Geist Mono 11px / 600 / ls 1.5px / padding 12×32 / radius 8. DEMO=white bg, CONTACT=lime bg, text dark-green.
- Site container horizontal padding: ~52px (desktop).
