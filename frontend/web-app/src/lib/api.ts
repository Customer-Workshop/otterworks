import { apiClient } from "./api-client";
import type {
  User,
  AuthTokens,
  LoginCredentials,
  RegisterCredentials,
  FileItem,
  Document,
  Notification,
  SearchResult,
  SearchFilters,
  ActivityItem,
  StorageUsage,
  UserSettings,
  PaginatedResponse,
  SharedUser,
} from "@/types";

// Raw shape returned by the file-service (snake_case, different field names)
interface RawFileItem {
  id: string;
  name: string;
  mime_type: string;
  size_bytes: number;
  s3_key: string;
  folder_id: string | null;
  owner_id: string;
  version: number;
  is_trashed: boolean;
  created_at: string;
  updated_at: string;
}

interface RawFileListResponse {
  files: RawFileItem[];
  total: number;
  page: number;
  page_size: number;
}

// Normalize a single file from the file-service format to the frontend FileItem shape
function mapRawFile(raw: RawFileItem): FileItem {
  return {
    id: raw.id,
    name: raw.name,
    mimeType: raw.mime_type ?? "application/octet-stream",
    size: raw.size_bytes ?? 0,
    parentId: raw.folder_id ?? null,
    ownerId: raw.owner_id ?? "",
    ownerName: "",
    isFolder: false,
    path: `/${raw.name}`,
    sharedWith: [],
    tags: [],
    createdAt: raw.created_at ?? "",
    updatedAt: raw.updated_at ?? "",
    versions: [],
  };
}

// ── Auth ──────────────────────────────────────────────────────
export const authApi = {
  login: async (credentials: LoginCredentials): Promise<AuthTokens> => {
    const { data } = await apiClient.post<AuthTokens>("/auth/login", credentials);
    return data;
  },
  register: async (credentials: RegisterCredentials): Promise<AuthTokens> => {
    const { displayName, email, password } = credentials;
    const { data } = await apiClient.post<AuthTokens>("/auth/register", {
      displayName,
      email,
      password,
    });
    return data;
  },
  getProfile: async (): Promise<User> => {
    const { data } = await apiClient.get<User>("/auth/profile");
    return data;
  },
  updateProfile: async (updates: Partial<User>): Promise<User> => {
    const { data } = await apiClient.patch<User>("/auth/profile", updates);
    return data;
  },
  logout: async (): Promise<void> => {
    await apiClient.post("/auth/logout");
  },
};

