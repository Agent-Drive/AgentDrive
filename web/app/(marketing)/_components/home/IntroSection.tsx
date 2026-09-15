export function IntroSection() {
  return (
    <section className="max-w-2xl">
      <div className="font-geist space-y-5 text-[1rem] leading-[1.65] text-[rgba(240,244,248,0.82)]">
        <p>
          Agent Drive builds{" "}
          <strong className="font-medium text-[var(--ink)]">high-fidelity datasets</strong> for the
          people and systems that run modern marketing. Agents are only as good as their context —
          most are working with thin, generic data. We fix that.
        </p>
        <p>
          We go deep on one domain before the next. Our first dataset,{" "}
          <strong className="font-medium text-[var(--ink)]">Ads</strong>, gives you a live view of
          what competitors are running — and gives your agents real market copy to work with at
          generation time.
        </p>
      </div>

      <div className="audience-split mt-10 mb-6">
        <div className="audience-col">
          <div className="audience-label">For Humans</div>
          <ul className="audience-list">
            <li>Live competitor intelligence</li>
            <li>Trend signals &amp; benchmarks</li>
            <li>Dashboard + export</li>
          </ul>
        </div>
        <div className="audience-divider" />
        <div className="audience-col">
          <div className="audience-label">For AI Agents</div>
          <ul className="audience-list">
            <li>Structured corpus for RAG</li>
            <li>MCP · API · CLI access</li>
            <li>Clean schema, zero hallucination</li>
          </ul>
        </div>
      </div>

      <div className="trusted-strip" style={{ marginTop: "2rem", marginBottom: 0 }}>
        <span className="trusted-label">Trusted by</span>
        <div className="trusted-names">
          <span>Ogilvy</span>
          <span>Publicis</span>
          <span>Monks</span>
          <span>R/GA</span>
          <span>TBWA</span>
        </div>
      </div>
    </section>
  );
}
