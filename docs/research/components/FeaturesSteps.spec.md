# FeaturesSteps Specification

## Overview
- **Target file:** `src/components/FeaturesSteps.tsx`
- **Source:** `section.features-steps` (height ≈3085px on live site — pinned/sticky scroll)
- **Interaction model:** SCROLL-DRIVEN, pinned. A rolling odometer (01→06) advances with scroll; the matching capability highlights; a right video panel swaps per step.

## Implementation
- Section height `320vh`; inner `position: sticky; top: 0; height: 100vh`.
- Scroll progress `(-rect.top)/(offsetHeight - innerHeight)` → active index `floor(progress*6)`.
- Left: Geist Mono odometer number (lime, clamp 3.5–6rem) + "/ 06"; capability list, active item full opacity dark-green, others 25%.
- Right: video panel (rounded 2xl), cross-fades between step videos.

## Capabilities (verbatim)
1. Autonomous, agentic AI-driven workflows from gate to dock
2. Single pane of glass visibility of all yard operations
3. Managed by a unified platform with AI computer vision
4. Highly configurable to all yards in your network
5. Unlocked value of your existing WMS/TMS
6. Digitally transformed, data rich, and predictive

## Responsive
- 2-col ≥1024px; single column stack below (video above list).
