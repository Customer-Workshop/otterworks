export interface AuditEvent {
  id: string;
  timestamp: string;
  userId: string;
  userName: string;
  action: 'create' | 'update' | 'delete' | 'share' | 'login' | 'logout' | 'download' | 'upload' | 'suspend' | 'restore';
  resourceType: string;
  resourceName: string;
  details: string;
  ipAddress: string;
  severity: 'info' | 'warning' | 'critical';
}
