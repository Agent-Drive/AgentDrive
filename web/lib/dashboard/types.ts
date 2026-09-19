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

export type ApiKey = {
  id: string;
  key_prefix: string;
  name: string | null;
  created_at: string;
  expires_at: string | null;
  revoked_at: string | null;
  last_used: string | null;
};

export type ApiKeyListResponse = {
  api_keys: ApiKey[];
  total: number;
};

export type ApiKeyCreateResponse = {
  id: string;
  key: string;
  key_prefix: string;
  name: string | null;
  created_at: string;
  expires_at: string | null;
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
