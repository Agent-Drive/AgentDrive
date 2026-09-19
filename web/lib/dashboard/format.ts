export const STORAGE_CAP_BYTES = 1024 ** 4;

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

export function formatCompactBytes(bytes: number): string {
  if (bytes >= 1024 ** 4) return `${(bytes / 1024 ** 4).toFixed(bytes % 1024 ** 4 === 0 ? 0 : 1)}TB`;
  if (bytes >= 1024 ** 3) return `${Math.round(bytes / 1024 ** 3)}GB`;
  if (bytes >= 1024 ** 2) return `${Math.round(bytes / 1024 ** 2)}MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)}KB`;
  return `${bytes}B`;
}

export function formatFileLabel(contentType: string, filename: string): string {
  if (contentType.startsWith("video/")) return "video";
  if (contentType.startsWith("image/")) return "image";
  if (contentType.includes("pdf")) return "pdf";
  if (contentType.includes("spreadsheet") || contentType.includes("csv") || filename.endsWith(".csv")) {
    return "csv";
  }
  const ext = filename.includes(".") ? filename.split(".").pop()?.toLowerCase() : "";
  if (ext) return ext;
  const subtype = contentType.split("/")[1];
  return subtype || "file";
}

export function formatWhen(iso: string): string {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso));
}
