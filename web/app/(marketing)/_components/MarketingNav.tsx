import Link from "next/link";

export function MarketingNav() {
  return (
    <nav className="flex items-center gap-6 text-sm">
      <Link href="/pricing" className="text-steel hover:text-ink">
        Pricing
      </Link>
      <Link href="/login" className="text-cobalt hover:underline">
        Sign in
      </Link>
    </nav>
  );
}
