import type { Metadata } from "next";
import { Geist_Mono } from "next/font/google";
import "./globals.css";

const geistMono = Geist_Mono({
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  variable: "--font-geist-mono",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://orbitops.space"),
  title:
    "Robinson | Orbital Datacenter Command — keep compute alive in orbit",
  description:
    "A supervised multi-agent command center for orbital GPU datacenters — adapting compute to radiation, heat, power and downlink in real time, with human approval on every critical action.",
  icons: {
    icon: [{ url: "/robinson-icon.svg", type: "image/svg+xml" }],
    shortcut: "/robinson-icon.svg",
    apple: "/robinson-icon.svg",
  },
  manifest: "/seo/site.webmanifest",
  openGraph: {
    title: "Robinson — Orbital Datacenter Command",
    description:
      "The supervised multi-agent crew that keeps datacenters alive in orbit.",
    images: ["/seo/social-image.webp"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`h-full ${geistMono.variable}`}>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
