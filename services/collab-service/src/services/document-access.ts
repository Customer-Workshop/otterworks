import type { Logger } from 'pino';

export function extractDocumentName(requestUrl: string): string | null {
  const path = requestUrl.startsWith('/') ? requestUrl.slice(1) : requestUrl;
  const encodedDocumentName = path.split('?')[0];

  if (!encodedDocumentName) {
    return null;
  }

  try {
    const documentName = decodeURIComponent(encodedDocumentName);
    return documentName || null;
  } catch {
    return null;
  }
}

export async function authorizeDocumentAccess(
  documentName: string,
  token: string,
  options: { documentServiceUrl: string; timeoutMs: number },
  logger: Logger,
): Promise<boolean> {
  try {
    const response = await fetch(
      `${options.documentServiceUrl}/api/v1/documents/${encodeURIComponent(documentName)}`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
        },
        signal: AbortSignal.timeout(options.timeoutMs),
      },
    );

    return response.ok;
  } catch (err) {
    logger.warn({ err, documentName }, 'document_access_authorization_failed');
    return false;
  }
}
