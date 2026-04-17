import { Announcement } from '../../models/announcement.model';

export const MOCK_ANNOUNCEMENTS: Announcement[] = [
  {
    id: 'ann-001', title: 'Scheduled Maintenance Window',
    content: 'OtterWorks will undergo scheduled maintenance on April 20, 2026 from 2:00 AM to 6:00 AM UTC. During this time, file uploads and real-time collaboration may be temporarily unavailable.',
    priority: 'high', status: 'published',
    createdAt: '2026-04-16T10:00:00Z', publishedAt: '2026-04-16T10:30:00Z', expiresAt: '2026-04-21T00:00:00Z',
    createdBy: 'Frank Wilson', targetAudience: 'all',
  },
  {
    id: 'ann-002', title: 'New Feature: AI Document Summaries (Beta)',
    content: 'We are rolling out AI-powered document summaries to select users. If you would like to participate in the beta program, please contact your administrator.',
    priority: 'medium', status: 'draft',
    createdAt: '2026-04-15T14:00:00Z',
    createdBy: 'Alice Johnson', targetAudience: 'editors',
  },
  {
    id: 'ann-003', title: 'Storage Quota Increase for Enterprise Users',
    content: 'Effective immediately, all enterprise plan users will receive an increased storage quota from 5 GB to 10 GB. No action is required on your part.',
    priority: 'medium', status: 'published',
    createdAt: '2026-04-10T09:00:00Z', publishedAt: '2026-04-10T09:30:00Z',
    createdBy: 'Alice Johnson', targetAudience: 'all',
  },
  {
    id: 'ann-004', title: 'Security Update: Password Policy Change',
    content: 'Starting May 1, 2026, all accounts will be required to use passwords with a minimum of 12 characters including uppercase, lowercase, numbers, and special characters.',
    priority: 'critical', status: 'published',
    createdAt: '2026-04-08T08:00:00Z', publishedAt: '2026-04-08T08:30:00Z',
    createdBy: 'Frank Wilson', targetAudience: 'all',
  },
  {
    id: 'ann-005', title: 'Welcome to OtterWorks 2.0',
    content: 'We are excited to announce the launch of OtterWorks 2.0, featuring real-time collaboration, improved search, and a brand new admin dashboard.',
    priority: 'low', status: 'archived',
    createdAt: '2026-03-01T12:00:00Z', publishedAt: '2026-03-01T12:30:00Z',
    createdBy: 'Alice Johnson', targetAudience: 'all',
  },
];
