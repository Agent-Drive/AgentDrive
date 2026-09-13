import type { FileStatus } from "../_lib/types";

const STYLES: Record<string, string> = {
  ready: "text-ready",
  failed: "text-failed",
  uploading: "text-progress",
  pending: "text-progress",
  processing: "text-progress",
};

export function StatusBadge({ status }: { status: FileStatus | string }) {
  return (
    <span className={`font-mono text-xs ${STYLES[status] ?? "text-steel"}`}>
      {status}
    </span>
  );
}
