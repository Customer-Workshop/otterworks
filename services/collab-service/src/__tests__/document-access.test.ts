import {
  DocumentServiceAccessChecker,
  documentIdFromRoomName,
} from '../services/document-access';

const mockLogger = {
  info: jest.fn(),
  warn: jest.fn(),
  error: jest.fn(),
  debug: jest.fn(),
  fatal: jest.fn(),
  trace: jest.fn(),
  child: jest.fn().mockReturnThis(),
  level: 'info',
} as never;

function mockResponse(status: number): Response {
  return { ok: status >= 200 && status < 300, status, body: null } as unknown as Response;
}

describe('documentIdFromRoomName', () => {
  it('strips the y-websocket document- prefix', () => {
    expect(documentIdFromRoomName('document-abc-123')).toBe('abc-123');
  });

  it('decodes URL-encoded room names', () => {
    expect(documentIdFromRoomName('document-a%20b')).toBe('a b');
  });

  it('returns unprefixed names unchanged', () => {
    expect(documentIdFromRoomName('abc-123')).toBe('abc-123');
  });
});

describe('DocumentServiceAccessChecker', () => {
  const fetchMock = jest.fn<Promise<Response>, Parameters<typeof fetch>>();
  let checker: DocumentServiceAccessChecker;

  beforeEach(() => {
    fetchMock.mockReset();
    global.fetch = fetchMock as unknown as typeof fetch;
    checker = new DocumentServiceAccessChecker(
      { baseUrl: 'http://document-service:8083/', cacheTtlMs: 60000 },
      mockLogger,
    );
  });

  it('asks document-service for the document with the caller token', async () => {
    fetchMock.mockResolvedValue(mockResponse(200));

    await expect(checker.canAccess('doc-1', 'user-1', 'jwt-token')).resolves.toBe(true);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://document-service:8083/api/v1/documents/doc-1');
    expect((init?.headers as Record<string, string>).Authorization).toBe(
      'Bearer jwt-token',
    );
  });

  it('encodes the document id in the request path', async () => {
    fetchMock.mockResolvedValue(mockResponse(200));

    await checker.canAccess('../admin?x=1', 'user-1', 'jwt-token');

    expect(fetchMock.mock.calls[0][0]).toBe(
      'http://document-service:8083/api/v1/documents/..%2Fadmin%3Fx%3D1',
    );
  });

  it.each([403, 404, 401, 500])(
    'denies access when document-service returns %i',
    async (status) => {
      fetchMock.mockResolvedValue(mockResponse(status));

      await expect(checker.canAccess('doc-1', 'user-1', 'jwt-token')).resolves.toBe(
        false,
      );
    },
  );

  it('fails closed when document-service is unreachable', async () => {
    fetchMock.mockRejectedValue(new Error('ECONNREFUSED'));

    await expect(checker.canAccess('doc-1', 'user-1', 'jwt-token')).resolves.toBe(false);
  });

  it('denies access without a document id, user id, or token', async () => {
    await expect(checker.canAccess('', 'user-1', 'jwt-token')).resolves.toBe(false);
    await expect(checker.canAccess('doc-1', '', 'jwt-token')).resolves.toBe(false);
    await expect(checker.canAccess('doc-1', 'user-1', '')).resolves.toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('caches decisions per user and document', async () => {
    fetchMock
      .mockResolvedValueOnce(mockResponse(200))
      .mockResolvedValueOnce(mockResponse(403));

    await expect(checker.canAccess('doc-1', 'user-1', 'jwt-token')).resolves.toBe(true);
    await expect(checker.canAccess('doc-1', 'user-1', 'jwt-token')).resolves.toBe(true);
    await expect(checker.canAccess('doc-1', 'user-2', 'other-token')).resolves.toBe(
      false,
    );

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('re-checks after the cache entry expires', async () => {
    checker = new DocumentServiceAccessChecker(
      { baseUrl: 'http://document-service:8083', cacheTtlMs: 0 },
      mockLogger,
    );
    fetchMock
      .mockResolvedValueOnce(mockResponse(200))
      .mockResolvedValueOnce(mockResponse(403));

    await expect(checker.canAccess('doc-1', 'user-1', 'jwt-token')).resolves.toBe(true);
    await expect(checker.canAccess('doc-1', 'user-1', 'jwt-token')).resolves.toBe(false);
  });
});
