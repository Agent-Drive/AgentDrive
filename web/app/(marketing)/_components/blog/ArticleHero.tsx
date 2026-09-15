export function ArticleHero() {
  return (
    <header className="hero-banner">
      <div className="max-w-4xl">
        <span className="meta-tag mb-4 block">Editorial · Dataset Strategy</span>
        <h1 className="font-geist mb-6 text-[3.5rem] leading-[1.1] font-medium tracking-tight text-[var(--ink)]">
          Why we started with ads: the case for domain-specific data
        </h1>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[0.75rem] text-[var(--ink-dim)]">
          <span>By Sarah Chen</span>
          <span className="text-[var(--ink-faint)]">|</span>
          <span>June 12, 2025</span>
          <span className="text-[var(--ink-faint)]">|</span>
          <span>8 min read</span>
        </div>
      </div>
    </header>
  );
}
