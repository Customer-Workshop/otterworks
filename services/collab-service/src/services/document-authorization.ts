import { createHash } from 'crypto';
import type { Logger } from 'pino';

export interface DocumentAuthorizer {
  canAccessDocument(documentId: string, token: string | undefined): Promise<boolean>;
}

interface CacheEntry {
  allowed: boolean;
  expiresAt: number;
}

export class DocumentServiceAuthorizer implements DocumentAuthorizer {
  private readonly cache = new Map<string, CacheEntry>();

  constructor(
    private readonly baseUrl: string,
    private readonly logger: Logger,
    private readonly cacheTtlMs = 30000,
    private readonly requestTimeoutMs = 3000,
    private readonly maxCacheEntries = 5000,
  ) {}

  async canAccessDocument(
    documentId: string,
    token: string | undefined,
  ): Promise<boolean> {
    if (!token || typeof documentId !== 'string' || documentId.length === 0) {
      return false;
    }

    const tokenHash = createHash('sha256').update(token).digest('hex');
    const cacheKey = `${tokenHash}:${documentId}`;
    const cached = this.cache.get(cacheKey);
    if (cached) {
      if (cached.expiresAt > Date.now()) {
        return cached.allowed;
      }
      this.cache.delete(cacheKey);
    }

    try {
      const response = await fetch(
        `${this.baseUrl}/api/v1/documents/${encodeURIComponent(documentId)}`,
        {
          headers: { Authorization: `Bearer ${token}` },
          signal: AbortSignal.timeout(this.requestTimeoutMs),
        },
      );

      if (response.status === 200) {
        this.cacheResult(cacheKey, true);
        return true;
      }

      if ([401, 403, 404, 422].includes(response.status)) {
        this.cacheResult(cacheKey, false);
        return false;
      }

      this.logger.error(
        { documentId, status: response.status },
        'document_authorization_unexpected_status',
      );
      return false;
    } catch (err) {
      this.logger.error({ err, documentId }, 'document_authorization_failed');
      return false;
    }
  }

  private cacheResult(cacheKey: string, allowed: boolean): void {
    if (this.cache.size >= this.maxCacheEntries) {
      const oldestKey = this.cache.keys().next().value;
      if (oldestKey !== undefined) {
        this.cache.delete(oldestKey);
      }
    }

    this.cache.set(cacheKey, {
      allowed,
      expiresAt: Date.now() + this.cacheTtlMs,
    });
  }
}
