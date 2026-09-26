import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { OtterWorksApiService } from './otterworks-api.service';
import { ApiError } from '../models/api-error';
import { AuthResponse } from '../models/auth.model';
import { DocumentListResponse, OtterDocument } from '../models/document.model';
import { FileListResponse } from '../models/file.model';

describe('OtterWorksApiService', () => {
  let service: OtterWorksApiService;
  let httpMock: HttpTestingController;

  const authResponse: AuthResponse = {
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    tokenType: 'Bearer',
    expiresIn: 3600,
    user: { id: 'u1', email: 'otter@otterworks.io', displayName: 'Otter' },
  };

  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [HttpClientTestingModule] });
    service = TestBed.inject(OtterWorksApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('posts camelCase credentials to /auth/register', () => {
    let result: AuthResponse | undefined;
    service.register('Otter', 'otter@otterworks.io', 'password123').subscribe(r => (result = r));

    const req = httpMock.expectOne('/api/v1/auth/register');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({
      displayName: 'Otter',
      email: 'otter@otterworks.io',
      password: 'password123',
    });
    req.flush(authResponse);

    expect(result).toEqual(authResponse);
  });

  it('posts credentials to /auth/login', () => {
    service.login('otter@otterworks.io', 'password123').subscribe();

    const req = httpMock.expectOne('/api/v1/auth/login');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ email: 'otter@otterworks.io', password: 'password123' });
    req.flush(authResponse);
  });

  it('requests documents with page and size defaults', () => {
    const page: DocumentListResponse = { items: [], total: 0, page: 1, size: 50, pages: 0 };
    let result: DocumentListResponse | undefined;
    service.getDocuments().subscribe(r => (result = r));

    const req = httpMock.expectOne('/api/v1/documents?page=1&size=50');
    expect(req.request.method).toBe('GET');
    req.flush(page);

    expect(result).toEqual(page);
  });

  it('creates a document from a title', () => {
    const created = { id: 'd1', title: 'Notes' } as OtterDocument;
    let result: OtterDocument | undefined;
    service.createDocument('Notes').subscribe(r => (result = r));

    const req = httpMock.expectOne('/api/v1/documents');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ title: 'Notes' });
    req.flush(created);

    expect(result).toEqual(created);
  });

  it('requests files with snake_case paging params', () => {
    const page: FileListResponse = { files: [], total: 0, page: 2, page_size: 10 };
    service.getFiles(2, 10).subscribe(r => expect(r).toEqual(page));

    const req = httpMock.expectOne('/api/v1/files?page=2&page_size=10');
    expect(req.request.method).toBe('GET');
    req.flush(page);
  });

  it('prefers message, then error, then detail from a JSON error body', () => {
    const cases: Array<{ body: Record<string, string>; expected: string }> = [
      { body: { message: 'from message', error: 'from error', detail: 'from detail' }, expected: 'from message' },
      { body: { error: 'from error', detail: 'from detail' }, expected: 'from error' },
      { body: { detail: 'from detail' }, expected: 'from detail' },
    ];

    for (const testCase of cases) {
      let error: ApiError | undefined;
      service.login('a@b.io', 'pw').subscribe({ error: (e: ApiError) => (error = e) });
      httpMock
        .expectOne('/api/v1/auth/login')
        .flush(testCase.body, { status: 400, statusText: 'Bad Request' });

      expect(error instanceof ApiError).toBeTrue();
      expect(error?.message).toBe(testCase.expected);
      expect(error?.status).toBe(400);
    }
  });

  it('falls back to the raw body for a non-JSON error', () => {
    let error: ApiError | undefined;
    service.getDocuments().subscribe({ error: (e: ApiError) => (error = e) });

    httpMock
      .expectOne('/api/v1/documents?page=1&size=50')
      .flush('upstream exploded', { status: 502, statusText: 'Bad Gateway' });

    expect(error?.message).toBe('upstream exploded');
    expect(error?.status).toBe(502);
  });

  it('falls back to a status message for an empty error body', () => {
    let error: ApiError | undefined;
    service.getDocuments().subscribe({ error: (e: ApiError) => (error = e) });

    httpMock
      .expectOne('/api/v1/documents?page=1&size=50')
      .flush(null, { status: 503, statusText: 'Service Unavailable' });

    expect(error?.message).toBe('Request failed with status 503.');
  });

  it('reports an unreachable backend for a transport failure', () => {
    let error: ApiError | undefined;
    service.getFiles().subscribe({ error: (e: ApiError) => (error = e) });

    httpMock.expectOne('/api/v1/files?page=1&page_size=50').error(new ProgressEvent('error'));

    expect(error?.status).toBe(0);
    expect(error?.message).toContain('Could not reach the OtterWorks backend');
  });
});
