import type { FileStatus } from "@/lib/dashboard/types";

function labelFor(status: string): { text: string; className: string } {
  if (status === "ready") return { text: "indexed", className: "status-ok" };
  if (status === "failed") return { text: "failed", className: "status-err" };
  if (status === "processing" || status === "pending" || status === "uploading") {
    return { text: "processing", className: "status-sync" };
  }
  return { text: status, className: "status-sync" };
}

export function OpsStatusBadge({ status }: { status: FileStatus | string }) {
  const { text, className } = labelFor(status);
  return <span className={`status-badge ${className}`}>{text}</span>;
}
