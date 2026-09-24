import { Injectable } from '@angular/core';
import { HttpClient, HttpContext, HttpContextToken } from '@angular/common/http';
import { Observable, catchError, map, of, shareReplay } from 'rxjs';
import {
  ArchiveDocument, ArchiveHash, PeerConfig, ReconciliationReport, RunSummary,
} from '../models/migration.model';

/** Marks a request aimed at the peer deployment so a 401 there does not log the user out here. */
export const PEER_REQUEST = new HttpContextToken<boolean>(() => false);

/** Migration report + archive read path. Same /api/v1 gateway base as the rest of the dashboard. */
@Injectable({ providedIn: 'root' })
export class MigrationApiService {
  private readonly baseUrl = '/api/v1';
  /** Written by nginx from PEER_APP_URL at container start; absent in local dev. */
  private readonly peerConfigUrl = '/config/peer.json';
  private peerConfig$?: Observable<string>;

  constructor(private http: HttpClient) {}

  listRuns(): Observable<RunSummary[]> {
    return this.http.get<RunSummary[]>(`${this.baseUrl}/reports/reconciliation`);
  }

  getReport(runId: string): Observable<ReconciliationReport> {
    return this.http.get<ReconciliationReport>(`${this.baseUrl}/reports/reconciliation/${encodeURIComponent(runId)}`);
  }

  csvUrl(runId: string): string {
    return `${this.baseUrl}/reports/reconciliation/${encodeURIComponent(runId)}.csv`;
  }

  htmlUrl(runId: string): string {
    return `${this.baseUrl}/reports/reconciliation/${encodeURIComponent(runId)}.html`;
  }

  /** Report body fetched through HttpClient so the bearer header is attached (plain links would be unauthenticated). */
  getReportFile(runId: string, format: 'csv' | 'html'): Observable<Blob> {
    const url = format === 'csv' ? this.csvUrl(runId) : this.htmlUrl(runId);
    return this.http.get(url, { responseType: 'blob' });
  }

  getDocument(docId: string, baseUrl?: string): Observable<ArchiveDocument> {
    return this.http.get<ArchiveDocument>(this.documentUrl(docId, baseUrl), this.options(baseUrl));
  }

  getDocumentHash(docId: string, baseUrl?: string): Observable<ArchiveHash> {
    return this.http.get<ArchiveHash>(`${this.documentUrl(docId, baseUrl)}/hash`, this.options(baseUrl));
  }

  /** Configured peer base URL ('' when PEER_APP_URL is unset). */
  peerAppUrl(): Observable<string> {
    if (!this.peerConfig$) {
      this.peerConfig$ = this.http.get<PeerConfig>(this.peerConfigUrl).pipe(
        map(cfg => (cfg?.peer_app_url || '').replace(/\/+$/, '')),
        catchError(() => of('')),
        shareReplay(1),
      );
    }
    return this.peerConfig$;
  }

  /**
   * The gateway only forwards versioned prefixes (/api/v1/reports -> report-service), so both the
   * local and the peer deployment are read through /api/v1/reports/archive/documents/{docId};
   * baseUrl is the peer's API host (PEER_APP_URL).
   */
  documentUrl(docId: string, baseUrl?: string): string {
    const id = encodeURIComponent(docId);
    return `${baseUrl || ''}${this.baseUrl}/reports/archive/documents/${id}`;
  }

  private options(baseUrl?: string): { context: HttpContext } {
    return { context: new HttpContext().set(PEER_REQUEST, !!baseUrl) };
  }
}
