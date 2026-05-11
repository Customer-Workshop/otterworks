import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of, delay, Subject, map } from 'rxjs';
import { User, UserActivity } from '../models/user.model';
import { AuditEvent } from '../models/audit.model';
import { FeatureFlag } from '../models/feature-flag.model';
import { Announcement } from '../models/announcement.model';
import { ServiceHealth } from '../models/system-health.model';
import { DashboardStats, AnalyticsReport } from '../models/analytics.model';
import { MOCK_USERS, MOCK_USER_ACTIVITIES } from './mock-data/users.mock';
import { MOCK_AUDIT_EVENTS } from './mock-data/audit.mock';
import { MOCK_FEATURE_FLAGS } from './mock-data/features.mock';
import { MOCK_ANNOUNCEMENTS } from './mock-data/announcements.mock';
import { MOCK_SERVICE_HEALTH } from './mock-data/health.mock';
import { MOCK_DASHBOARD_STATS, MOCK_ANALYTICS_REPORT, mockStorage, formatStorageUsed } from './mock-data/analytics.mock';
import { Incident } from '../models/incident.model';
import { MOCK_INCIDENTS } from './mock-data/incidents.mock';

@Injectable({ providedIn: 'root' })
export class AdminApiService {
  private readonly baseUrl = '/api/v1';

  readonly statsChanged$ = new Subject<void>();

  constructor(private http: HttpClient) {}

  // Dashboard
  getDashboardStats(): Observable<DashboardStats> {
    // return this.http.get<DashboardStats>(`${this.baseUrl}/admin/dashboard/stats`);
    return of(MOCK_DASHBOARD_STATS).pipe(delay(500));
  }

  // Users
  getUsers(): Observable<User[]> {
    // return this.http.get<User[]>(`${this.baseUrl}/admin/users`);
    return of(MOCK_USERS).pipe(delay(400));
  }

  getUser(id: string): Observable<User | undefined> {
    // return this.http.get<User>(`${this.baseUrl}/admin/users/${id}`);
    return of(MOCK_USERS.find(u => u.id === id)).pipe(delay(300));
  }

  getUserActivity(userId: string): Observable<UserActivity[]> {
    // return this.http.get<UserActivity[]>(`${this.baseUrl}/admin/users/${userId}/activity`);
    return of(MOCK_USER_ACTIVITIES.filter(a => a.userId === userId)).pipe(delay(300));
  }

  suspendUser(userId: string): Observable<User> {
    // return this.http.post<User>(`${this.baseUrl}/admin/users/${userId}/suspend`, {});
    const user = MOCK_USERS.find(u => u.id === userId);
    if (user) {
      user.status = 'suspended';
    }
    return of(user as User).pipe(delay(500));
  }

  restoreUser(userId: string): Observable<User> {
    // return this.http.post<User>(`${this.baseUrl}/admin/users/${userId}/restore`, {});
    const user = MOCK_USERS.find(u => u.id === userId);
    if (user) {
      user.status = 'active';
    }
    return of(user as User).pipe(delay(500));
  }

  deleteUser(userId: string): Observable<void> {
    // return this.http.delete<void>(`${this.baseUrl}/admin/users/${userId}`);
    const index = MOCK_USERS.findIndex(u => u.id === userId);
    if (index !== -1) {
      MOCK_USERS.splice(index, 1);
      MOCK_DASHBOARD_STATS.totalUsers = Math.max(0, MOCK_DASHBOARD_STATS.totalUsers - 1);
      this.statsChanged$.next();
    }
    return of(undefined).pipe(delay(500));
  }

  deleteDocument(docId: string, fileSizeBytes = 275 * 1024 * 1024): Observable<void> {
    // return this.http.delete<void>(`${this.baseUrl}/admin/documents/${docId}`);
    MOCK_DASHBOARD_STATS.activeDocuments = Math.max(0, MOCK_DASHBOARD_STATS.activeDocuments - 1);
    mockStorage.usedBytes = Math.max(0, mockStorage.usedBytes - fileSizeBytes);
    MOCK_DASHBOARD_STATS.storageUsed = formatStorageUsed(mockStorage.usedBytes);
    this.statsChanged$.next();
    return of(undefined).pipe(delay(400));
  }

  // Audit
  getAuditEvents(): Observable<AuditEvent[]> {
    // return this.http.get<AuditEvent[]>(`${this.baseUrl}/audit/events`);
    return of(MOCK_AUDIT_EVENTS).pipe(delay(400));
  }

