export interface User {
  id: string;
  email: string;
  displayName: string;
  role: 'admin' | 'editor' | 'viewer';
  status: 'active' | 'suspended' | 'pending';
  avatarUrl?: string;
  storageUsed: number;
  storageQuota: number;
  lastLogin: string;
  createdAt: string;
  department?: string;
  documentsCount: number;
}

export interface UserActivity {
  id: string;
  userId: string;
  action: string;
  resource: string;
  timestamp: string;
  details?: string;
  ipAddress?: string;
}
