import { PresenceHandler, type PresenceInfo } from '../handlers/presence';
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
    it('should return empty presence for unknown document', () => {
      const presence = handler.getDocumentPresence('unknown-doc');
      expect(presence.documentId).toBe('unknown-doc');
      expect(presence.users).toEqual([]);
      expect(presence.count).toBe(0);
    });

    it('should return users present in a document', () => {
      awareness.addUser('doc-1', 's1', 'u1', 'Alice', 'a@t.com');
      awareness.addUser('doc-1', 's2', 'u2', 'Bob', 'b@t.com');

      const presence = handler.getDocumentPresence('doc-1');
      expect(presence.documentId).toBe('doc-1');
      expect(presence.users).toHaveLength(2);
      expect(presence.count).toBe(2);
    });

    it('should reflect user removal', () => {
      awareness.addUser('doc-1', 's1', 'u1', 'Alice', 'a@t.com');
      awareness.removeUser('s1');

      const presence = handler.getDocumentPresence('doc-1');
      expect(presence.count).toBe(0);
    });
  });

  describe('getActiveDocuments', () => {
    it('should return empty array when no documents active', () => {
      const docs = handler.getActiveDocuments();
      expect(docs).toEqual([]);
    });

    it('should return active documents with user counts', () => {
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
  });

  describe('broadcastPresenceUpdate', () => {
    it('should emit presence-update to the document room', () => {
      awareness.addUser('doc-1', 's1', 'u1', 'Alice', 'a@t.com');

      const mockTo = jest.fn().mockReturnValue({ emit: jest.fn() });
      const mockIo = { to: mockTo } as any;

      handler.broadcastPresenceUpdate(mockIo, 'doc-1');
      expect(mockTo).toHaveBeenCalledWith('doc:doc-1');
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
      const mockTo = jest.fn().mockReturnValue({ emit: jest.fn() });
      const mockIo = { to: mockTo, sockets: { sockets: new Map() } } as any;

      const timer = handler.startCleanupInterval(mockIo, 1000, 500);
      expect(timer).toBeDefined();
      clearInterval(timer);
    });

    it('should call cleanup on interval', () => {
      const mockTo = jest.fn().mockReturnValue({ emit: jest.fn() });
      const mockIo = { to: mockTo, sockets: { sockets: new Map() } } as any;

      const cleanupSpy = jest.spyOn(awareness, 'cleanupStaleUsers');
      const timer = handler.startCleanupInterval(mockIo, 100, 50);

      jest.advanceTimersByTime(150);
      expect(cleanupSpy).toHaveBeenCalled();
      clearInterval(timer);
    });

    it('should invoke onDocumentEmpty when document becomes empty', () => {
      const onEmpty = jest.fn();
      const mockTo = jest.fn().mockReturnValue({ emit: jest.fn() });
      const mockEmit = jest.fn();
      const mockLeave = jest.fn();
      const mockSocketTo = jest.fn().mockReturnValue({ emit: jest.fn() });
      const mockSocket = {
        emit: mockEmit,
        leave: mockLeave,
        to: mockSocketTo,
      };
      const socketsMap = new Map([['s1', mockSocket]]);
      const mockIo = { to: mockTo, sockets: { sockets: socketsMap } } as any;

      awareness.addUser('doc-1', 's1', 'u1', 'Alice', 'a@t.com');

      const timer = handler.startCleanupInterval(mockIo, 100, 0, onEmpty);

      jest.advanceTimersByTime(150);
      expect(onEmpty).toHaveBeenCalledWith('doc-1');
      clearInterval(timer);
    });
  });
});
