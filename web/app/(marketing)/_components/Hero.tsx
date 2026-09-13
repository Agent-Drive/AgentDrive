import Link from "next/link";

export function Hero() {
  return (
    <section className="max-w-3xl">
      <h1 className="font-display text-5xl leading-tight tracking-tight sm:text-6xl">
        Files your agents can actually use.
      </h1>
      <p className="mt-6 max-w-xl text-lg leading-relaxed text-steel">
        Agent Drive ingests documents, chunks them, and serves hybrid search over MCP
        and a REST API. Store once. Retrieve by meaning.
      </p>
      <div className="mt-8 flex flex-wrap gap-4">
        <Link
          href="/login"
          className="bg-ink px-4 py-2 text-sm text-paper hover:bg-cobalt"
        >
          Open dashboard
        </Link>
        <Link href="/pricing" className="border border-rule px-4 py-2 text-sm hover:border-ink">
          Pricing
        </Link>
      </div>
    </section>
  );
}
