import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, catchError, map, of, shareReplay } from 'rxjs';
import {
  ArchiveDocument, ArchiveHash, PeerConfig, ReconciliationReport, RunSummary,
} from '../models/migration.model';

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

  getDocument(docId: string, baseUrl?: string): Observable<ArchiveDocument> {
    return this.http.get<ArchiveDocument>(this.documentUrl(docId, baseUrl));
  }

  getDocumentHash(docId: string, baseUrl?: string): Observable<ArchiveHash> {
    return this.http.get<ArchiveHash>(`${this.documentUrl(docId, baseUrl)}/hash`);
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
   * Local deployment: gateway path under /api/v1. Peer deployment: the report contract path
   * /api/archive/documents/{docId} on the peer's API host (also served under /api/v1 there).
   */
  documentUrl(docId: string, baseUrl?: string): string {
    const id = encodeURIComponent(docId);
    return baseUrl ? `${baseUrl}/api/archive/documents/${id}` : `${this.baseUrl}/archive/documents/${id}`;
  }
}
