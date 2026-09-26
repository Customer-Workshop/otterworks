/**
 * Document DTOs for /documents. Document payloads are snake_case on the wire
 * (ported from Models/DocumentModels.cs).
 */
export interface CreateDocumentRequest {
  title: string;
}

export interface OtterDocument {
  id: string;
  title: string;
  content: string | null;
  content_type: string | null;
  owner_id: string | null;
  folder_id: string | null;
  is_deleted: boolean;
  word_count: number;
  version: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface DocumentListResponse {
  items: OtterDocument[];
  total: number;
  page: number;
  size: number;
  pages: number;
}
