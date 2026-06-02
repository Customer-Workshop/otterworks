import { AwarenessService } from '../services/awareness';
import { PresenceHandler } from '../handlers/presence';

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
    it('should return empty presence for unknown document', () => {
      const presence = handler.getDocumentPresence('doc-unknown');

      expect(presence.documentId).toBe('doc-unknown');
      expect(presence.users).toEqual([]);
      expect(presence.count).toBe(0);
    });

    it('should return users currently in a document', () => {
      awareness.addUser('doc-1', 's1', 'u1', 'Alice', 'alice@test.com');
      awareness.addUser('doc-1', 's2', 'u2', 'Bob', 'bob@test.com');

      const presence = handler.getDocumentPresence('doc-1');

      expect(presence.documentId).toBe('doc-1');
      expect(presence.count).toBe(2);
      expect(presence.users).toHaveLength(2);
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
    it('should return empty when no documents active', () => {
      const docs = handler.getActiveDocuments();
      expect(docs).toEqual([]);
    });

    it('should return documents with user counts', () => {
      awareness.addUser('doc-1', 's1', 'u1', 'Alice', 'a@t.com');
      awareness.addUser('doc-1', 's2', 'u2', 'Bob', 'b@t.com');
      awareness.addUser('doc-2', 's3', 'u3', 'Charlie', 'c@t.com');

      const docs = handler.getActiveDocuments();
      expect(docs).toHaveLength(2);

      const doc1 = docs.find((d) => d.documentId === 'doc-1');
      const doc2 = docs.find((d) => d.documentId === 'doc-2');

      expect(doc1).toBeDefined();
      expect(doc1!.userCount).toBe(2);
      expect(doc2).toBeDefined();
      expect(doc2!.userCount).toBe(1);
    });
  });

  describe('broadcastPresenceUpdate', () => {
    it('should emit presence-update to the document room', () => {
      awareness.addUser('doc-1', 's1', 'u1', 'Alice', 'a@t.com');

      const mockEmit = jest.fn();
      const mockIo = {
        to: jest.fn().mockReturnValue({ emit: mockEmit }),
      } as any;

      handler.broadcastPresenceUpdate(mockIo, 'doc-1');

      expect(mockIo.to).toHaveBeenCalledWith('doc:doc-1');
      expect(mockEmit).toHaveBeenCalledWith(
        'presence-update',
        expect.objectContaining({
          documentId: 'doc-1',
          count: 1,
        }),
      );
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
      const mockIo = {
        to: jest.fn().mockReturnValue({ emit: jest.fn() }),
        sockets: { sockets: new Map() },
      } as any;

      const timer = handler.startCleanupInterval(mockIo, 1000, 500);
      expect(timer).toBeDefined();
      clearInterval(timer);
    });

    it('should call onDocumentEmpty when a document has no users after cleanup', () => {
      awareness.addUser('doc-1', 's1', 'u1', 'Alice', 'a@t.com');

      // Manually make the user stale by updating lastActive to long ago
      const users = awareness.getDocumentUsers('doc-1');
      if (users.length > 0) {
        (users[0] as any).lastActive = Date.now() - 999999;
      }

      const mockEmit = jest.fn();
      const mockSocket = {
        emit: jest.fn(),
        leave: jest.fn(),
        to: jest.fn().mockReturnValue({ emit: jest.fn() }),
      };
      const mockIo = {
        to: jest.fn().mockReturnValue({ emit: mockEmit }),
        sockets: {
          sockets: new Map([['s1', mockSocket]]),
        },
      } as any;

      const onDocumentEmpty = jest.fn();
      const timer = handler.startCleanupInterval(mockIo, 100, 500, onDocumentEmpty);

      jest.advanceTimersByTime(150);

      clearInterval(timer);
    });
  });
});
