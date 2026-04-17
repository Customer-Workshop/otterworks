export interface ServiceHealth {
  name: string;
  status: 'healthy' | 'degraded' | 'down';
  uptime: string;
  responseTime: number;
  lastChecked: string;
  version: string;
  port: number;
  language: string;
  details?: string;
}
