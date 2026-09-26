import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, catchError, throwError } from 'rxjs';
import { ApiError } from '../models/api-error';
import { AuthResponse, LoginRequest, RegisterRequest } from '../models/auth.model';
import { CreateDocumentRequest, DocumentListResponse, OtterDocument } from '../models/document.model';
import { FileListResponse } from '../models/file.model';

/**
 * REST client for the OtterWorks API gateway, a port of Services/OtterWorksApiClient.cs.
 * Auth payloads are camelCase and document/file payloads are snake_case; the models carry
 * the wire field names verbatim so one client handles both shapes.
 */
@Injectable({ providedIn: 'root' })
export class OtterWorksApiService {
  static readonly BASE_URL = '/api/v1';

  private readonly http = inject(HttpClient);

  register(displayName: string, email: string, password: string): Observable<AuthResponse> {
    const body: RegisterRequest = { displayName, email, password };
    return this.request(this.http.post<AuthResponse>(this.url('/auth/register'), body));
  }

  login(email: string, password: string): Observable<AuthResponse> {
    const body: LoginRequest = { email, password };
    return this.request(this.http.post<AuthResponse>(this.url('/auth/login'), body));
  }

  getDocuments(page = 1, size = 50): Observable<DocumentListResponse> {
    return this.request(
      this.http.get<DocumentListResponse>(this.url(`/documents?page=${page}&size=${size}`))
    );
  }

  createDocument(title: string): Observable<OtterDocument> {
    const body: CreateDocumentRequest = { title };
    return this.request(this.http.post<OtterDocument>(this.url('/documents'), body));
  }

  getFiles(page = 1, pageSize = 50): Observable<FileListResponse> {
    return this.request(
      this.http.get<FileListResponse>(this.url(`/files?page=${page}&page_size=${pageSize}`))
    );
  }

  private url(path: string): string {
    return `${OtterWorksApiService.BASE_URL}/${path.replace(/^\/+/, '')}`;
  }

  private request<T>(source: Observable<T>): Observable<T> {
    return source.pipe(
      catchError((error: unknown) => throwError(() => this.toApiError(error)))
    );
  }

  private toApiError(error: unknown): ApiError {
    if (!(error instanceof HttpErrorResponse)) {
      return error instanceof ApiError ? error : new ApiError(0, String(error));
    }

    if (error.status === 0) {
      return new ApiError(
        0,
        'Could not reach the OtterWorks backend. Verify it is running and that the ' +
          'API base URL is correct.'
      );
    }

    return new ApiError(error.status, OtterWorksApiService.extractError(error));
  }

  /**
   * Mirrors OtterWorksApiClient.ExtractError: prefer `message`, then `error`, then `detail`
   * from a JSON error body; otherwise the raw body; otherwise a status-based message.
   */
  private static extractError(response: HttpErrorResponse): string {
    const body: unknown = response.error;

    let parsed: unknown = body;
    if (typeof body === 'string') {
      const text = body.trim();
      if (text.length > 0) {
        try {
          parsed = JSON.parse(text) as unknown;
        } catch {
          return body;
        }
      } else {
        parsed = null;
      }
    }

    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      const record = parsed as Record<string, unknown>;
      for (const key of ['message', 'error', 'detail']) {
        const value = record[key];
        if (value !== undefined && value !== null) {
          return typeof value === 'string' ? value : JSON.stringify(value);
        }
      }
      return JSON.stringify(parsed);
    }

    if (typeof parsed === 'string' && parsed.trim().length > 0) {
      return parsed;
    }

    return `Request failed with status ${response.status}.`;
  }
}
