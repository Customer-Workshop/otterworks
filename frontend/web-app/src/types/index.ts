// ============================================================
// OtterWorks Shared Types
// ============================================================

export interface User {
  readonly id: string;
  readonly email: string;
  readonly displayName: string;
  readonly avatarUrl?: string;
  readonly createdAt?: string;
  readonly updatedAt?: string;
}

export interface AuthTokens {
  readonly accessToken: string;
  readonly refreshToken: string;
  readonly expiresAt: number;
}

export interface LoginCredentials {
  readonly email: string;
  readonly password: string;
}

export interface RegisterCredentials {
  readonly displayName: string;
  readonly email: string;
  readonly password: string;
  readonly confirmPassword: string;
}

export interface FileItem {
  readonly id: string;
  readonly name: string;
  readonly mimeType: string;
  readonly size: number;
  readonly parentId: string | null;
  readonly ownerId: string;
  readonly ownerName: string;
  readonly isFolder: boolean;
  readonly isTrashed?: boolean;
  readonly path: string;
  readonly thumbnailUrl?: string;
  readonly downloadUrl?: string;
  readonly sharedWith: SharedUser[];
  readonly tags: string[];
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly trashedAt?: string;
  readonly versions: FileVersion[];
}

export interface FileVersion {
  readonly id: string;
  readonly fileId: string;
  readonly versionNumber: number;
  readonly size: number;
  readonly uploadedBy: string;
  readonly createdAt: string;
  readonly downloadUrl: string;
}

export interface SharedUser {
  readonly userId: string;
  readonly name: string;
  readonly email: string;
  readonly avatarUrl?: string;
  readonly permission: "view" | "edit" | "admin";
}

export interface Document {
  readonly id: string;
  readonly title: string;
  readonly content: string;
  readonly ownerId: string;
  readonly ownerName: string;
  readonly parentId: string | null;
  readonly sharedWith: SharedUser[];
  readonly collaborators: Collaborator[];
  readonly tags: string[];
  readonly wordCount: number;
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly trashedAt?: string;
}

export interface Collaborator {
  readonly userId: string;
  readonly name: string;
  readonly avatarUrl?: string;
  readonly color: string;
  readonly isOnline: boolean;
}

export interface Notification {
  readonly id: string;
  readonly type: "share" | "comment" | "mention" | "edit" | "system";
  readonly title: string;
  readonly message: string;
  readonly read: boolean;
  readonly actorId?: string;
  readonly actorName?: string;
  readonly actorAvatarUrl?: string;
  readonly resourceId?: string;
  readonly resourceType?: "file" | "document";
  readonly createdAt: string;
}

export interface SearchResult {
  readonly id: string;
  readonly type: "file" | "document" | "folder";
  readonly name: string;
  readonly snippet?: string;
  readonly path: string;
  readonly updatedAt: string;
  readonly ownerName: string;
}

export interface SearchFilters {
  readonly query: string;
  readonly type?: "file" | "document" | "folder" | "all";
  readonly dateFrom?: string;
  readonly dateTo?: string;
  readonly owner?: string;
  readonly tags?: string[];
}

export interface ActivityItem {
  readonly id: string;
  readonly type: "upload" | "edit" | "share" | "comment" | "delete" | "restore";
  readonly description: string;
  readonly actorName: string;
  readonly actorAvatarUrl?: string;
  readonly resourceName: string;
  readonly resourceType: "file" | "document";
  readonly resourceId: string;
  readonly createdAt: string;
}

export interface StorageUsage {
  readonly used: number;
  readonly total: number;
  readonly fileCount: number;
  readonly documentCount: number;
}

export interface UserSettings {
  readonly notificationEmail: boolean;
  readonly notificationInApp: boolean;
  readonly notificationDesktop: boolean;
  readonly theme: "light" | "dark" | "system";
  readonly language: string;
}

export interface PaginatedResponse<T> {
  readonly data: T[];
  readonly total: number;
  readonly page: number;
  readonly pageSize: number;
  readonly hasMore: boolean;
}

export type ViewMode = "grid" | "list";

export type SortField = "name" | "updatedAt" | "size" | "createdAt";
export type SortDirection = "asc" | "desc";

export interface SortConfig {
  readonly field: SortField;
  readonly direction: SortDirection;
}
