/**
 * File DTOs for /files. File payloads are snake_case on the wire
 * (ported from Models/FileModels.cs).
 */
export interface FileItem {
  id: string;
  name: string;
  size: number | null;
  content_type: string | null;
  created_at: string | null;
}

export interface FileListResponse {
  files: FileItem[];
  total: number;
  page: number;
  page_size: number;
}
