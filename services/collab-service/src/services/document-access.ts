import type { Logger } from 'pino';

export type AccessDecision = 'allow' | 'denied' | 'not-found';

export interface AccessPrincipal {
  userId: string;
  roles?: string[];
  /** Raw bearer token, forwarded to document-service so it can authenticate the caller. */
  token?: string;
}

export interface DocumentAccessChecker {
  checkAccess(documentId: string, principal: AccessPrincipal): Promise<AccessDecision>;
}

const PRIVILEGED_ROLES = ['admin', 'service', 'internal'];
const MAX_CACHE_ENTRIES = 1000;

export function hasPrivilegedRole(roles: string[] | undefined): boolean {
  return (roles ?? []).some((role) => PRIVILEGED_ROLES.includes(role.toLowerCase()));
}

/**
 * Resolves whether a caller may access a document. Ownership and sharing live in
 * document-service, so its own owner/share enforcement is used as the oracle:
 * 200 means the caller may access the document, 403 means it exists but is not theirs.
 * Unreachable or unexpected responses fail closed.
 */
export class HttpDocumentAccessService implements DocumentAccessChecker {
  private cache = new Map<string, { decision: AccessDecision; expiresAt: number }>();
  private inFlight = new Map<string, Promise<AccessDecision>>();

  constructor(
    private readonly baseUrl: string,
    private readonly logger: Logger,
    private readonly cacheTtlMs = 30000,
    private readonly timeoutMs = 3000,
  ) {}

  async checkAccess(
    documentId: string,
    principal: AccessPrincipal,
  ): Promise<AccessDecision> {
    if (!documentId || !principal.userId) return 'denied';
    if (hasPrivilegedRole(principal.roles)) return 'allow';

    const key = `${principal.userId}:${documentId}`;
    const cached = this.cache.get(key);
    if (cached && cached.expiresAt > Date.now()) return cached.decision;

    // One request per key: concurrent callers await the same promise, so they resume
    // in the order they arrived instead of in response order, and a burst of events
    // does not stampede document-service.
    const pending = this.inFlight.get(key);
    if (pending) return pending;

    const request = this.fetchDecision(documentId, principal)
      .then((decision) => {
        this.remember(key, decision);
        return decision;
      })
      .finally(() => {
        this.inFlight.delete(key);
      });

    this.inFlight.set(key, request);
    return request;
  }

  private remember(key: string, decision: AccessDecision): void {
    if (this.cache.size >= MAX_CACHE_ENTRIES) {
      const now = Date.now();
      for (const [entryKey, entry] of this.cache) {
        if (entry.expiresAt <= now) this.cache.delete(entryKey);
      }
      if (this.cache.size >= MAX_CACHE_ENTRIES) this.cache.clear();
    }
    this.cache.set(key, { decision, expiresAt: Date.now() + this.cacheTtlMs });
  }

  private async fetchDecision(
    documentId: string,
    principal: AccessPrincipal,
  ): Promise<AccessDecision> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);

    const headers: Record<string, string> = { 'X-User-ID': principal.userId };
    if (principal.token) headers.Authorization = `Bearer ${principal.token}`;

    try {
      const response = await fetch(
        `${this.baseUrl}/api/v1/documents/${encodeURIComponent(documentId)}`,
        { headers, signal: controller.signal },
      );

      if (response.ok) return 'allow';
      if (response.status === 404) return 'not-found';
      if (response.status !== 401 && response.status !== 403) {
        this.logger.error(
          { documentId, status: response.status },
          'document_access_check_unexpected_status',
        );
      }
      return 'denied';
    } catch (err) {
      this.logger.error({ err, documentId }, 'document_access_check_failed');
      return 'denied';
    } finally {
      clearTimeout(timer);
    }
  }
}
