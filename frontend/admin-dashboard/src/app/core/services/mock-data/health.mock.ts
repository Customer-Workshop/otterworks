import { ServiceHealth } from '../../models/system-health.model';

export const MOCK_SERVICE_HEALTH: ServiceHealth[] = [
  {
    name: 'API Gateway', status: 'healthy', uptime: '99.98%', responseTime: 12,
    lastChecked: '2026-04-17T14:00:00Z', version: '2.4.1', port: 8080, language: 'Go 1.22',
    details: 'Request routing, rate limiting, JWT validation',
  },
  {
    name: 'Auth Service', status: 'healthy', uptime: '99.99%', responseTime: 45,
    lastChecked: '2026-04-17T14:00:00Z', version: '3.1.0', port: 8081, language: 'Java 17',
    details: 'Authentication, authorization, user management',
  },
  {
    name: 'File Service', status: 'healthy', uptime: '99.95%', responseTime: 28,
    lastChecked: '2026-04-17T14:00:00Z', version: '1.8.2', port: 8082, language: 'Rust 1.77',
    details: 'File upload/download, S3 integration, versioning',
  },
  {
    name: 'Document Service', status: 'degraded', uptime: '98.50%', responseTime: 320,
    lastChecked: '2026-04-17T14:00:00Z', version: '2.2.0', port: 8083, language: 'Python 3.12',
    details: 'High latency detected - investigating database connection pool',
  },
  {
    name: 'Collaboration Service', status: 'healthy', uptime: '99.90%', responseTime: 8,
    lastChecked: '2026-04-17T14:00:00Z', version: '1.5.3', port: 8084, language: 'Node.js 20',
    details: 'Real-time collaborative editing (CRDT)',
  },
  {
    name: 'Notification Service', status: 'healthy', uptime: '99.97%', responseTime: 55,
    lastChecked: '2026-04-17T14:00:00Z', version: '1.3.1', port: 8086, language: 'Kotlin 1.9',
    details: 'Event-driven notifications (email, in-app, webhook)',
  },
  {
    name: 'Search Service', status: 'down', uptime: '95.20%', responseTime: 0,
    lastChecked: '2026-04-17T14:00:00Z', version: '1.1.0', port: 8087, language: 'Python 3.12',
    details: 'MeiliSearch instance unreachable - restarting pods',
  },
  {
    name: 'Analytics Service', status: 'healthy', uptime: '99.80%', responseTime: 90,
    lastChecked: '2026-04-17T14:00:00Z', version: '1.2.0', port: 8088, language: 'Scala 3.4',
    details: 'Usage analytics, data aggregation',
  },
  {
    name: 'Admin Service', status: 'healthy', uptime: '99.96%', responseTime: 65,
    lastChecked: '2026-04-17T14:00:00Z', version: '1.4.0', port: 8089, language: 'Ruby 3.3',
    details: 'Admin dashboard backend',
  },
  {
    name: 'Audit Service', status: 'healthy', uptime: '99.99%', responseTime: 35,
    lastChecked: '2026-04-17T14:00:00Z', version: '2.0.1', port: 8090, language: 'C# 12',
    details: 'Immutable audit trail, compliance',
  },
];
