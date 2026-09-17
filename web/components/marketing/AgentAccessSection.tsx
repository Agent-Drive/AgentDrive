import Link from "next/link";
import { ApiSnippet } from "./ApiSnippet";

const SURFACES = [
  { key: "MCP", val: "Native tool for Claude, GPT, Cursor" },
  { key: "API", val: "REST endpoint, structured JSON" },
  { key: "CLI", val: "agentdrive pull --brand nike --limit 50" },
] as const;

export function AgentAccessSection() {
  return (
    <section id="agent-access">
      <div className="mb-3 flex items-baseline justify-between">
        <span className="font-mono text-[0.68rem] tracking-widest text-[var(--ink-dim)] uppercase">
          Agent Access
        </span>
        <Link
          href="#agent-access"
          className="border-b border-[var(--ink-faint)] pb-px font-mono text-[0.65rem] tracking-wide text-[var(--ink-dim)] transition-colors hover:border-[var(--ink)] hover:text-[var(--ink)]"
        >
          View docs →
        </Link>
      </div>
      <p className="font-geist mb-5 max-w-lg text-[0.9rem] leading-[1.65] text-[rgba(240,244,248,0.72)]">
        Three surfaces. One data layer. Agents retrieve real ad context at generation time — so
        output is accurate, grounded, and on-brand.
      </p>

      <div className="agent-access-strip mb-6">
        {SURFACES.map((item) => (
          <div key={item.key} className="agent-access-item">
            <span className="agent-access-key">{item.key}</span>
            <span className="agent-access-val">{item.val}</span>
          </div>
        ))}
      </div>
      <ApiSnippet />
    </section>
  );
}