  // Feature Flags
  getFeatureFlags(): Observable<FeatureFlag[]> {
    // return this.http.get<FeatureFlag[]>(`${this.baseUrl}/admin/features`);
    return of(MOCK_FEATURE_FLAGS).pipe(delay(300));
  }

  toggleFeatureFlag(flagId: string, enabled: boolean): Observable<FeatureFlag> {
    // return this.http.patch<FeatureFlag>(`${this.baseUrl}/admin/features/${flagId}`, { enabled });
    const flag = MOCK_FEATURE_FLAGS.find(f => f.id === flagId);
    if (flag) {
      flag.enabled = enabled;
    }
    return of(flag as FeatureFlag).pipe(delay(400));
  }

  // System Health
  getSystemHealth(): Observable<ServiceHealth[]> {
    // return this.http.get<ServiceHealth[]>(`${this.baseUrl}/admin/health`);
    return of(MOCK_SERVICE_HEALTH).pipe(delay(600));
  }

  // Announcements
  getAnnouncements(): Observable<Announcement[]> {
    // return this.http.get<Announcement[]>(`${this.baseUrl}/admin/announcements`);
    return of([...MOCK_ANNOUNCEMENTS]).pipe(delay(400));
  }

  createAnnouncement(announcement: Partial<Announcement>): Observable<Announcement> {
    // return this.http.post<Announcement>(`${this.baseUrl}/admin/announcements`, announcement);
    const newAnnouncement: Announcement = {
      id: 'ann-' + Date.now(),
      title: announcement.title || '',
      content: announcement.content || '',
      priority: announcement.priority || 'medium',
      status: 'draft',
      createdAt: new Date().toISOString(),
      createdBy: 'Admin User',
      targetAudience: announcement.targetAudience || 'all',
    };
    MOCK_ANNOUNCEMENTS.unshift(newAnnouncement);
    return of(newAnnouncement).pipe(delay(500));
  }

  publishAnnouncement(id: string): Observable<Announcement> {
    const ann = MOCK_ANNOUNCEMENTS.find(a => a.id === id);
    if (ann) {
      ann.status = 'published';
      ann.publishedAt = new Date().toISOString();
    }
    return of(ann as Announcement).pipe(delay(400));
  }

  deleteAnnouncement(id: string): Observable<void> {
    // return this.http.delete<void>(`${this.baseUrl}/admin/announcements/${id}`);
    const index = MOCK_ANNOUNCEMENTS.findIndex(a => a.id === id);
    if (index !== -1) {
      MOCK_ANNOUNCEMENTS.splice(index, 1);
    }
    return of(undefined).pipe(delay(400));
  }

  // Storage Quotas
  updateStorageQuota(userId: string, quota: number): Observable<User> {
    // return this.http.patch<User>(`${this.baseUrl}/admin/users/${userId}/quota`, { quota });
    const user = MOCK_USERS.find(u => u.id === userId);
    if (user) {
      user.storageQuota = quota;
    }
    return of(user as User).pipe(delay(400));
  }

  // Analytics
  getAnalyticsReport(): Observable<AnalyticsReport> {
    // return this.http.get<AnalyticsReport>(`${this.baseUrl}/analytics/report`);
    return of(MOCK_ANALYTICS_REPORT).pipe(delay(600));
  }

  // Incidents
  getIncidents(): Observable<Incident[]> {
    // return this.http.get<any>(`${this.baseUrl}/admin/incidents`).pipe(map(res => res.incidents));
    return of([...MOCK_INCIDENTS]).pipe(delay(400));
  }

  getIncident(id: string): Observable<Incident | undefined> {
    // return this.http.get<Incident>(`${this.baseUrl}/admin/incidents/${id}`);
    return of(MOCK_INCIDENTS.find(i => i.id === id)).pipe(delay(300));
  }

  createIncident(incident: Partial<Incident>): Observable<Incident> {
    return this.http.post<any>(`${this.baseUrl}/admin/incidents`, { incident }).pipe(
      map(res => this.mapIncident(res.incident || res)),
    );
  }

  private mapIncident(raw: any): Incident {
    return {
      id: raw.id,
      title: raw.title,
      description: raw.description,
      severity: raw.severity,
      status: raw.status,
      affectedService: raw.affected_service,
      devinSessionId: raw.devin_session_id,
      devinSessionUrl: raw.devin_session_url,
      devinSessionStatus: raw.devin_session_status,
      reporterId: raw.reporter_id,
      resolvedAt: raw.resolved_at,
      active: raw.active,
      createdAt: raw.created_at,
      updatedAt: raw.updated_at,
    };
  }
}
