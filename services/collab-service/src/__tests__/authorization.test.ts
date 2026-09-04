import express from 'express';
import { createServer, type Server } from 'http';
import { Server as SocketIOServer } from 'socket.io';
import { io as clientIO, Socket as ClientSocket } from 'socket.io-client';
import jwt from 'jsonwebtoken';
import { AwarenessService } from '../services/awareness';
import { PresenceHandler } from '../handlers/presence';
import { DocumentStore } from '../services/document-store';
import { MetricsCollector } from '../metrics';
import { CollaborationManager } from '../handlers/collaboration';
import { createAuthMiddleware } from '../middleware/auth';
import { createCollabRouter } from '../routes/collab';
import {
  HttpDocumentAccessService,
  type AccessDecision,
  type DocumentAccessChecker,
} from '../services/document-access';
import type { RedisAdapter } from '../services/redis-adapter';

const JWT_SECRET = 'test-secret-key-for-unit-tests';
const OWNER = 'owner-user';
const OTHER = 'other-user';
const SHARED = 'shared-user';
const OWNED_DOC = 'doc-owned';
const MISSING_DOC = 'doc-missing';

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

/** Stands in for document-service: OWNER owns OWNED_DOC, SHARED has been granted access. */
const documentAccess: DocumentAccessChecker = {
  checkAccess: jest.fn(
    async (
      documentId: string,
      principal: { userId: string },
    ): Promise<AccessDecision> => {
      if (documentId === MISSING_DOC) return 'not-found';
      if (
        documentId === OWNED_DOC &&
        (principal.userId === OWNER || principal.userId === SHARED)
      ) {
        return 'allow';
      }
      return 'denied';
    },
  ),
};

describe('HTTP authorization on /api/v1/collab', () => {
  let httpServer: Server;
  let baseUrl: string;
  let awareness: AwarenessService;

  beforeAll((done) => {
    awareness = new AwarenessService(mockLogger);
    const presenceHandler = new PresenceHandler(awareness, mockLogger);

    const app = express();
    app.use('/api/v1/collab', createCollabRouter(presenceHandler, documentAccess));

    httpServer = createServer(app);
    httpServer.listen(0, () => {
      const addr = httpServer.address();
      baseUrl = `http://localhost:${typeof addr === 'object' && addr ? addr.port : 0}`;
      done();
    });
  });

  afterAll((done) => {
    httpServer.close(done);
  });

  beforeEach(() => {
    awareness.addUser(OWNED_DOC, 'socket-owner', OWNER, 'Owner', 'owner@test.com');
    awareness.addUser('doc-other', 'socket-other', OTHER, 'Other', 'other@test.com');
  });

  afterEach(() => {
    awareness.removeUser('socket-owner');
    awareness.removeUser('socket-other');
  });

  function get(path: string, userId?: string): Promise<Response> {
    const headers: Record<string, string> = {};
    if (userId) headers['X-User-ID'] = userId;
    return fetch(`${baseUrl}${path}`, { headers });
  }

  describe('GET /documents/:id/presence', () => {
    it('returns presence to the document owner', async () => {
      const response = await get(`/api/v1/collab/documents/${OWNED_DOC}/presence`, OWNER);
      expect(response.status).toBe(200);
      const body = (await response.json()) as { documentId: string; count: number };
      expect(body.documentId).toBe(OWNED_DOC);
      expect(body.count).toBe(1);
    });

    it('returns presence to a user the document is shared with', async () => {
      const response = await get(
        `/api/v1/collab/documents/${OWNED_DOC}/presence`,
        SHARED,
      );
      expect(response.status).toBe(200);
    });

    it('rejects another authenticated user with 403', async () => {
      const response = await get(`/api/v1/collab/documents/${OWNED_DOC}/presence`, OTHER);
      expect(response.status).toBe(403);
    });

    it('rejects a request without X-User-ID with 401', async () => {
      const response = await get(`/api/v1/collab/documents/${OWNED_DOC}/presence`);
      expect(response.status).toBe(401);
    });

    it('returns 404 for a document that does not exist', async () => {
      const response = await get(
        `/api/v1/collab/documents/${MISSING_DOC}/presence`,
        OWNER,
      );
      expect(response.status).toBe(404);
    });
  });

  describe('GET /documents', () => {
    it('lists only the documents the caller participates in', async () => {
      const response = await get('/api/v1/collab/documents', OWNER);
      expect(response.status).toBe(200);
      const body = (await response.json()) as {
        documents: Array<{ documentId: string }>;
        count: number;
      };
      expect(body.documents.map((d) => d.documentId)).toEqual([OWNED_DOC]);
      expect(body.count).toBe(1);
    });

    it('rejects a request without X-User-ID with 401', async () => {
      const response = await get('/api/v1/collab/documents');
      expect(response.status).toBe(401);
    });
  });
});

