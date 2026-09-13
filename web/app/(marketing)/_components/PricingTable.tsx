import Link from "next/link";

export function PricingTable() {
  return (
    <section className="max-w-xl">
      <h1 className="font-display text-5xl tracking-tight">Pricing</h1>
      <p className="mt-6 text-lg leading-relaxed text-steel">
        Free while we build. Sign in, connect MCP, and store files. We will publish
        usage pricing before we charge.
      </p>
      <Link
        href="/login"
        className="mt-8 inline-block bg-ink px-4 py-2 text-sm text-paper hover:bg-cobalt"
      >
        Sign in
      </Link>
    </section>
  );
}
