import Link from "next/link";
import { AgentDriveMark } from "../home/AgentDriveMark";
import { ArrowRightIcon } from "../home/ArrowRightIcon";

const LINKS = [
  { href: "/blog", label: "Blog", current: true },
  { href: "/#agent-access", label: "Docs" },
  { href: "/#", label: "Pricing" },
] as const;

export function BlogNav() {
  return (
    <nav className="desktop-nav glass-nav fixed top-0 z-50 flex w-full items-center justify-between px-8 py-5">
      <Link href="/" className="flex shrink-0 items-center gap-2.5 whitespace-nowrap text-[var(--ink)]">
        <AgentDriveMark className="h-7 w-7 text-[var(--ink)]" />
        <span className="font-geist text-[1.15rem] font-semibold tracking-tight text-[var(--ink)]">
          Agent Drive
        </span>
      </Link>
      <div className="flex items-center">
        <div className="mr-8 flex items-center gap-8 font-mono text-[0.72rem] tracking-wide text-[var(--ink-dim)]">
          {LINKS.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              className={"current" in link && link.current ? "text-[var(--ink)]" : "transition-colors hover:text-[var(--ink)]"}
              aria-current={"current" in link && link.current ? "page" : undefined}
            >
              {link.label}
            </Link>
          ))}
        </div>
        <a
          href="/sign-in"
          className="flex items-center gap-2 rounded-md bg-[var(--ink)] px-3.5 py-1.5 font-mono text-[0.7rem] tracking-wide text-[var(--bg)] uppercase transition-opacity hover:opacity-80"
        >
          Sign in <ArrowRightIcon className="btn-arrow-icon h-3 w-3" />
        </a>
      </div>
    </nav>
  );
}
