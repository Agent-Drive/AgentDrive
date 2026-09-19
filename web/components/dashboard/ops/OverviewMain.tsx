"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { searchCorpusAction } from "@/lib/dashboard/actions";
import type { DriveFile, SearchHit } from "@/lib/dashboard/types";
import { SearchIcon } from "./OpsIcons";
import { OpsFileTable } from "./OpsFileTable";

function fileNameFor(hit: SearchHit, filesById: Map<string, string>) {
  const fileId = typeof hit.provenance.file_id === "string" ? hit.provenance.file_id : "";
  if (typeof hit.provenance.filename === "string" && hit.provenance.filename) {
    return hit.provenance.filename;
  }
  if (fileId && filesById.has(fileId)) {
    return filesById.get(fileId) as string;
  }
  return fileId || "Unknown file";
}

function snippetText(hit: SearchHit) {
  const text = hit.content.trim();
  return text.length > 280 ? `${text.slice(0, 280)}…` : text;
}

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
          <OpsFileTable files={files} />
        ) : hits === undefined ? (
          <p className="px-3 py-3 font-mono text-[0.65rem] text-[var(--ink-dim)]">Searching…</p>
        ) : hits === null ? (
          <OpsFileTable files={filtered} />
        ) : hits.length > 0 ? (
          <div>
            {hits.map((hit) => {
              const fileId = typeof hit.provenance.file_id === "string" ? hit.provenance.file_id : "";
              const name = fileNameFor(hit, filesById);
              return (
                <div key={hit.chunk_id} className="search-hit">
                  <p className="font-geist text-[0.75rem] leading-relaxed text-[rgba(240,244,248,0.85)]">
                    {snippetText(hit)}
                  </p>
                  {fileId ? (
                    <Link
                      href={`/dashboard/files/${fileId}`}
                      className="mt-1.5 inline-block font-mono text-[0.6rem] text-[var(--accent)]"
                    >
                      {name}
                    </Link>
                  ) : (
                    <p className="mt-1.5 font-mono text-[0.6rem] text-[var(--accent)]">{name}</p>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <p className="px-3 py-3 font-mono text-[0.65rem] text-[var(--ink-dim)]">No matching passages.</p>
        )}
      </div>
    </>
  );
}
