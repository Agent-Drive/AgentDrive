import { getFile } from "../../_lib/api";
import { formatBytes, formatWhen } from "../../_lib/format";
import { StatusBadge } from "../../_components/StatusBadge";

export default async function FileDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const file = await getFile(id);

  return (
    <main>
      <h1 className="font-display text-4xl tracking-tight">{file.filename}</h1>
      <dl className="mt-8 grid max-w-xl grid-cols-2 gap-x-6 gap-y-4 text-sm">
        <dt className="text-steel">Status</dt>
        <dd>
          <StatusBadge status={file.status} />
        </dd>
        <dt className="text-steel">Type</dt>
        <dd>{file.content_type}</dd>
        <dt className="text-steel">Size</dt>
        <dd className="font-mono text-xs">{formatBytes(file.file_size)}</dd>
        <dt className="text-steel">Chunks</dt>
        <dd>{file.chunk_count ?? "—"}</dd>
        <dt className="text-steel">Updated</dt>
        <dd>{formatWhen(file.updated_at)}</dd>
        {file.current_phase ? (
          <>
            <dt className="text-steel">Phase</dt>
            <dd>{file.current_phase}</dd>
          </>
        ) : null}
      </dl>
    </main>
  );
}
