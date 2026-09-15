import Link from "next/link";

const LINKS = [
  { href: "/#agent-access", label: "Documentation" },
  { href: "/#", label: "Pricing" },
  { href: "#", label: "Twitter" },
] as const;

export function BlogFooter() {
  return (
    <footer className="mt-12 border-t border-[var(--ink-faint)] bg-[#05060A] px-10 py-12">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-8">
        <div>
          <div className="font-geist mb-2 text-[1.1rem] font-semibold tracking-tight text-[var(--ink)]">
            Agent Drive
          </div>
          <div className="font-mono text-[0.75rem] tracking-wide text-[var(--ink-dim)]">
            The ad intelligence layer.
          </div>
        </div>
        <div className="flex gap-10 font-mono text-[0.75rem] text-[var(--ink-dim)]">
          {LINKS.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              className="transition-colors hover:text-[var(--ink)]"
            >
              {link.label}
            </Link>
          ))}
        </div>
      </div>
    </footer>
  );
}
