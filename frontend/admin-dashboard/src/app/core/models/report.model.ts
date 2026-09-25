export type ReportStatus = 'PENDING' | 'GENERATING' | 'COMPLETED' | 'FAILED';

export type ReportType = 'PDF' | 'CSV' | 'EXCEL';

export type ReportCategory =
  | 'USAGE_ANALYTICS'
  | 'AUDIT_LOG'
  | 'STORAGE_SUMMARY'
  | 'USER_ACTIVITY'
  | 'COLLABORATION_METRICS'
  | 'SYSTEM_HEALTH'
  | 'COMPLIANCE';

export const REPORT_STATUSES: ReportStatus[] = ['PENDING', 'GENERATING', 'COMPLETED', 'FAILED'];

export const REPORT_TYPES: ReportType[] = ['PDF', 'CSV', 'EXCEL'];

export const REPORT_CATEGORIES: ReportCategory[] = [
  'USAGE_ANALYTICS',
  'AUDIT_LOG',
  'STORAGE_SUMMARY',
  'USER_ACTIVITY',
  'COLLABORATION_METRICS',
  'SYSTEM_HEALTH',
  'COMPLIANCE',
];

export interface Report {
  id: number;
  reportName: string;
  category: ReportCategory | string;
  reportType: ReportType | string;
  status: ReportStatus | string;
  requestedBy: string;
  dateFrom?: string;
  dateTo?: string;
  createdAt?: string;
  completedAt?: string;
  fileSizeBytes?: number;
  rowCount?: number;
  downloadUrl?: string;
  errorMessage?: string;
}

export interface CreateReportRequest {
  reportName: string;
  category: ReportCategory;
  reportType: ReportType;
  requestedBy: string;
}
