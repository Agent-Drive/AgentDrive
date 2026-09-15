import { Logo } from "@/components/Logo";
import { CyanotypeBackground } from "./CyanotypeBackground";
import { MarketingNav } from "./MarketingNav";

export function MarketingChrome({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative min-h-svh">
      <CyanotypeBackground />
      <header className="relative z-10 mx-auto flex max-w-5xl items-center justify-between px-6 py-6">
        <Logo />
        <MarketingNav />
      </header>
      <div className="relative z-10">{children}</div>
    </div>
  );
}
