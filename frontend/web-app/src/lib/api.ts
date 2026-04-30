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

// ── Helpers ───────────────────────────────────────────────────
// Extract the user ID from the JWT stored in localStorage.
function getOwnerIdFromJwt(): string | null {
  if (typeof window === "undefined") return null;
  const token = localStorage.getItem("otter_access_token");
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, '+').replace(/_/g, '/')));
    return payload.sub ?? null;
  } catch {
    return null;
  }
}

// Backend file objects use different field names — normalise to frontend FileItem shape.
function normalizeFileItem(raw: Record<string, unknown>): FileItem {
  return {
    ...raw,
    size: (raw.sizeBytes ?? raw.size ?? 0) as number,
    mimeType: (raw.mimeType ?? raw.contentType ?? "") as string,
    parentId: (raw.folderId ?? raw.parentId ?? null) as string | null,
    isFolder: (raw.isFolder ?? false) as boolean,
    ownerName: (raw.ownerName ?? "") as string,
    path: (raw.path ?? "") as string,
    sharedWith: (raw.sharedWith ?? []) as SharedUser[],
    tags: (raw.tags ?? []) as string[],
    versions: (raw.versions ?? []) as FileItem["versions"],
  } as FileItem;
}

// ── Files ─────────────────────────────────────────────────────
export const filesApi = {
  list: async (
    parentId?: string | null,
    page = 1,
    pageSize = 50
  ): Promise<PaginatedResponse<FileItem>> => {
    const params: Record<string, string | number> = { page, page_size: pageSize };
    if (parentId) params.folder_id = parentId;
    const { data } = await apiClient.get<any>("/files", { params });
    // Backend returns { files: [...], total, page, pageSize } — normalise to PaginatedResponse
    const rawItems = data.files ?? data.data ?? [];
    const items: FileItem[] = rawItems.map(normalizeFileItem);
    return {
      data: items,
      total: data.total ?? items.length,
      page: data.page ?? page,
      pageSize: data.pageSize ?? pageSize,
      hasMore: (data.page ?? page) * (data.pageSize ?? pageSize) < (data.total ?? items.length),
    };
  },
  get: async (id: string): Promise<FileItem> => {
    const { data } = await apiClient.get<any>(`/files/${id}`);
    return normalizeFileItem(data);
  },
  upload: async (file: File, parentId?: string | null): Promise<FileItem> => {
    const formData = new FormData();
    formData.append("file", file);
    if (parentId) formData.append("folder_id", parentId);

    // The file-service requires owner_id — extract it from the JWT sub claim
    const ownerId = getOwnerIdFromJwt();
    if (ownerId) formData.append("owner_id", ownerId);

    const { data } = await apiClient.post<any>("/files/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    // Backend wraps response in { file: {...} }
    const raw = data.file ?? data;
    return normalizeFileItem(raw);
  },
  createFolder: async (name: string, parentId?: string | null): Promise<FileItem> => {
    const ownerId = getOwnerIdFromJwt();
    const { data } = await apiClient.post<any>("/folders", {
      name,
      parent_id: parentId ?? null,
      owner_id: ownerId,
    });
    return normalizeFileItem(data);
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
    const { data } = await apiClient.get<any>("/files/shared", {
      params: { page, page_size: pageSize },
    });
    const items = (data.data ?? data.files ?? []).map(normalizeFileItem);
    return {
      data: items,
      total: data.total ?? items.length,
      page: data.page ?? page,
      pageSize: data.pageSize ?? pageSize,
      hasMore: (data.page ?? page) * (data.pageSize ?? pageSize) < (data.total ?? items.length),
    };
  },
  getTrashed: async (page = 1, pageSize = 50): Promise<PaginatedResponse<FileItem>> => {
    const { data } = await apiClient.get<any>("/files/trash", {
      params: { page, page_size: pageSize },
    });
    const items = (data.data ?? data.files ?? []).map(normalizeFileItem);
    return {
      data: items,
      total: data.total ?? items.length,
      page: data.page ?? page,
      pageSize: data.pageSize ?? pageSize,
      hasMore: (data.page ?? page) * (data.pageSize ?? pageSize) < (data.total ?? items.length),
    };
  },
  permanentDelete: async (id: string): Promise<void> => {
    await apiClient.delete(`/files/${id}/permanent`);
  },
  getRecent: async (limit = 10): Promise<FileItem[]> => {
    const { data } = await apiClient.get<any[]>("/files/recent", {
      params: { limit },
    });
    return (Array.isArray(data) ? data : []).map(normalizeFileItem);
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
