import Link from "next/link";

const STATS = [
  { value: "2.4M+", label: "ads indexed" },
  { value: "14K+", label: "brands tracked" },
  { value: "Daily", label: "refresh cadence" },
] as const;

export function DatasetSection() {
  return (
    <section id="ads">
      <div className="mb-6 flex items-baseline justify-between">
        <span className="font-mono text-[0.68rem] tracking-widest text-[var(--ink-dim)] uppercase">
          Datasets
        </span>
      </div>

      <div className="dataset-card">
        <div className="dataset-card-inner">
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.75rem" }}>
              <span className="dataset-title">Mosaic Ads</span>
              <span className="dataset-beta">
                <span
                  className="animate-pulse-green"
                  style={{
                    width: 5,
                    height: 5,
                    borderRadius: "50%",
                    background: "#28C840",
                    display: "inline-block",
                  }}
                />
                Public Beta
              </span>
            </div>
            <p className="dataset-body">
              A live dataset of competitor ads — copy, creative, platform, and format — updated
              daily. For humans who need market intelligence and agents who need real copy to draw
              from.
            </p>
            <Link href="#ads" className="dataset-cta">
              Explore Ads dataset →
            </Link>
          </div>
          <div className="dataset-stats">
            <div className="dataset-stats-label">Live stats</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
              {STATS.map((stat, i) => (
                <div
                  key={stat.label}
                  style={
                    i === 0
                      ? undefined
                      : { borderTop: "1px solid var(--ink-faint)", paddingTop: "0.6rem" }
                  }
                >
                  <span className="dataset-stat-value">{stat.value}</span>
                  <div className="dataset-stat-key">{stat.label}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
