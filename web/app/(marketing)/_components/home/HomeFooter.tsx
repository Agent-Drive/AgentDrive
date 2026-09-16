import Link from "next/link";

const LINKS = [
  { href: "#agent-access", label: "Docs" },
  { href: "#", label: "Pricing" },
  { href: "#contact", label: "Contact" },
] as const;

export function HomeFooter() {
  return (
    <footer id="contact" className="border-t border-[var(--ink-faint)] pt-10 pb-4">
      <div className="flex flex-wrap items-center justify-between gap-6">
        <div>
          <div className="font-geist mb-1 text-[0.95rem] font-semibold tracking-tight">
            Agent Drive
          </div>
          <div className="font-mono text-[0.7rem] tracking-wide text-[var(--ink-dim)]">
            Made with <span className="text-[var(--accent)]">♥</span> in London
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
