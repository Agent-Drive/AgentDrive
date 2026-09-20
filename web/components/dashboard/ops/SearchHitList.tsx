import Link from "next/link";
import type { SearchHit } from "@/lib/dashboard/types";

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

function passageText(hit: SearchHit) {
  const text = (hit.parent_content ?? hit.content).trim();
  return text.length > 280 ? `${text.slice(0, 280)}…` : text;
}

export function SearchHitList({
  hits,
  filesById,
}: {
  hits: SearchHit[];
  filesById: Map<string, string>;
}) {
  return (
    <div>
      {hits.map((hit) => {
        const fileId = typeof hit.provenance.file_id === "string" ? hit.provenance.file_id : "";
        const name = fileNameFor(hit, filesById);
        const body = (
          <>
            <p className="font-mono text-[0.75rem] text-[var(--ink)]">{name}</p>
            <p className="mt-1.5 font-geist text-[0.75rem] leading-relaxed text-[rgba(240,244,248,0.85)]">
              {passageText(hit)}
            </p>
          </>
        );

        if (!fileId) {
          return (
            <div key={hit.chunk_id} className="search-hit">
              {body}
            </div>
          );
        }

        return (
          <Link
            key={hit.chunk_id}
            href={`/dashboard/files/${fileId}`}
            className="search-hit"
          >
            {body}
          </Link>
        );
      })}
    </div>
  );
}
