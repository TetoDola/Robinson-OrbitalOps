# BenefitsSection (Fullscreen Features) Specification

## Overview
- **Target file:** `src/components/BenefitsSection.tsx`
- **Source:** `section.fullscreen-features__wrapper` (height ≈3510px — pinned scroll)
- **Interaction model:** SCROLL-DRIVEN pinned panels + odometer "Benefit 0X". Each benefit = full-bleed background video + eyebrow + big title + paragraph, dark-green base.

## Implementation
- Section height `300vh` (3 benefits); inner sticky 100vh; background videos cross-fade per active index; bottom gradient to `#052424`; text bottom-left; vertical progress bars right.

## Benefits (verbatim)
- **Benefit 01 — A single solution for maximum, automated throughput.** "Deep integrations anticipate incoming loads, enabling our AI computer vision technology to automate gate check-ins and all critical yard operations: from assigning locations and maintaining real-time visibility to coordinating spotters for efficient load movement. It then closes the loop by validating assets before exit, providing comprehensive performance supervision across your entire yard network." — video `benefit-1-wide.mp4`
- **Benefit 02 — Easy, scalable operation.** "Terminal was designed from the ground up for disruption-free operations. Easy to deploy and support, the system has a low IT lift with no 3rd party devices to support, and a modern UI/UX that's super-easy for operators to use from day one. Configurable to your yard, Terminal YOS integrates seamlessly with most TMS and WMS systems." — video `benefit-2-vert.mp4`
- **Benefit 03 — (title inferred) Cost-effective, priced as a service.** "We know that yard operations run on lean budgets, which is why we price our all-inclusive solution as a service with terms that won't bust the bank. Ready to deploy right away, and rapid to scale over time." — video `benefit-3-wide.mp4`

## Gaps
- Benefit 03 heading text could not be cleanly extracted (rendered as split spans); title is a faithful paraphrase pending re-extraction.
