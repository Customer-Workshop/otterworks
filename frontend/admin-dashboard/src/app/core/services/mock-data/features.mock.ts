import { FeatureFlag } from '../../models/feature-flag.model';

export const MOCK_FEATURE_FLAGS: FeatureFlag[] = [
  {
    id: 'ff-001', name: 'Real-time Collaboration', key: 'real-time-collab',
    description: 'Enable CRDT-based real-time collaborative editing for documents',
    enabled: true, category: 'Collaboration', updatedAt: '2026-04-15T12:00:00Z', updatedBy: 'Frank Wilson',
  },
  {
    id: 'ff-002', name: 'AI Document Summary', key: 'ai-doc-summary',
    description: 'Generate AI-powered summaries for uploaded documents',
    enabled: false, category: 'AI Features', updatedAt: '2026-04-10T09:00:00Z', updatedBy: 'Alice Johnson',
  },
  {
    id: 'ff-003', name: 'Advanced Search', key: 'advanced-search',
    description: 'Enable full-text search with filters powered by OpenSearch',
    enabled: true, category: 'Search', updatedAt: '2026-04-12T14:00:00Z', updatedBy: 'Frank Wilson',
  },
  {
    id: 'ff-004', name: 'File Versioning', key: 'file-versioning',
    description: 'Track and restore previous versions of uploaded files',
    enabled: true, category: 'Storage', updatedAt: '2026-03-28T10:00:00Z', updatedBy: 'Alice Johnson',
  },
  {
    id: 'ff-005', name: 'Webhook Notifications', key: 'webhook-notifications',
    description: 'Allow users to configure webhook endpoints for event notifications',
    enabled: false, category: 'Notifications', updatedAt: '2026-04-01T11:00:00Z', updatedBy: 'Frank Wilson',
  },
  {
    id: 'ff-006', name: 'Dark Mode', key: 'dark-mode',
    description: 'Enable dark mode theme toggle for the web application',
    enabled: true, category: 'UI', updatedAt: '2026-04-08T16:00:00Z', updatedBy: 'Carol Chen',
  },
  {
    id: 'ff-007', name: 'Bulk File Operations', key: 'bulk-file-ops',
    description: 'Allow selecting and performing operations on multiple files at once',
    enabled: false, category: 'Storage', updatedAt: '2026-04-05T09:00:00Z', updatedBy: 'Alice Johnson',
  },
  {
    id: 'ff-008', name: 'Public Link Sharing', key: 'public-link-sharing',
    description: 'Generate public shareable links for documents and files',
    enabled: true, category: 'Collaboration', updatedAt: '2026-03-20T13:00:00Z', updatedBy: 'Frank Wilson',
  },
  {
    id: 'ff-009', name: 'Usage Analytics Dashboard', key: 'usage-analytics',
    description: 'Show detailed usage analytics and reports for admin users',
    enabled: true, category: 'Analytics', updatedAt: '2026-04-14T10:00:00Z', updatedBy: 'Alice Johnson',
  },
  {
    id: 'ff-010', name: 'Two-Factor Authentication', key: '2fa-auth',
    description: 'Require two-factor authentication for all admin accounts',
    enabled: false, category: 'Security', updatedAt: '2026-04-03T08:00:00Z', updatedBy: 'Frank Wilson',
  },
];
