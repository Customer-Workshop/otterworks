import type { Logger } from 'pino';

const ROOM_PREFIX = 'document-';
const MAX_CACHE_ENTRIES = 10000;

/** Maps a y-websocket room name (`document-<id>`) to the document-service id. */
export function documentIdFromRoomName(roomName: string): string {
  let decoded = roomName;
  try {
    decoded = decodeURIComponent(roomName);
  } catch {
    // malformed escape sequence: fall through with the raw name
  }
  return decoded.startsWith(ROOM_PREFIX) ? decoded.slice(ROOM_PREFIX.length) : decoded;
}

export interface DocumentAccessChecker {
  canAccess(documentId: string, userId: string, token: string): Promise<boolean>;
}

export interface DocumentAccessOptions {
  baseUrl: string;
  timeoutMs?: number;
  cacheTtlMs?: number;
}

interface CacheEntry {
  allowed: boolean;
  expiresAt: number;
}

/**
 * Authorizes a user against a document by asking document-service for it with
 * the caller's own JWT. document-service enforces ownership, so a 2xx means the
 * user may read and edit the document; anything else (403, 404, network error)
 * is treated as denied.
 */
export class DocumentServiceAccessChecker implements DocumentAccessChecker {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly cacheTtlMs: number;
  private readonly cache: Map<string, CacheEntry> = new Map();

  constructor(
    options: DocumentAccessOptions,
    private readonly logger: Logger,
  ) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, '');
    this.timeoutMs = options.timeoutMs ?? 3000;
    this.cacheTtlMs = options.cacheTtlMs ?? 30000;
  }

  async canAccess(documentId: string, userId: string, token: string): Promise<boolean> {
    if (!documentId || !userId || !token) return false;

    const cacheKey = `${userId}:${documentId}`;
    const cached = this.cache.get(cacheKey);
    if (cached && cached.expiresAt > Date.now()) {
      return cached.allowed;
    }

    let response: Response;
    try {
      response = await fetch(
        `${this.baseUrl}/api/v1/documents/${encodeURIComponent(documentId)}`,
        {
          method: 'GET',
          headers: { Authorization: `Bearer ${token}` },
          signal: AbortSignal.timeout(this.timeoutMs),
        },
      );
    } catch (err) {
      this.logger.error({ err, documentId, userId }, 'document_access_check_failed');
      return false;
    }

    response.body?.cancel().catch(() => undefined);

    const allowed = response.ok;
    if (!allowed) {
      this.logger.warn(
        { documentId, userId, status: response.status },
        'document_access_denied',
      );
    }

    this.remember(cacheKey, allowed);
    return allowed;
  }

  private remember(cacheKey: string, allowed: boolean): void {
    if (this.cache.size >= MAX_CACHE_ENTRIES) {
      const now = Date.now();
      for (const [key, entry] of this.cache) {
        if (entry.expiresAt <= now) this.cache.delete(key);
      }
      if (this.cache.size >= MAX_CACHE_ENTRIES) this.cache.clear();
    }
    this.cache.set(cacheKey, { allowed, expiresAt: Date.now() + this.cacheTtlMs });
  }
}
