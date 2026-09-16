import Link from "next/link";
import { AgentDriveMark } from "./AgentDriveMark";
import { ArrowRightIcon } from "./ArrowRightIcon";
import { NoiseCanvas } from "./NoiseCanvas";

export function HeroAside() {
  return (
    <aside className="layout-aside flex flex-col justify-between p-10 shadow-2xl text-[var(--ink)]">
      <NoiseCanvas />
      <div className="panel-gradient" style={{ position: "absolute", inset: 0, zIndex: -1 }} />

      <div className="relative z-10 flex items-center gap-2.5">
        <AgentDriveMark className="h-7 w-7 text-[var(--ink)]" />
        <span className="font-geist text-[1.15rem] font-semibold tracking-tight text-[var(--ink)]">
          Agent Drive
        </span>
      </div>

      <div className="relative z-10 mb-12 flex w-full flex-col justify-center">
        <h1 className="font-geist mb-6 text-[2.5rem] leading-[1.1] font-bold tracking-tight text-[var(--ink)]">
          Agent Drive builds datasets for humans and agents.
        </h1>
        <p className="font-geist mb-10 text-lg leading-relaxed font-light text-[var(--ink-dim)]">
          Most AI outputs are only as good as the data behind them. We&apos;re building the layer
          that fixes that — one domain at a time.
        </p>

        <div className="flex flex-col items-start gap-4">
          <div className="flex items-center gap-4">
            <a
              href="/sign-in"
              className="group flex items-center gap-2 rounded-md bg-[var(--accent)] px-5 py-3 font-mono text-[0.7rem] font-medium tracking-wide text-[var(--bg)] uppercase transition-all hover:brightness-105"
            >
              Dashboard
              <ArrowRightIcon className="btn-arrow-icon h-3 w-3 text-[var(--bg)]" />
            </a>
            <Link
              href="#agent-access"
              className="border-b border-[var(--ink-dim)] bg-transparent pb-0.5 font-mono text-[0.7rem] font-medium tracking-wide text-[var(--ink)] uppercase transition-colors hover:border-[var(--ink)]"
            >
              Read the docs
            </Link>
          </div>
        </div>
      </div>

      <div className="relative z-10">
        <div className="flex items-center gap-3 font-mono text-[0.62rem] tracking-widest text-[var(--ink-dim)] uppercase">
          <span>agentdrive.so</span>
          <span className="text-[var(--ink-faint)]">—</span>
          <span>Est. 2024</span>
        </div>
      </div>
    </aside>
  );
}