describe('Socket.IO document authorization', () => {
  let io: SocketIOServer;
  let httpServer: Server;
  let manager: CollaborationManager;
  let port: number;
  const clients: ClientSocket[] = [];

  const mockRedis = {
    get: jest.fn().mockResolvedValue(null),
    set: jest.fn().mockResolvedValue(undefined),
    lpush: jest.fn().mockResolvedValue(undefined),
    lrange: jest.fn().mockResolvedValue([]),
    ltrim: jest.fn().mockResolvedValue(undefined),
    expire: jest.fn().mockResolvedValue(undefined),
    hset: jest.fn().mockResolvedValue(undefined),
  } as unknown as jest.Mocked<RedisAdapter>;

  beforeAll((done) => {
    httpServer = createServer();
    io = new SocketIOServer(httpServer, { cors: { origin: '*' } });
    io.use(createAuthMiddleware(JWT_SECRET, mockLogger));

    const awareness = new AwarenessService(mockLogger);
    manager = new CollaborationManager({
      io,
      documentStore: new DocumentStore(mockRedis, mockLogger),
      awareness,
      presenceHandler: new PresenceHandler(awareness, mockLogger),
      documentAccess,
      metrics: new MetricsCollector(),
      logger: mockLogger,
      persistIntervalMs: 600000,
      snapshotIntervalMs: 600000,
    });
    manager.start();

    httpServer.listen(0, () => {
      const addr = httpServer.address();
      port = typeof addr === 'object' && addr ? addr.port : 0;
      done();
    });
  }, 15000);

  afterAll((done) => {
    for (const client of clients) client.disconnect();
    manager.stop();
    io.close();
    httpServer.close(done);
  });

  function connect(userId: string): Promise<ClientSocket> {
    const token = jwt.sign({ sub: userId, roles: ['user'] }, JWT_SECRET, {
      expiresIn: '1h',
    }); // nosemgrep: javascript.jsonwebtoken.security.jwt-hardcode.hardcoded-jwt-secret

    return new Promise((resolve, reject) => {
      const client = clientIO(`http://localhost:${port}`, {
        auth: { token },
        transports: ['websocket'],
      });
      clients.push(client);
      client.on('connect', () => resolve(client));
      client.on('connect_error', reject);
    });
  }

  function join(
    client: ClientSocket,
    documentId: string,
  ): Promise<{ success: boolean; error?: string }> {
    return new Promise((resolve) => {
      client.emit('join-document', { documentId }, resolve);
    });
  }

  function nextEvent<T>(client: ClientSocket, event: string): Promise<T> {
    return new Promise((resolve, reject) => {
      client.once(event, resolve);
      setTimeout(() => reject(new Error(`timed out waiting for ${event}`)), 3000);
    });
  }

  it('lets the owner join their document', async () => {
    const owner = await connect(OWNER);
    await expect(join(owner, OWNED_DOC)).resolves.toEqual({ success: true });
  });

  it('lets a user the document is shared with join', async () => {
    const shared = await connect(SHARED);
    await expect(join(shared, OWNED_DOC)).resolves.toEqual({ success: true });
  });

  it('rejects a join from another authenticated user', async () => {
    const other = await connect(OTHER);
    const syncLeak = nextEvent(other, 'sync-document').then(() => 'leaked');

    const response = await join(other, OWNED_DOC);
    expect(response).toEqual({ success: false, error: 'Access denied' });
    await expect(
      Promise.race([syncLeak, new Promise((r) => setTimeout(r, 300))]),
    ).resolves.not.toBe('leaked');
  });

  it('rejects document updates from a non-owner', async () => {
    const owner = await connect(OWNER);
    await join(owner, OWNED_DOC);

    const other = await connect(OTHER);
    const errorPromise = nextEvent<{ error: string }>(other, 'document-update-error');
    other.emit('document-update', { documentId: OWNED_DOC, update: 'AAA=' });

    await expect(errorPromise).resolves.toMatchObject({ error: 'Access denied' });
  });

  it('rejects history requests from a non-owner', async () => {
    const other = await connect(OTHER);
    const errorPromise = nextEvent<{ error: string }>(other, 'history-error');
    other.emit('request-history', { documentId: OWNED_DOC });

    await expect(errorPromise).resolves.toMatchObject({ error: 'Access denied' });
  });

  it('rejects snapshot requests from a non-owner', async () => {
    const other = await connect(OTHER);
    const errorPromise = nextEvent<{ error: string }>(other, 'snapshot-error');
    other.emit('request-snapshot', { documentId: OWNED_DOC });

    await expect(errorPromise).resolves.toMatchObject({ error: 'Access denied' });
  });

  it('rejects comment mutations from a non-owner', async () => {
    const other = await connect(OTHER);
    const errorPromise = nextEvent<{ action: string }>(other, 'comment-error');
    other.emit('comment-delete', { documentId: OWNED_DOC, commentId: 'c1' });

    await expect(errorPromise).resolves.toMatchObject({
      action: 'delete',
      error: 'Access denied',
    });
  });
});

