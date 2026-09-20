"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { STORAGE_CAP_BYTES, formatCompactBytes } from "@/lib/dashboard/format";
import { AccountMenu } from "./AccountMenu";
import { FilesIcon } from "./OpsIcons";

type OpsSidebarProps = {
  usedBytes: number;
  firstName: string | null;
  lastName: string | null;
  email: string | null;
};

const NAV = [
  { href: "/dashboard", label: "Files", icon: FilesIcon, exact: true },
] as const;

export function OpsSidebar({ usedBytes, firstName, lastName, email }: OpsSidebarProps) {
  const pathname = usePathname();
  const used = Math.min(usedBytes, STORAGE_CAP_BYTES);
  const pct = Math.min(100, (used / STORAGE_CAP_BYTES) * 100);
  const warn = pct >= 70;

  return (
    <aside className="panel sider">
      <div
        className="panel-content"
        style={{ padding: "0.75rem 0.5rem 0.25rem", display: "flex", flexDirection: "column" }}
      >
        <div className="mb-3">
          <div className="api-card">
            <span className="api-name shrink-0">Storage</span>
            <span className={`api-latency shrink-0${warn ? " text-[var(--warning)]" : ""}`}>
              {formatCompactBytes(used)} / 1TB
            </span>
            <div className="sparkline ml-auto shrink-0">
              <div
                className={`spark-fill${warn ? " bg-[var(--warning)]" : ""}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        </div>

        <nav className="mb-2 flex flex-col gap-0.5">
          {NAV.map((item) => {
            const active = item.exact
              ? pathname === item.href
              : pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={
                  active
                    ? "group flex items-center gap-2 rounded-md bg-[var(--accent-dim)] px-2.5 py-1.5 text-[var(--accent)] transition-all"
                    : "group flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[var(--ink-dim)] transition-all hover:bg-[rgba(255,255,255,0.04)] hover:text-[var(--ink)]"
                }
              >
                <Icon
                  className={
                    active
                      ? "h-4 w-4 opacity-90"
                      : "h-4 w-4 opacity-60 transition-opacity group-hover:opacity-90"
                  }
                />
                <span className={`font-mono text-[0.7rem]${active ? " font-medium" : ""}`}>
                  {item.label}
                </span>
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto">
          <AccountMenu firstName={firstName} lastName={lastName} email={email} />
        </div>
      </div>
    </aside>
  );
}
