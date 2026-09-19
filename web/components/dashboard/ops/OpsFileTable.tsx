import Link from "next/link";
import type { DriveFile } from "@/lib/dashboard/types";
import { formatFileLabel } from "@/lib/dashboard/format";
import { OpsStatusBadge } from "./OpsStatusBadge";

export function OpsFileTable({ files }: { files: DriveFile[] }) {
  if (files.length === 0) {
    return (
      <div className="flex flex-grow items-center justify-center px-4 py-10 font-mono text-[0.65rem] text-[var(--ink-dim)]">
        No files yet. Upload through MCP.
      </div>
    );
  }

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>File Name</th>
          <th>Format</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {files.map((file) => (
          <tr key={file.id}>
            <td>
              <Link href={`/dashboard/files/${file.id}`} className="ops-link">
                {file.filename}
              </Link>
            </td>
            <td>{formatFileLabel(file.content_type, file.filename)}</td>
            <td>
              <OpsStatusBadge status={file.status} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
