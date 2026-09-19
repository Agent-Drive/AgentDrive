import Link from "next/link";
import { getFile } from "@/lib/dashboard/api";
import { formatBytes, formatWhen } from "@/lib/dashboard/format";
import { OpsStatusBadge } from "@/components/dashboard/ops/OpsStatusBadge";

export default async function FileDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const file = await getFile(id);

  return (
    <>
      <Link
        href="/dashboard"
        className="mb-3 font-mono text-[0.6rem] text-[var(--ink-dim)] hover:text-[var(--accent)]"
      >
        ← Overview
      </Link>
      <h1 className="font-geist text-lg font-medium tracking-tight text-[var(--ink)]">
        {file.filename}
      </h1>
      <dl className="mt-5 grid max-w-xl grid-cols-2 gap-x-6 gap-y-3 text-[0.75rem]">
        <dt className="text-[var(--ink-dim)]">Status</dt>
        <dd>
          <OpsStatusBadge status={file.status} />
        </dd>
        <dt className="text-[var(--ink-dim)]">Type</dt>
        <dd className="font-mono text-[0.65rem]">{file.content_type}</dd>
        <dt className="text-[var(--ink-dim)]">Size</dt>
        <dd className="font-mono text-[0.65rem]">{formatBytes(file.file_size)}</dd>
        <dt className="text-[var(--ink-dim)]">Chunks</dt>
        <dd>{file.chunk_count ?? "—"}</dd>
        <dt className="text-[var(--ink-dim)]">Updated</dt>
        <dd>{formatWhen(file.updated_at)}</dd>
        {file.current_phase ? (
          <>
            <dt className="text-[var(--ink-dim)]">Phase</dt>
            <dd>{file.current_phase}</dd>
          </>
        ) : null}
      </dl>
    </>
  );
}
