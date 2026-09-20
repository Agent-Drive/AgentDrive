export type FileStatus =
  | "uploading"
  | "pending"
  | "processing"
  | "ready"
  | "failed";

export type DriveFile = {
  id: string;
  filename: string;
  content_type: string;
  file_size: number;
  status: FileStatus | string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  chunk_count: number | null;
  total_batches: number;
  completed_batches: number;
  current_phase: string | null;
};

export type FileListResponse = {
  files: DriveFile[];
  total: number;
};

export type SearchHit = {
  chunk_id: string;
  content: string;
  token_count: number;
  score: number;
  content_type: string;
  parent_content: string | null;
  parent_token_count: number | null;
  provenance: {
    file_id?: string;
    filename?: string;
    [key: string]: unknown;
  };
};

export type SearchResponse = {
  results: SearchHit[];
  query_tokens: number;
  search_time_ms: number;
};

export type DownloadUrlResponse = {
  file_id: string;
  filename: string;
  download_url: string;
  expires_in_hours: number;
};
