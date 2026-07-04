# HeroSection Specification

## Overview
- **Target file:** `src/components/HeroSection.tsx`
- **Source:** `section.video-carousel` (height ≈2700px / ~3× viewport scroll region on live site)
- **Screenshot:** `docs/design-references/clone-hero.png`
- **Interaction model:** scroll-driven full-bleed video carousel + time-rotating headline.

## Styles
- Section: `min-height: 100vh`, bg `#052424`, white text, overflow hidden.
- Video: absolutely positioned, `object-fit: cover`, autoplay muted loop playsInline. Sources `vid_3-1/2/3/5` → `public/videos/hero-1..4.mp4`. Dark-green gradient overlay bottom.
- H1: SuisseIntl, weight 400, live desktop = 70px / line-height 66.5px / letter-spacing -3.6px, white. Clone uses `clamp(2.5rem,7vw,4.375rem)`, leading .95, tracking -0.045em. Anchored bottom-left, `padding-bottom: 135px`.
- Rotating headlines (cross-fade ~4.2s):
  1. "We have reinvented the future of logistics through the yard."
  2. "AI-native technology that turns manual tasks into connected missions."
  3. "Moving the world by making goods flow."
- "SCROLL TO EXPLORE" indicator: Geist Mono eyebrow, uppercase, rotated 90°, right side.

## Responsive
- Text scales via clamp; padding-bottom reduces on mobile; scroll indicator hidden <1024px.
