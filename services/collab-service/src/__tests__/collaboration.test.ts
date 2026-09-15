import { Server as SocketIOServer } from 'socket.io';
import { createServer } from 'http';
import { io as clientIO, Socket as ClientSocket } from 'socket.io-client';
import jwt from 'jsonwebtoken';
import * as Y from 'yjs';
import { CollaborationManager } from '../handlers/collaboration';
import { DocumentStore } from '../services/document-store';
import { AwarenessService } from '../services/awareness';
import { PresenceHandler } from '../handlers/presence';
import { MetricsCollector } from '../metrics';
import { createAuthMiddleware } from '../middleware/auth';
import { RedisAdapter } from '../services/redis-adapter';
import type { DocumentAccessChecker } from '../services/document-access';

const JWT_SECRET = 'test-secret-key-for-unit-tests';
let PORT: number;

function createToken(payload: Record<string, unknown>): string {
  return jwt.sign(payload, JWT_SECRET, { expiresIn: '1h' }); // nosemgrep: javascript.jsonwebtoken.security.jwt-hardcode.hardcoded-jwt-secret
}

const mockRedis = {
  get: jest.fn().mockResolvedValue(null),
  set: jest.fn().mockResolvedValue(undefined),
  del: jest.fn().mockResolvedValue(undefined),
  hset: jest.fn().mockResolvedValue(undefined),
  hget: jest.fn().mockResolvedValue(null),
  hgetall: jest.fn().mockResolvedValue({}),
  hdel: jest.fn().mockResolvedValue(undefined),
  hincrby: jest.fn().mockResolvedValue(1),
  lpush: jest.fn().mockResolvedValue(undefined),
  lrange: jest.fn().mockResolvedValue([]),
  ltrim: jest.fn().mockResolvedValue(undefined),
  llen: jest.fn().mockResolvedValue(0),
  expire: jest.fn().mockResolvedValue(undefined),
  publish: jest.fn().mockResolvedValue(undefined),
  subscribe: jest.fn().mockResolvedValue(undefined),
  connect: jest.fn().mockResolvedValue(undefined),
  disconnect: jest.fn(),
  ping: jest.fn().mockResolvedValue(true),
} as unknown as jest.Mocked<RedisAdapter>;

const FORBIDDEN_DOC_PREFIX = 'forbidden-';
const INTRUDER_USER = 'user-intruder';

const mockDocumentAccess: jest.Mocked<DocumentAccessChecker> = {
  canAccess: jest.fn(
    async (documentId: string, userId: string, token: string): Promise<boolean> =>
      !!token && userId !== INTRUDER_USER && !documentId.startsWith(FORBIDDEN_DOC_PREFIX),
  ),
};

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

