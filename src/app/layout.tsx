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
  metadataBase: new URL("https://terminal-industries.com"),
  title:
    "Terminal Yard Operating System | The New Industry Standard in Yard Operations",
  description:
    "AI-native technology that turns manual tasks into connected missions. The Yard Operating System (YOS™) for modern yard operations.",
  icons: {
    icon: [
      { url: "/seo/favicon.svg", type: "image/svg+xml" },
      { url: "/seo/favicon-96x96.png", sizes: "96x96", type: "image/png" },
      { url: "/seo/favicon.ico" },
    ],
    apple: "/seo/apple-touch-icon.png",
  },
  manifest: "/seo/site.webmanifest",
  openGraph: {
    title: "Terminal Yard Operating System",
    description:
      "The new industry standard in yard operations — AI-native YOS™ from gate to dock.",
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
