export interface Announcement {
  id: string;
  title: string;
  content: string;
  priority: 'low' | 'medium' | 'high' | 'critical';
  status: 'draft' | 'published' | 'archived';
  createdAt: string;
  publishedAt?: string;
  expiresAt?: string;
  createdBy: string;
  targetAudience: 'all' | 'admins' | 'editors' | 'viewers';
}
