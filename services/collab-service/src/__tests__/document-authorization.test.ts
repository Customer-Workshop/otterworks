import { DocumentServiceAuthorizer } from '../services/document-authorization';

const mockLogger = {
  error: jest.fn(),
} as never;

describe('DocumentServiceAuthorizer', () => {
  const fetchMock = jest.fn();
  let authorizer: DocumentServiceAuthorizer;

  beforeEach(() => {
    fetchMock.mockReset();
    global.fetch = fetchMock;
    authorizer = new DocumentServiceAuthorizer(
      'http://document-service:8083',
      mockLogger,
    );
  });

  it('allows a document when document-service returns 200', async () => {
    fetchMock.mockResolvedValue({ status: 200 });

    await expect(authorizer.canAccessDocument('doc-1', 'token')).resolves.toBe(true);
  });

  it.each([403, 404, 422])(
    'denies a document when document-service returns %s',
    async (status) => {
      fetchMock.mockResolvedValue({ status });

      await expect(authorizer.canAccessDocument('doc-1', 'token')).resolves.toBe(false);
    },
  );

  it('denies and retries after an unexpected status', async () => {
    fetchMock.mockResolvedValue({ status: 500 });

    await expect(authorizer.canAccessDocument('doc-1', 'token')).resolves.toBe(false);
    await expect(authorizer.canAccessDocument('doc-1', 'token')).resolves.toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('denies network errors without caching them', async () => {
    fetchMock.mockRejectedValue(new Error('network failure'));

    await expect(authorizer.canAccessDocument('doc-1', 'token')).resolves.toBe(false);
    await expect(authorizer.canAccessDocument('doc-1', 'token')).resolves.toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('caches positive results', async () => {
    fetchMock.mockResolvedValue({ status: 200 });

    await expect(authorizer.canAccessDocument('doc-1', 'token')).resolves.toBe(true);
    await expect(authorizer.canAccessDocument('doc-1', 'token')).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('uses separate cache entries for different tokens', async () => {
    fetchMock.mockResolvedValue({ status: 200 });

    await authorizer.canAccessDocument('doc-1', 'token-a');
    await authorizer.canAccessDocument('doc-1', 'token-b');

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('sends the bearer token to document-service', async () => {
    fetchMock.mockResolvedValue({ status: 200 });

    await authorizer.canAccessDocument('doc/1', 'token');

    expect(fetchMock).toHaveBeenCalledWith(
      'http://document-service:8083/api/v1/documents/doc%2F1',
      expect.objectContaining({
        headers: { Authorization: 'Bearer token' },
      }),
    );
  });
});