describe('HttpDocumentAccessService', () => {
  const originalFetch = global.fetch;
  let fetchMock: jest.Mock;

  beforeEach(() => {
    fetchMock = jest.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterAll(() => {
    global.fetch = originalFetch;
  });

  function service(cacheTtlMs = 0): HttpDocumentAccessService {
    return new HttpDocumentAccessService(
      'http://document-service:8083',
      mockLogger,
      cacheTtlMs,
    );
  }

  it('allows the caller when document-service returns the document', async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200 });
    await expect(service().checkAccess('doc-1', { userId: OWNER })).resolves.toBe(
      'allow',
    );
    expect(fetchMock).toHaveBeenCalledWith(
      'http://document-service:8083/api/v1/documents/doc-1',
      expect.objectContaining({
        headers: expect.objectContaining({ 'X-User-ID': OWNER }),
      }),
    );
  });

  it('denies the caller when document-service returns 403', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 403 });
    await expect(service().checkAccess('doc-1', { userId: OTHER })).resolves.toBe(
      'denied',
    );
  });

  it('reports a missing document', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 404 });
    await expect(service().checkAccess('doc-1', { userId: OWNER })).resolves.toBe(
      'not-found',
    );
  });

  it('fails closed when document-service is unreachable', async () => {
    fetchMock.mockRejectedValue(new Error('ECONNREFUSED'));
    await expect(service().checkAccess('doc-1', { userId: OWNER })).resolves.toBe(
      'denied',
    );
  });

  it('denies a caller without an id', async () => {
    await expect(service().checkAccess('doc-1', { userId: '' })).resolves.toBe('denied');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('allows admin and internal service callers without a lookup', async () => {
    await expect(
      service().checkAccess('doc-1', { userId: 'admin-user', roles: ['ADMIN'] }),
    ).resolves.toBe('allow');
    await expect(
      service().checkAccess('doc-1', { userId: 'svc', roles: ['service'] }),
    ).resolves.toBe('allow');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('caches decisions per user and document', async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200 });
    const access = service(30000);
    await access.checkAccess('doc-1', { userId: OWNER });
    await access.checkAccess('doc-1', { userId: OWNER });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
