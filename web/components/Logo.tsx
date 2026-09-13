import Link from "next/link";

export function Logo({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="inline-flex items-baseline gap-2 text-ink no-underline">
      <span aria-hidden className="inline-block h-3 w-3 rounded-full bg-cobalt" />
      <span className="font-display text-xl tracking-tight">Agent Drive</span>
    </Link>
  );
}
