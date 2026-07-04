import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Live Demo | OrbitOps Command Center",
  description:
    "Supervised multi-agent command center for orbital GPU datacenters — live orbital telemetry and Mission Patch approval console.",
};

export default function DemoPage() {
  return (
    <iframe
      src="/demo.html"
      title="OrbitOps Command Center demo"
      allow="fullscreen"
      style={{
        position: "fixed",
        inset: 0,
        width: "100%",
        height: "100%",
        border: 0,
        display: "block",
        background: "#030504",
      }}
    />
  );
}
