import Link from "next/link";
import type { DriveFile } from "../_lib/types";
import { formatBytes, formatWhen } from "../_lib/format";
import { EmptyFiles } from "./EmptyFiles";
import { StatusBadge } from "./StatusBadge";

export function FileTable({ files }: { files: DriveFile[] }) {
  if (files.length === 0) {
    return <EmptyFiles />;
  }

  return (
    <div className="overflow-x-auto border-t border-rule">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-rule text-steel">
            <th className="py-2 pr-4 font-medium">File</th>
            <th className="py-2 pr-4 font-medium">Status</th>
            <th className="py-2 pr-4 font-medium">Size</th>
            <th className="py-2 font-medium">Updated</th>
          </tr>
        </thead>
        <tbody>
          {files.map((file) => (
            <tr key={file.id} className="border-b border-rule">
              <td className="py-3 pr-4">
                <Link href={`/dashboard/files/${file.id}`} className="hover:text-cobalt">
                  {file.filename}
                </Link>
              </td>
              <td className="py-3 pr-4">
                <StatusBadge status={file.status} />
                {file.current_phase && file.status !== "ready" && file.status !== "failed" ? (
                  <span className="ml-2 text-xs text-steel">{file.current_phase}</span>
                ) : null}
              </td>
              <td className="py-3 pr-4 font-mono text-xs">{formatBytes(file.file_size)}</td>
              <td className="py-3 text-steel">{formatWhen(file.updated_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