describe('CollaborationManager', () => {
  let io: SocketIOServer;
  let httpServer: ReturnType<typeof createServer>;
  let manager: CollaborationManager;
  let metrics: MetricsCollector;
  let awareness: AwarenessService;
  let presenceHandler: PresenceHandler;
  let documentStore: DocumentStore;

  beforeAll((done) => {
    httpServer = createServer();
    io = new SocketIOServer(httpServer, {
      cors: { origin: '*' },
    });

    io.use(createAuthMiddleware(JWT_SECRET, mockLogger));

    metrics = new MetricsCollector();
    awareness = new AwarenessService(mockLogger);
    presenceHandler = new PresenceHandler(awareness, mockLogger);
    documentStore = new DocumentStore(mockRedis, mockLogger);

    manager = new CollaborationManager({
      io,
      documentStore,
      awareness,
      presenceHandler,
      documentAccess: mockDocumentAccess,
      metrics,
      logger: mockLogger,
      persistIntervalMs: 600000, // long interval so it doesn't fire during tests
      snapshotIntervalMs: 600000,
    });
    manager.start();

    httpServer.listen(0, () => {
      const addr = httpServer.address();
      PORT = typeof addr === 'object' && addr ? addr.port : 0;
      done();
    });
  }, 15000);

  afterAll((done) => {
    manager.stop();
    io.close();
    httpServer.close(done);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  function connectClient(userId: string, displayName: string): Promise<ClientSocket> {
    return new Promise((resolve, reject) => {
      const token = createToken({
        sub: userId,
        name: displayName,
        email: `${userId}@test.com`,
        roles: ['user'],
      });

      const client = clientIO(`http://localhost:${PORT}`, {
        auth: { token },
        transports: ['websocket'],
      });

      client.on('connect', () => resolve(client));
      client.on('connect_error', (err) => reject(err));

      setTimeout(() => reject(new Error('Connection timeout')), 5000);
    });
  }

  describe('Authentication', () => {
    it('should reject connections without a token', (done) => {
      const client = clientIO(`http://localhost:${PORT}`, {
        auth: {},
        transports: ['websocket'],
      });

      client.on('connect_error', (err) => {
        expect(err.message).toContain('Authentication required');
        client.disconnect();
        done();
      });
    });

    it('should reject connections with an invalid token', (done) => {
      const client = clientIO(`http://localhost:${PORT}`, {
        auth: { token: 'invalid-token-value' },
        transports: ['websocket'],
      });

      client.on('connect_error', (err) => {
        expect(err.message).toContain('Invalid or expired token');
        client.disconnect();
        done();
      });
    });

    it('should accept connections with a valid token', async () => {
      const client = await connectClient('user-auth-test', 'Test User');
      expect(client.connected).toBe(true);
      client.disconnect();
    });
  });

  describe('Document Joining', () => {
    it('should allow a user to join a document room', async () => {
      const client = await connectClient('user-join-1', 'Alice');

      const response = await new Promise<{ success: boolean }>((resolve) => {
        client.emit(
          'join-document',
          { documentId: 'doc-join-test' },
          (res: { success: boolean }) => resolve(res),
        );
      });

      expect(response.success).toBe(true);
      client.disconnect();
    });

    it('should sync document state to joining client', async () => {
      const client = await connectClient('user-sync-1', 'Bob');

      const syncPromise = new Promise<{ documentId: string; state: string }>(
        (resolve) => {
          client.on('sync-document', (data) => resolve(data));
        },
      );

      client.emit('join-document', { documentId: 'doc-sync-test' }, () => {});

      const syncData = await syncPromise;
      expect(syncData.documentId).toBe('doc-sync-test');
      expect(syncData.state).toBeDefined();

      client.disconnect();
    });

    it('should notify other users when someone joins', async () => {
      const client1 = await connectClient('user-notify-1', 'Alice');
      const client2 = await connectClient('user-notify-2', 'Bob');

      // Client 1 joins first
      await new Promise<void>((resolve) => {
        client1.emit('join-document', { documentId: 'doc-notify-test' }, () => resolve());
      });

      // Listen for join notification on client 1
      const joinPromise = new Promise<{ userId: string; displayName: string }>(
        (resolve) => {
          client1.on('user-joined', (data) => resolve(data));
        },
      );

      // Client 2 joins
      client2.emit('join-document', { documentId: 'doc-notify-test' }, () => {});

      const joinData = await joinPromise;
      expect(joinData.userId).toBe('user-notify-2');
      expect(joinData.displayName).toBe('Bob');

      client1.disconnect();
      client2.disconnect();
    });
  });

  describe('Document Authorization', () => {
    function joinDocument(
      client: ClientSocket,
      documentId: string,
    ): Promise<{ success: boolean; error?: string }> {
      return new Promise((resolve) => {
        client.emit('join-document', { documentId }, (res: { success: boolean }) =>
          resolve(res),
        );
      });
    }

    function expectNoEvent(client: ClientSocket, event: string, ms = 200): Promise<void> {
      return new Promise((resolve, reject) => {
        const timer = setTimeout(resolve, ms);
        client.once(event, (data) => {
          clearTimeout(timer);
          reject(new Error(`unexpected ${event}: ${JSON.stringify(data)}`));
        });
      });
    }

    it('should check document access with the caller identity and token on join', async () => {
      const client = await connectClient('user-authz-1', 'Alice');

      const response = await joinDocument(client, 'doc-authz-check');

      expect(response.success).toBe(true);
      expect(mockDocumentAccess.canAccess).toHaveBeenCalledWith(
        'doc-authz-check',
        'user-authz-1',
        expect.any(String),
      );
      client.disconnect();
    });

    it('should refuse to join and not sync state for a document the user cannot access', async () => {
      const client = await connectClient(INTRUDER_USER, 'Mallory');
      const noSync = expectNoEvent(client, 'sync-document');

      const response = await joinDocument(client, 'doc-victim');

      expect(response).toEqual({ success: false, error: 'Access denied' });
      await noSync;
      expect(awareness.getUserDocument(client.id as string)).toBeFalsy();
      expect(manager.getDocument('doc-victim')).toBeUndefined();
      client.disconnect();
    });

    it('should not apply or broadcast updates from a socket that has not joined the document', async () => {
      const owner = await connectClient('user-authz-owner', 'Alice');
      const intruder = await connectClient(INTRUDER_USER, 'Mallory');
      await joinDocument(owner, 'doc-authz-update');
      const denied = await joinDocument(intruder, 'doc-authz-update');
      expect(denied.success).toBe(false);

      const tempDoc = new Y.Doc();
      tempDoc.getText('content').insert(0, 'tampered');
      const update = Buffer.from(Y.encodeStateAsUpdate(tempDoc)).toString('base64');

      const ownerSawNothing = expectNoEvent(owner, 'document-update');
      const errorPromise = new Promise<{ error: string }>((resolve) => {
        intruder.on('document-update-error', (data) => resolve(data));
      });

      intruder.emit('document-update', { documentId: 'doc-authz-update', update });

      const err = await errorPromise;
      expect(err.error).toBe('Access denied');
      await ownerSawNothing;
      expect(manager.getDocument('doc-authz-update')?.getText('content').toString()).toBe(
        '',
      );
      expect(mockRedis.set).not.toHaveBeenCalled();

      owner.disconnect();
      intruder.disconnect();
    });

    it('should not return history or create snapshots for a socket outside the document', async () => {
      const owner = await connectClient('user-authz-owner-2', 'Alice');
      const intruder = await connectClient(INTRUDER_USER, 'Mallory');
      await joinDocument(owner, 'doc-authz-history');

      const historyError = new Promise<{ error: string }>((resolve) => {
        intruder.on('history-error', (data) => resolve(data));
      });
      const snapshotError = new Promise<{ error: string }>((resolve) => {
        intruder.on('snapshot-error', (data) => resolve(data));
      });
      const noHistory = expectNoEvent(intruder, 'document-history');
      const noSnapshot = expectNoEvent(intruder, 'snapshot-created');

      intruder.emit('request-history', { documentId: 'doc-authz-history' });
      intruder.emit('request-snapshot', { documentId: 'doc-authz-history' });

      expect((await historyError).error).toBe('Access denied');
      expect((await snapshotError).error).toBe('Access denied');
      await Promise.all([noHistory, noSnapshot]);
      expect(mockRedis.lrange).not.toHaveBeenCalled();
      expect(mockRedis.lpush).not.toHaveBeenCalled();

      owner.disconnect();
      intruder.disconnect();
    });

    it('should deny access to a forbidden document even for an otherwise valid user', async () => {
      const client = await connectClient('user-authz-2', 'Alice');

      const response = await joinDocument(client, `${FORBIDDEN_DOC_PREFIX}doc`);

      expect(response.success).toBe(false);
      client.disconnect();
    });
  });

  describe('Document Updates', () => {
    it('should broadcast document updates to other clients', async () => {
      const client1 = await connectClient('user-update-1', 'Alice');
      const client2 = await connectClient('user-update-2', 'Bob');

      // Both join the same document
      await Promise.all([
        new Promise<void>((resolve) => {
          client1.emit('join-document', { documentId: 'doc-update-test' }, () =>
            resolve(),
          );
        }),
        new Promise<void>((resolve) => {
          client2.emit('join-document', { documentId: 'doc-update-test' }, () =>
            resolve(),
          );
        }),
      ]);

      // Wait for sync to complete
      await new Promise((r) => setTimeout(r, 100));

      // Listen for update on client 2
      const updatePromise = new Promise<{
        documentId: string;
        update: string;
      }>((resolve) => {
        client2.on('document-update', (data) => resolve(data));
      });

      // Create a valid Yjs update
      const tempDoc = new Y.Doc();
      const text = tempDoc.getText('content');
      text.insert(0, 'Hello');
      const validUpdate = Y.encodeStateAsUpdate(tempDoc);
      const encodedUpdate = Buffer.from(validUpdate).toString('base64');

      client1.emit('document-update', {
        documentId: 'doc-update-test',
        update: encodedUpdate,
      });

      const updateData = await updatePromise;
      expect(updateData.documentId).toBe('doc-update-test');
      expect(updateData.update).toBe(encodedUpdate);

      client1.disconnect();
      client2.disconnect();
    });
  });

  describe('Cursor Updates', () => {
    it('should broadcast cursor updates to other clients', async () => {
      const client1 = await connectClient('user-cursor-1', 'Alice');
      const client2 = await connectClient('user-cursor-2', 'Bob');

      await Promise.all([
        new Promise<void>((resolve) => {
          client1.emit('join-document', { documentId: 'doc-cursor-test' }, () =>
            resolve(),
          );
        }),
        new Promise<void>((resolve) => {
          client2.emit('join-document', { documentId: 'doc-cursor-test' }, () =>
            resolve(),
          );
        }),
      ]);

      await new Promise((r) => setTimeout(r, 100));

      const cursorPromise = new Promise<{
        userId: string;
        cursor: { index: number; length: number };
      }>((resolve) => {
        client2.on('cursor-update', (data) => resolve(data));
      });

      client1.emit('cursor-update', {
        documentId: 'doc-cursor-test',
        cursor: { index: 42, length: 0 },
        selection: null,
      });

      const cursorData = await cursorPromise;
      expect(cursorData.userId).toBe('user-cursor-1');
      expect(cursorData.cursor).toEqual({ index: 42, length: 0 });

      client1.disconnect();
      client2.disconnect();
    });
  });

  describe('Disconnect Handling', () => {
    it('should notify others when a user disconnects', async () => {
      const client1 = await connectClient('user-disc-1', 'Alice');
      const client2 = await connectClient('user-disc-2', 'Bob');

      await Promise.all([
        new Promise<void>((resolve) => {
          client1.emit('join-document', { documentId: 'doc-disc-test' }, () => resolve());
        }),
        new Promise<void>((resolve) => {
          client2.emit('join-document', { documentId: 'doc-disc-test' }, () => resolve());
        }),
      ]);

      await new Promise((r) => setTimeout(r, 100));

      const leftPromise = new Promise<{ userId: string }>((resolve) => {
        client1.on('user-left', (data) => resolve(data));
      });

      client2.disconnect();

      const leftData = await leftPromise;
      expect(leftData.userId).toBe('user-disc-2');

      client1.disconnect();
    });
  });

  describe('Leave Document', () => {
    it('should allow a user to leave a document', async () => {
      const client1 = await connectClient('user-leave-1', 'Alice');
      const client2 = await connectClient('user-leave-2', 'Bob');

      await Promise.all([
        new Promise<void>((resolve) => {
          client1.emit('join-document', { documentId: 'doc-leave-test' }, () =>
            resolve(),
          );
        }),
        new Promise<void>((resolve) => {
          client2.emit('join-document', { documentId: 'doc-leave-test' }, () =>
            resolve(),
          );
        }),
      ]);

      await new Promise((r) => setTimeout(r, 100));

      const leftPromise = new Promise<{ socketId: string }>((resolve) => {
        client1.on('user-left', (data) => resolve(data));
      });

      client2.emit('leave-document', { documentId: 'doc-leave-test' });

      const leftData = await leftPromise;
      expect(leftData.socketId).toBeDefined();

      client1.disconnect();
      client2.disconnect();
    });
  });
});
