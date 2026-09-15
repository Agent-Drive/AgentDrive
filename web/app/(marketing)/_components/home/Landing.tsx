import { AgentAccessSection } from "./AgentAccessSection";
import { BlogSection } from "./BlogSection";
import { HeroAside } from "./HeroAside";
import { IntroSection } from "./IntroSection";
import { HomeFooter } from "./HomeFooter";
import { DesktopNav, MobileNav } from "./SiteNav";
import { TestimonialsSection } from "./TestimonialsSection";

export function Landing() {
  return (
    <>
      <HeroAside />
      <MobileNav />
      <main className="layout-main">
        <DesktopNav />
        <div className="content-wrap">
          <IntroSection />
          <AgentAccessSection />
          <TestimonialsSection />
          <BlogSection />
          <HomeFooter />
        </div>
      </main>
    </>
  );
}
