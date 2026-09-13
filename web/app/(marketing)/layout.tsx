import { Logo } from "@/components/Logo";
import { MarketingNav } from "./_components/MarketingNav";

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-svh">
      <header className="mx-auto flex max-w-5xl items-center justify-between px-6 py-6">
        <Logo />
        <MarketingNav />
      </header>
      {children}
    </div>
  );
}
