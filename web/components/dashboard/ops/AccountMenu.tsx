"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOutAction } from "@/lib/dashboard/actions";
import { ChevronRightIcon, LogOutIcon, SettingsIcon } from "./OpsIcons";

type AccountMenuProps = {
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

const itemClass =
  "flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left font-mono text-[0.7rem] text-[var(--ink-dim)] transition-colors hover:bg-[rgba(255,255,255,0.04)] hover:text-[var(--ink)]";

export function AccountMenu({ firstName, lastName, email }: AccountMenuProps) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const onSettings = pathname.startsWith("/dashboard/settings");

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!open) return;

    function onPointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      {open ? (
        <div
          role="menu"
          aria-label="Account"
          className="absolute inset-x-0 bottom-full mb-1 rounded-md border border-[var(--border)] bg-[var(--surface)] p-1"
        >
          <Link href="/dashboard/settings" role="menuitem" className={itemClass}>
            <SettingsIcon className="h-3.5 w-3.5 opacity-70" />
            Settings
          </Link>
          <form action={signOutAction}>
            <button type="submit" role="menuitem" className={itemClass}>
              <LogOutIcon className="h-3.5 w-3.5 opacity-70" />
              Log out
            </button>
          </form>
        </div>
      ) : null}

      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((value) => !value)}
        className={
          onSettings || open
            ? "group flex w-full cursor-pointer items-center gap-2 rounded-md bg-[rgba(255,255,255,0.04)] px-2 py-1.5 text-left transition-colors"
            : "group flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-[rgba(255,255,255,0.04)]"
        }
      >
        <div className="flex h-6 w-6 items-center justify-center rounded-md bg-[var(--accent-dim)] font-mono text-[0.6rem] font-medium text-[var(--accent)]">
          {initials(firstName, lastName, email)}
        </div>
        <div className="flex min-w-0 flex-col">
          <span className="truncate text-[0.7rem] leading-tight font-medium text-[var(--ink)]">
            {displayName(firstName, lastName, email)}
          </span>
          <span className="mt-0.5 font-mono text-[0.6rem] leading-tight text-[var(--ink-dim)]">
            Basic
          </span>
        </div>
        <ChevronRightIcon
          className={`ml-auto h-3.5 w-3.5 text-[var(--ink-dim)] transition-transform${open ? " -rotate-90 opacity-100" : " opacity-0 group-hover:opacity-100"}`}
        />
      </button>
    </div>
  );
}
