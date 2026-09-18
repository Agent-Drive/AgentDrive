import Link from "next/link";
import { ArrowRightIcon } from "./ArrowRightIcon";

const LINKS = [
  { href: "/blog", label: "Blog" },
  { href: "/#agent-access", label: "Docs" },
  { href: "/#", label: "Pricing" },
] as const;

export function MobileNav() {
  return (
    <nav className="mobile-nav" aria-label="Mobile navigation">
      <span className="mobile-nav-logo">Agent Drive</span>
      <div className="mobile-nav-links">
        {LINKS.map((link) => (
          <Link key={link.label} href={link.href}>
            {link.label}
          </Link>
        ))}
      </div>
    </nav>
  );
}

export function DesktopNav() {
  return (
    <nav className="desktop-nav glass-nav sticky top-0 z-40 flex items-center justify-end border-l border-[rgba(240,244,248,0.06)] px-8 py-5">
      <div className="mr-8 flex items-center gap-8 font-mono text-[0.72rem] tracking-wide text-[var(--ink-dim)]">
        {LINKS.map((link) => (
          <Link key={link.label} href={link.href} className="transition-colors hover:text-[var(--ink)]">
            {link.label}
          </Link>
        ))}
      </div>
      <a
        href="/auth/sign-in"
        className="flex items-center gap-2 rounded-md bg-[var(--ink)] px-3.5 py-1.5 font-mono text-[0.7rem] tracking-wide text-[var(--bg)] uppercase transition-opacity hover:opacity-80"
      >
        Sign in <ArrowRightIcon className="btn-arrow-icon h-3 w-3" />
      </a>
    </nav>
  );
}
