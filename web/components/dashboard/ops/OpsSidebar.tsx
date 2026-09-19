"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOutAction } from "@/lib/dashboard/actions";
import { STORAGE_CAP_BYTES, formatCompactBytes } from "@/lib/dashboard/format";
import { ActivityIcon, ChevronRightIcon, KeyIcon } from "./OpsIcons";

type OpsSidebarProps = {
  usedBytes: number;
  firstName: string | null;
  lastName: string | null;
  email: string | null;
};

function initials(firstName: string | null, lastName: string | null, email: string | null) {
  const first = firstName?.trim().charAt(0);
  const last = lastName?.trim().charAt(0);
  if (first && last) return `${first}${last}`.toUpperCase();
  if (first) return first.toUpperCase();
  const fromEmail = email?.trim().charAt(0);
  return (fromEmail ?? "?").toUpperCase();
}

function displayName(firstName: string | null, lastName: string | null, email: string | null) {
  const name = `${firstName ?? ""} ${lastName ?? ""}`.trim();
  return name || email || "Account";
}

const NAV = [
  { href: "/dashboard", label: "Overview", icon: ActivityIcon, exact: true },
  { href: "/dashboard/keys", label: "API keys", icon: KeyIcon, exact: false },
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
          <form action={signOutAction}>
            <button
              type="submit"
              className="group flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-[rgba(255,255,255,0.04)]"
            >
              <div className="flex h-6 w-6 items-center justify-center rounded-md bg-[var(--accent-dim)] font-mono text-[0.6rem] font-medium text-[var(--accent)]">
                {initials(firstName, lastName, email)}
              </div>
              <div className="flex min-w-0 flex-col">
                <span className="truncate text-[0.7rem] leading-tight font-medium text-[var(--ink)]">
                  {displayName(firstName, lastName, email)}
                </span>
                <span className="mt-0.5 font-mono text-[0.6rem] leading-tight text-[var(--ink-dim)]">
                  Admin
                </span>
              </div>
              <ChevronRightIcon className="ml-auto h-3.5 w-3.5 text-[var(--ink-dim)] opacity-0 transition-opacity group-hover:opacity-100" />
            </button>
          </form>
        </div>
      </div>
    </aside>
  );
}
