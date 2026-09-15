import Link from "next/link";

const LINKS = [
  { href: "#ads", label: "Ads" },
  { href: "#agent-access", label: "Docs" },
  { href: "/pricing", label: "Pricing" },
  { href: "#contact", label: "Contact" },
] as const;

export function MosaicFooter() {
  return (
    <footer id="contact" className="border-t border-[var(--ink-faint)] pt-10 pb-4">
      <div className="flex flex-wrap items-center justify-between gap-6">
        <div>
          <div className="font-geist mb-1 text-[0.95rem] font-semibold tracking-tight">Mosaic</div>
          <div className="mb-2 font-mono text-[0.7rem] tracking-wide text-[var(--ink-dim)]">
            Made with <span className="text-[var(--accent)]">♥</span> in LA
          </div>
          <div className="flex items-center gap-1.5 font-mono text-[0.68rem] text-[var(--ink-dim)]">
            <span className="animate-pulse-green h-1.5 w-1.5 rounded-full bg-[#28C840]" />
            All systems operational
          </div>
        </div>
        <div className="flex gap-8 font-mono text-[0.7rem] text-[var(--ink-dim)]">
          {LINKS.map((link) => (
            <Link key={link.label} href={link.href} className="transition-colors hover:text-[var(--ink)]">
              {link.label}
            </Link>
          ))}
        </div>
      </div>
    </footer>
  );
}
