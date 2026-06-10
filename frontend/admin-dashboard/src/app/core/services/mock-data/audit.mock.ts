import { AuditEvent } from '../../models/audit.model';

const MOCK_IP_ALICE = '192.168.1.10';
const MOCK_IP_BOB = '10.0.0.25';
const MOCK_IP_CAROL = '10.0.0.42';
const MOCK_IP_EMILY = '172.16.0.5';
const MOCK_IP_FRANK = '192.168.1.15';
const MOCK_IP_HENRY = '10.0.0.80';
const MOCK_IP_IRENE = '172.16.0.12';
const MOCK_IP_JAMES = '10.0.1.100';
const MOCK_IP_UNKNOWN = '203.0.113.50';

export const MOCK_AUDIT_EVENTS: AuditEvent[] = [
  {
    id: 'aud-001', timestamp: '2026-04-17T12:30:00Z', userId: 'usr-006', userName: 'Frank Wilson',
    action: 'delete', resourceType: 'File', resourceName: 'old-backup.zip',
    details: 'Permanently deleted file from trash', ipAddress: MOCK_IP_FRANK, severity: 'warning',
  },
  {
    id: 'aud-002', timestamp: '2026-04-17T11:00:00Z', userId: 'usr-009', userName: 'Irene Garcia',
    action: 'upload', resourceType: 'File', resourceName: 'Blog-Post-Draft.docx',
    details: 'Uploaded new file (2.4 MB)', ipAddress: MOCK_IP_IRENE, severity: 'info',
  },
  {
    id: 'aud-003', timestamp: '2026-04-17T10:30:00Z', userId: 'usr-001', userName: 'Alice Johnson',
    action: 'upload', resourceType: 'File', resourceName: 'Q4-Report.docx',
    details: 'Uploaded new file (5.1 MB)', ipAddress: MOCK_IP_ALICE, severity: 'info',
  },
  {
    id: 'aud-004', timestamp: '2026-04-17T09:15:00Z', userId: 'usr-001', userName: 'Alice Johnson',
    action: 'share', resourceType: 'Document', resourceName: 'Budget-2026.xlsx',
    details: 'Shared with bob.martinez@otterworks.io (editor)', ipAddress: MOCK_IP_ALICE, severity: 'info',
  },
  {
    id: 'aud-005', timestamp: '2026-04-17T09:00:00Z', userId: 'usr-002', userName: 'Bob Martinez',
    action: 'create', resourceType: 'Folder', resourceName: 'Marketing-Assets',
    details: 'Created new folder', ipAddress: MOCK_IP_BOB, severity: 'info',
  },
  {
    id: 'aud-006', timestamp: '2026-04-17T08:20:00Z', userId: 'usr-005', userName: 'Emily Davis',
    action: 'share', resourceType: 'Document', resourceName: 'Product-Roadmap.docx',
    details: 'Shared with engineering team (viewer)', ipAddress: MOCK_IP_EMILY, severity: 'info',
  },
  {
    id: 'aud-007', timestamp: '2026-04-17T08:00:00Z', userId: 'usr-001', userName: 'Alice Johnson',
    action: 'login', resourceType: 'System', resourceName: 'Admin Portal',
    details: 'Successful login from known IP', ipAddress: MOCK_IP_ALICE, severity: 'info',
  },
  {
    id: 'aud-008', timestamp: '2026-04-16T22:15:00Z', userId: 'usr-004', userName: 'David Kim',
    action: 'suspend', resourceType: 'User', resourceName: 'david.kim@otterworks.io',
    details: 'Account suspended by admin due to policy violation', ipAddress: MOCK_IP_FRANK, severity: 'critical',
  },
  {
    id: 'aud-009', timestamp: '2026-04-16T16:45:00Z', userId: 'usr-003', userName: 'Carol Chen',
    action: 'download', resourceType: 'File', resourceName: 'Design-System.fig',
    details: 'Downloaded file (45.2 MB)', ipAddress: MOCK_IP_CAROL, severity: 'info',
  },
  {
    id: 'aud-010', timestamp: '2026-04-16T16:00:00Z', userId: 'usr-001', userName: 'Alice Johnson',
    action: 'update', resourceType: 'Document', resourceName: 'Team-Notes.docx',
    details: 'Document edited (version 14)', ipAddress: MOCK_IP_ALICE, severity: 'info',
  },
  {
    id: 'aud-011', timestamp: '2026-04-16T14:30:00Z', userId: 'usr-002', userName: 'Bob Martinez',
    action: 'upload', resourceType: 'File', resourceName: 'Campaign-Brief.pdf',
    details: 'Uploaded new file (1.8 MB)', ipAddress: MOCK_IP_BOB, severity: 'info',
  },
  {
    id: 'aud-012', timestamp: '2026-04-16T10:00:00Z', userId: 'usr-006', userName: 'Frank Wilson',
    action: 'login', resourceType: 'System', resourceName: 'Admin Portal',
    details: 'Failed login attempt (wrong password)', ipAddress: MOCK_IP_UNKNOWN, severity: 'warning',
  },
  {
    id: 'aud-013', timestamp: '2026-04-15T15:30:00Z', userId: 'usr-008', userName: 'Henry Patel',
    action: 'create', resourceType: 'Document', resourceName: 'API-Docs-v2.md',
    details: 'Created new document', ipAddress: MOCK_IP_HENRY, severity: 'info',
  },
  {
    id: 'aud-014', timestamp: '2026-04-15T12:00:00Z', userId: 'usr-006', userName: 'Frank Wilson',
    action: 'update', resourceType: 'System', resourceName: 'Feature Flag: real-time-collab',
    details: 'Feature flag enabled', ipAddress: MOCK_IP_FRANK, severity: 'warning',
  },
  {
    id: 'aud-015', timestamp: '2026-04-15T09:00:00Z', userId: 'usr-010', userName: 'James Thompson',
    action: 'login', resourceType: 'System', resourceName: 'Web App',
    details: 'Successful login', ipAddress: MOCK_IP_JAMES, severity: 'info',
  },
];
