import { AgentAccessSection } from "./AgentAccessSection";
import { BlogSection } from "./BlogSection";
import { DatasetSection } from "./DatasetSection";
import { HeroAside } from "./HeroAside";
import { IntroSection } from "./IntroSection";
import { MosaicFooter } from "./MosaicFooter";
import { DesktopNav, MobileNav } from "./SiteNav";
import { TestimonialsSection } from "./TestimonialsSection";

export function MosaicPage() {
  return (
    <>
      <HeroAside />
      <MobileNav />
      <main className="layout-main">
        <DesktopNav />
        <div className="content-wrap">
          <IntroSection />
          <DatasetSection />
          <AgentAccessSection />
          <TestimonialsSection />
          <BlogSection />
          <MosaicFooter />
        </div>
      </main>
    </>
  );
}