// ── Files ─────────────────────────────────────────────────────
export const filesApi = {
  list: async (
    parentId?: string | null,
    page = 1,
    pageSize = 50
  ): Promise<PaginatedResponse<FileItem>> => {
    // file-service uses folder_id, not parentId
    const params: Record<string, string | number> = { page, pageSize };
    if (parentId) params.folder_id = parentId;
    const { data } = await apiClient.get<RawFileListResponse>("/files", { params });
    return {
      data: (data.files ?? []).map(mapRawFile),
      total: data.total ?? 0,
      page: data.page ?? page,
      pageSize: data.page_size ?? pageSize,
      hasMore: ((data.page ?? page) * (data.page_size ?? pageSize)) < (data.total ?? 0),
    };
  },
  get: async (id: string): Promise<FileItem> => {
    const { data } = await apiClient.get<RawFileItem>(`/files/${id}`);
    return mapRawFile(data);
  },
  upload: async (file: File, parentId?: string | null): Promise<FileItem> => {
    const formData = new FormData();
    formData.append("file", file);
    // file-service uses folder_id, not parentId
    if (parentId) formData.append("folder_id", parentId);
    const { data } = await apiClient.post<{ file: RawFileItem }>("/files/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return mapRawFile(data.file);
  },
  createFolder: async (name: string, parentId?: string | null): Promise<FileItem> => {
    const { data } = await apiClient.post<FileItem>("/files/folder", { name, parentId });
    return data;
  },
  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/files/${id}`);
  },
  share: async (id: string, users: SharedUser[]): Promise<void> => {
    await apiClient.post(`/files/${id}/share`, { users });
  },
  restore: async (id: string): Promise<void> => {
    await apiClient.post(`/files/${id}/restore`);
  },
  getShared: async (page = 1, pageSize = 50): Promise<PaginatedResponse<FileItem>> => {
    const { data } = await apiClient.get<PaginatedResponse<FileItem>>("/files/shared", {
      params: { page, pageSize },
    });
    return data;
  },
  getTrashed: async (page = 1, pageSize = 50): Promise<PaginatedResponse<FileItem>> => {
    const { data } = await apiClient.get<PaginatedResponse<FileItem>>("/files/trash", {
      params: { page, pageSize },
    });
    return data;
  },
  permanentDelete: async (id: string): Promise<void> => {
    await apiClient.delete(`/files/${id}/permanent`);
  },
  getRecent: async (limit = 10): Promise<FileItem[]> => {
    // The file-service has no /recent endpoint; fetch the first page and
    // return the most recently uploaded files sorted by createdAt descending.
    const { data } = await apiClient.get<RawFileListResponse>("/files", {
      params: { page: 1, pageSize: 50 },
    });
    return (data.files ?? [])
      .map(mapRawFile)
      .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
      .slice(0, limit);
  },
};

// ── Documents ─────────────────────────────────────────────────
export const documentsApi = {
  list: async (page = 1, pageSize = 50): Promise<PaginatedResponse<Document>> => {
    const { data } = await apiClient.get<PaginatedResponse<Document>>("/documents", {
      params: { page, pageSize },
    });
    return data;
  },
  get: async (id: string): Promise<Document> => {
    const { data } = await apiClient.get<Document>(`/documents/${id}`);
    return data;
  },
  create: async (title: string, parentId?: string | null): Promise<Document> => {
    const { data } = await apiClient.post<Document>("/documents", { title, parentId });
    return data;
  },
  update: async (id: string, updates: Partial<Document>): Promise<Document> => {
    const { data } = await apiClient.patch<Document>(`/documents/${id}`, updates);
    return data;
  },
  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/documents/${id}`);
  },
  share: async (id: string, users: SharedUser[]): Promise<void> => {
    await apiClient.post(`/documents/${id}/share`, { users });
  },
  restore: async (id: string): Promise<void> => {
    await apiClient.post(`/documents/${id}/restore`);
  },
  getRecent: async (limit = 10): Promise<Document[]> => {
    const { data } = await apiClient.get<Document[]>("/documents/recent", {
      params: { limit },
    });
    return data;
  },
};

// ── Search ────────────────────────────────────────────────────
export const searchApi = {
  search: async (filters: SearchFilters): Promise<PaginatedResponse<SearchResult>> => {
    const { data } = await apiClient.get<PaginatedResponse<SearchResult>>("/search", {
      params: filters,
    });
    return data;
  },
  suggest: async (query: string): Promise<string[]> => {
    const { data } = await apiClient.get<string[]>("/search/suggest", {
      params: { query },
    });
    return data;
  },
};

// ── Notifications ─────────────────────────────────────────────
export const notificationsApi = {
  list: async (page = 1, pageSize = 20): Promise<PaginatedResponse<Notification>> => {
    const { data } = await apiClient.get<PaginatedResponse<Notification>>("/notifications", {
      params: { page, pageSize },
    });
    return data;
  },
  markRead: async (id: string): Promise<void> => {
    await apiClient.patch(`/notifications/${id}/read`);
  },
  markAllRead: async (): Promise<void> => {
    await apiClient.post("/notifications/read-all");
  },
  getUnreadCount: async (): Promise<number> => {
    const { data } = await apiClient.get<{ count: number }>("/notifications/unread-count");
    return data.count;
  },
};

// ── Activity ──────────────────────────────────────────────────
export const activityApi = {
  getRecent: async (limit = 20): Promise<ActivityItem[]> => {
    const { data } = await apiClient.get<ActivityItem[]>("/activity/recent", {
      params: { limit },
    });
    return data;
  },
};

// ── Storage ───────────────────────────────────────────────────
export const storageApi = {
  getUsage: async (): Promise<StorageUsage> => {
    const { data } = await apiClient.get<StorageUsage>("/storage/usage");
    return data;
  },
};

// ── Settings ──────────────────────────────────────────────────
export const settingsApi = {
  get: async (): Promise<UserSettings> => {
    const { data } = await apiClient.get<UserSettings>("/settings");
    return data;
  },
  update: async (settings: Partial<UserSettings>): Promise<UserSettings> => {
    const { data } = await apiClient.patch<UserSettings>("/settings", settings);
    return data;
  },
};
