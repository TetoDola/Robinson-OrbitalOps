import { SmoothScroll } from "@/components/SmoothScroll";
import { Header } from "@/components/Header";
import { HeroSection } from "@/components/HeroSection";
import { LogoMarquee } from "@/components/LogoMarquee";
import { BridgeSection } from "@/components/BridgeSection";
import { FeaturesSteps } from "@/components/FeaturesSteps";
import { YosStatement } from "@/components/YosStatement";
import { BenefitsSection } from "@/components/BenefitsSection";
import { BuiltByIndustry } from "@/components/BuiltByIndustry";
import { QuoteSection } from "@/components/QuoteSection";
import { HowItWorks } from "@/components/HowItWorks";
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
        <YosStatement />
        <BenefitsSection />
        <BuiltByIndustry />
        <QuoteSection />
        <HowItWorks />
        <ContactSection />
      </main>
      <Footer />
    </>
  );
}
