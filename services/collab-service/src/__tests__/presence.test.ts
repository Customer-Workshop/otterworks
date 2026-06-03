import { PresenceHandler } from '../handlers/presence';
import { AwarenessService } from '../services/awareness';

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

describe('PresenceHandler', () => {
  let awareness: AwarenessService;
  let handler: PresenceHandler;

  beforeEach(() => {
    jest.clearAllMocks();
    awareness = new AwarenessService(mockLogger);
    handler = new PresenceHandler(awareness, mockLogger);
  });

  describe('getDocumentPresence', () => {
    it('should return empty presence for a document with no users', () => {
      const presence = handler.getDocumentPresence('doc-empty');

      expect(presence.documentId).toBe('doc-empty');
      expect(presence.users).toEqual([]);
      expect(presence.count).toBe(0);
    });

    it('should return users and count for an active document', () => {
      awareness.addUser('doc-1', 's1', 'u1', 'Alice', 'alice@test.com');
      awareness.addUser('doc-1', 's2', 'u2', 'Bob', 'bob@test.com');

      const presence = handler.getDocumentPresence('doc-1');

      expect(presence.documentId).toBe('doc-1');
      expect(presence.users).toHaveLength(2);
      expect(presence.count).toBe(2);
      expect(presence.users.map((u) => u.userId).sort()).toEqual(['u1', 'u2']);
    });

    it('should reflect user removal', () => {
      awareness.addUser('doc-1', 's1', 'u1', 'Alice', 'alice@test.com');
      awareness.addUser('doc-1', 's2', 'u2', 'Bob', 'bob@test.com');
      awareness.removeUser('s1');

      const presence = handler.getDocumentPresence('doc-1');

      expect(presence.count).toBe(1);
      expect(presence.users[0].userId).toBe('u2');
    });
  });

  describe('getActiveDocuments', () => {
    it('should return empty array when no documents are active', () => {
      const docs = handler.getActiveDocuments();
      expect(docs).toEqual([]);
    });

    it('should list all active documents with user counts', () => {
      awareness.addUser('doc-1', 's1', 'u1', 'Alice', 'a@t.com');
      awareness.addUser('doc-1', 's2', 'u2', 'Bob', 'b@t.com');
      awareness.addUser('doc-2', 's3', 'u3', 'Charlie', 'c@t.com');

      const docs = handler.getActiveDocuments();

      expect(docs).toHaveLength(2);

      const doc1 = docs.find((d) => d.documentId === 'doc-1');
      const doc2 = docs.find((d) => d.documentId === 'doc-2');

      expect(doc1?.userCount).toBe(2);
      expect(doc2?.userCount).toBe(1);
    });

    it('should not include documents after all users leave', () => {
      awareness.addUser('doc-1', 's1', 'u1', 'Alice', 'a@t.com');
      awareness.removeUser('s1');

      const docs = handler.getActiveDocuments();
      expect(docs).toEqual([]);
    });
  });

  describe('broadcastPresenceUpdate', () => {
    it('should emit presence-update to the correct room', () => {
      awareness.addUser('doc-1', 's1', 'u1', 'Alice', 'a@t.com');

      const mockEmit = jest.fn();
      const mockTo = jest.fn().mockReturnValue({ emit: mockEmit });
      const mockIO = { to: mockTo } as any;

      handler.broadcastPresenceUpdate(mockIO, 'doc-1');

      expect(mockTo).toHaveBeenCalledWith('doc:doc-1');
      expect(mockEmit).toHaveBeenCalledWith('presence-update', {
        documentId: 'doc-1',
        users: expect.any(Array),
        count: 1,
      });
    });
  });

  describe('startCleanupInterval', () => {
    beforeEach(() => {
      jest.useFakeTimers();
    });

    afterEach(() => {
      jest.useRealTimers();
    });

    it('should return a timer handle', () => {
      const mockIO = { to: jest.fn().mockReturnValue({ emit: jest.fn() }), sockets: { sockets: new Map() } } as any;
      const timer = handler.startCleanupInterval(mockIO, 1000, 500);
      expect(timer).toBeDefined();
      clearInterval(timer);
    });

    it('should remove stale users after the idle timeout', () => {
      const mockEmit = jest.fn();
      const mockTo = jest.fn().mockReturnValue({ emit: mockEmit });
      const mockIO = { to: mockTo, sockets: { sockets: new Map() } } as any;

      awareness.addUser('doc-1', 's1', 'u1', 'Alice', 'a@t.com');

      // Manually make user stale by setting lastActive in the past
      const users = awareness.getDocumentUsers('doc-1');
      (users[0] as any).lastActive = Date.now() - 600000;

      const timer = handler.startCleanupInterval(mockIO, 100, 500);

      jest.advanceTimersByTime(150);

      expect(awareness.getDocumentUserCount('doc-1')).toBe(0);
      clearInterval(timer);
    });

    it('should call onDocumentEmpty callback when a document has no users left', () => {
      const mockEmit = jest.fn();
      const mockTo = jest.fn().mockReturnValue({ emit: mockEmit });
      const mockIO = { to: mockTo, sockets: { sockets: new Map() } } as any;
      const onDocumentEmpty = jest.fn();

      awareness.addUser('doc-1', 's1', 'u1', 'Alice', 'a@t.com');
      const users = awareness.getDocumentUsers('doc-1');
      (users[0] as any).lastActive = Date.now() - 600000;

      const timer = handler.startCleanupInterval(mockIO, 100, 500, onDocumentEmpty);

      jest.advanceTimersByTime(150);

      expect(onDocumentEmpty).toHaveBeenCalledWith('doc-1');
      clearInterval(timer);
    });

    it('should emit session-expired to evicted sockets', () => {
      const mockSocketEmit = jest.fn();
      const mockSocketLeave = jest.fn();
      const mockSocketTo = jest.fn().mockReturnValue({ emit: jest.fn() });
      const mockSocket = {
        emit: mockSocketEmit,
        leave: mockSocketLeave,
        to: mockSocketTo,
      };

      const socketsMap = new Map();
      socketsMap.set('s1', mockSocket);

      const mockEmit = jest.fn();
      const mockTo = jest.fn().mockReturnValue({ emit: mockEmit });
      const mockIO = { to: mockTo, sockets: { sockets: socketsMap } } as any;

      awareness.addUser('doc-1', 's1', 'u1', 'Alice', 'a@t.com');
      const users = awareness.getDocumentUsers('doc-1');
      (users[0] as any).lastActive = Date.now() - 600000;

      const timer = handler.startCleanupInterval(mockIO, 100, 500);
      jest.advanceTimersByTime(150);

      expect(mockSocketEmit).toHaveBeenCalledWith('session-expired', {
        documentId: 'doc-1',
        reason: 'idle_timeout',
      });
      expect(mockSocketLeave).toHaveBeenCalledWith('doc:doc-1');
      clearInterval(timer);
    });
  });
});
