import { SmoothScroll } from "@/components/SmoothScroll";
import { Header } from "@/components/Header";
import { HeroSection } from "@/components/HeroSection";
import { LogoMarquee } from "@/components/LogoMarquee";
import { BridgeSection } from "@/components/BridgeSection";
import { FeaturesSteps } from "@/components/FeaturesSteps";
import { ContactSection } from "@/components/ContactSection";
import { Footer } from "@/components/Footer";

export default function Home() {
  return (
    <>
      <SmoothScroll />
      <Header />
      <main>
        <HeroSection />
        <LogoMarquee />
        <BridgeSection />
        <FeaturesSteps />
        <ContactSection />
      </main>
      <Footer />
    </>
  );
}
