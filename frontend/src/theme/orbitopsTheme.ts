import { defineTheme } from "@astryxdesign/core/theme";

/**
 * OrbitOps theme for Astryx — maps the design system's tokens onto our
 * aerospace palette (Launch Blue accent · Jade/Amber/Tomato semantics) and
 * fonts (IBM Plex Sans / JetBrains Mono). Dark-committed command console.
 */
export const orbitopsTheme = defineTheme({
  name: "orbitops",
  color: { accent: "#2f8fff", neutralStyle: "cool", contrast: "standard" },
  typography: {
    scale: { base: 15, ratio: 1.2 },
    body: { family: "IBM Plex Sans", fallbacks: "system-ui, -apple-system, sans-serif" },
    code: { family: "JetBrains Mono", fallbacks: "ui-monospace, Menlo, monospace" },
  },
  radius: { base: 6, multiplier: 1 },
  motion: { fast: 160, medium: 320, ratio: 0.75 },
  tokens: {
    "--color-accent": ["#2f8fff", "#3a97ff"],
    "--color-on-accent": ["#04121f", "#04121f"],
    "--color-background-body": ["#0a0e18", "#0a0e18"],
    "--color-background-surface": ["#161c28", "#161c28"],
    "--color-background-card": ["#1a2130", "#1a2130"],
    "--color-text-primary": ["#eef1f5", "#eef1f5"],
    "--color-text-secondary": ["#aab4c2", "#aab4c2"],
    "--color-success": ["#3ccf92", "#3ccf92"],
    "--color-error": ["#f06442", "#f06442"],
  },
});
