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
    if (parentId) formData.append("folder_id", parentId);

    // The file-service requires owner_id — extract it from the JWT sub claim
    const ownerId = getOwnerIdFromJwt();
    if (ownerId) formData.append("owner_id", ownerId);

    const { data } = await apiClient.post<{ file: RawFileItem }>("/files/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    // Backend wraps response in { file: {...} }
    const raw = data.file ?? (data as unknown as RawFileItem);
    return mapRawFile(raw);
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
    const params: Record<string, string | number> = { page: 1, page_size: limit };
    const { data } = await apiClient.get<RawFileListResponse>("/files", { params });
    return (data.files ?? []).map(mapRawFile);
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
    const { data } = await apiClient.get<{ items?: Document[] }>("/documents", {
      params: { page: 1, size: limit },
    });
    return data.items ?? [];
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
  getRecent: async (_limit = 20): Promise<ActivityItem[]> => {
    // Activity service endpoint does not exist yet; return empty list
    // to avoid dashboard errors.
    return [];
  },
};

// ── Storage ───────────────────────────────────────────────────
export const storageApi = {
  getUsage: async (): Promise<StorageUsage> => {
    // The /storage/usage endpoint is not routed. Compute stats from
    // existing file and document list endpoints instead.
    const [fileRes, docRes] = await Promise.all([
      apiClient.get<RawFileListResponse>("/files", { params: { page: 1, page_size: 1 } }),
      apiClient.get<{ total?: number }>("/documents", { params: { page: 1, size: 1 } }),
    ]);

    const fileCount = fileRes.data.total ?? 0;
    const documentCount = docRes.data.total ?? 0;

    // Fetch all files to sum storage (only when there are files)
    let used = 0;
    if (fileCount > 0) {
      const allFiles = await apiClient.get<RawFileListResponse>("/files", {
        params: { page: 1, page_size: fileCount },
      });
      // The axios interceptor transforms size_bytes → sizeBytes at runtime.
      // Access both forms to work before and after the camelCase fix (PR #34).
      used = (allFiles.data.files ?? []).reduce(
        (sum, f) => {
          const raw = f as unknown as Record<string, number>;
          return sum + (raw.sizeBytes ?? raw.size_bytes ?? 0);
        },
        0,
      );
    }

    return {
      used,
      total: 10 * 1024 * 1024 * 1024, // 10 GB default quota
      fileCount,
      documentCount,
    };
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
