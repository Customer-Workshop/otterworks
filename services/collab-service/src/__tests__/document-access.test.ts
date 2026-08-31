import pino from 'pino';
import {
  authorizeDocumentAccess,
  extractDocumentName,
} from '../services/document-access';

const logger = pino({ level: 'silent' });
const fetchMock = jest.spyOn(global, 'fetch');

describe('extractDocumentName', () => {
  it.each([
    ['/doc-1?token=abc', 'doc-1'],
    ['/doc%20x', 'doc x'],
    ['/', null],
    ['', null],
  ])('extracts the document name from %s', (requestUrl, expected) => {
    expect(extractDocumentName(requestUrl)).toBe(expected);
  });
});

describe('authorizeDocumentAccess', () => {
  const options = {
    documentServiceUrl: 'http://document-service:8083',
    timeoutMs: 5000,
  };

  beforeEach(() => {
    fetchMock.mockReset();
  });

  it('returns true when document-service responds with 200', async () => {
    fetchMock.mockResolvedValue({ ok: true } as Response);

    await expect(
      authorizeDocumentAccess('doc-1', 'token-123', options, logger),
    ).resolves.toBe(true);

    expect(fetchMock).toHaveBeenCalledWith(
      'http://document-service:8083/api/v1/documents/doc-1',
      expect.objectContaining({
        headers: { Authorization: 'Bearer token-123' },
        signal: expect.any(AbortSignal),
      }),
    );
  });

  it.each([403, 404])(
    'returns false when document-service responds with %s',
    async (status) => {
      fetchMock.mockResolvedValue({ ok: false, status } as Response);

      await expect(
        authorizeDocumentAccess('doc-1', 'token-123', options, logger),
      ).resolves.toBe(false);
    },
  );

  it('returns false when document-service request fails', async () => {
    fetchMock.mockRejectedValue(new Error('network error'));

    await expect(
      authorizeDocumentAccess('doc-1', 'token-123', options, logger),
    ).resolves.toBe(false);
  });
});
