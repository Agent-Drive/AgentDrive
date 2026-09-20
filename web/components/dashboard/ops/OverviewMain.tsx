"use client";

import { useEffect, useMemo, useState } from "react";
import { searchCorpusAction } from "@/lib/dashboard/actions";
import type { DriveFile, SearchHit } from "@/lib/dashboard/types";
import { SearchIcon } from "./OpsIcons";
import { OpsFileTable } from "./OpsFileTable";
import { SearchHitList } from "./SearchHitList";

export function OverviewMain({ files }: { files: DriveFile[] }) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null | undefined>([]);

  const filesById = useMemo(
    () => new Map(files.map((file) => [file.id, file.filename])),
    [files],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return files;
    return files.filter((file) => file.filename.toLowerCase().includes(q));
  }, [files, query]);

  useEffect(() => {
    const q = query.trim();
    if (!q) return;

    const handle = window.setTimeout(async () => {
      const results = await searchCorpusAction(q);
      setHits(results);
    }, 280);

    return () => window.clearTimeout(handle);
  }, [query]);

  const hasQuery = query.trim().length > 0;

  return (
    <>
      <div className="mb-3">
        <div className="ops-search">
          <SearchIcon className="h-3.5 w-3.5 text-[var(--ink-dim)]" />
          <input
            type="search"
            value={query}
            onChange={(event) => {
              const next = event.target.value;
              setQuery(next);
              setHits(next.trim() ? undefined : []);
            }}
            placeholder="Search files…"
            className="h-full w-full border-none bg-transparent font-sans text-[0.75rem] leading-none text-[var(--ink)] outline-none placeholder:text-[var(--ink-dim)]"
          />
        </div>
      </div>

      <div className="flex-grow overflow-auto rounded border border-[var(--border)] bg-[var(--surface)]">
        {!hasQuery ? (
          <div>
            <p className="px-3 pt-3 pb-1 font-mono text-[0.6rem] tracking-wide text-[var(--ink-dim)] uppercase">
              Recent
            </p>
            <OpsFileTable files={files} />
          </div>
        ) : hits === undefined ? (
          <p className="px-3 py-3 font-mono text-[0.65rem] text-[var(--ink-dim)]">Searching…</p>
        ) : hits === null ? (
          <OpsFileTable files={filtered} />
        ) : hits.length > 0 ? (
          <SearchHitList hits={hits} filesById={filesById} />
        ) : (
          <p className="px-3 py-3 font-mono text-[0.65rem] text-[var(--ink-dim)]">No matching passages.</p>
        )}
      </div>
    </>
  );
}
