# Header Specification

## Overview
- **Target file:** `src/components/Header.tsx`
- **Screenshot:** `docs/design-references/desktop-hero-1440.png`
- **Interaction model:** static fixed overlay (translucent pill), dropdown nav, mobile drawer.

## Computed styles (getComputedStyle)
### `.site-header`
- position: fixed; top: 46px; left/right: 0; z-index: 10; height: 78px; background: transparent.

### `.inner` (centered pill)
- background: rgba(0, 0, 0, 0.3); backdrop-filter: blur(30px); border-radius: 8px;
- padding: 18px 24px; height: 78px; width ≈ 944px (centered, not full-width).
- layout: flex, space-between: logo · nav · [phone, DEMO, CONTACT].

### Logo
- Inline SVG, viewBox `0 0 215 49`, rendered 112×25.5px, `fill: currentColor` white. "T" tile mark + "Terminal" wordmark. Reproduced exactly in `icons.tsx` → `<TerminalLogo>`.

### Nav items (System / Markets / Featured / Resources = dropdown buttons; About = link)
- SuisseIntl 14px / weight 450 / white. Chevron 12px. Hover → lime `#abff02`; a 5×5px lime dot indicator scales/fades in below.

### CTA buttons (`.cta-button`)
- Geist Mono 11px / weight 600 / letter-spacing 1.5px / uppercase / color #052424.
- padding: 12px 32px; border-radius: 8px; height: 40.5px.
- **DEMO** `--secondary`: background #fff (hover → lime).
- **CONTACT** `--primary`: background #abff02 (hover → #fff).
- Phone: 40×40 icon button, border white/30 (hover → lime).

## Responsive
- **≥1024px:** full pill with all nav items + phone + both CTAs.
- **<1024px:** nav + CTAs hidden, hamburger shows; opens right slide-in drawer (dark-green, blur), with nav list + stacked DEMO/CONTACT.

## Notes / gaps
- Mega-panel dropdown contents (System/Markets/etc.) are stubbed as hover triggers; full mega-menu panels not rebuilt (out of homepage scope).
