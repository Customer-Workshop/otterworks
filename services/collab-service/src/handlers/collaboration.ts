import { Server as SocketIOServer, Socket } from 'socket.io';
import { Logger } from 'winston';
import * as Y from 'yjs';
import { DocumentStore } from '../services/document-store';

interface CursorPosition {
  userId: string;
  displayName: string;
  color: string;
  anchor: number;
  head: number;
}

export function setupCollaborationHandlers(
  io: SocketIOServer,
  documentStore: DocumentStore,
  logger: Logger,
): void {
  // Track Yjs documents in memory
  const documents = new Map<string, Y.Doc>();
  // Prevent race conditions during concurrent document initialization
  const documentInitPromises = new Map<string, Promise<Y.Doc>>();

  async function getOrCreateDoc(documentId: string): Promise<Y.Doc> {
    const existing = documents.get(documentId);
    if (existing) return existing;

    const pending = documentInitPromises.get(documentId);
    if (pending) return pending;

    const initPromise = (async () => {
      const doc = new Y.Doc();
      const savedState = await documentStore.getDocumentState(documentId);
      if (savedState) {
        Y.applyUpdate(doc, savedState);
      }
      documents.set(documentId, doc);
      documentInitPromises.delete(documentId);
      return doc;
    })();

    documentInitPromises.set(documentId, initPromise);
    return initPromise;
  }

  io.on('connection', (socket: Socket) => {
    logger.info('client_connected', { socketId: socket.id });

    // Join a document room
    socket.on('join-document', async (data: { documentId: string; userId: string; displayName: string }) => {
      const { documentId, userId, displayName } = data;
      const room = `doc:${documentId}`;

      await socket.join(room);
      logger.info('user_joined_document', { documentId, userId, socketId: socket.id });

      // Get or create Yjs document (safe against concurrent joins)
      const doc = await getOrCreateDoc(documentId);

      // Send current document state to new client
      const state = Y.encodeStateAsUpdate(doc);
      socket.emit('sync-document', { documentId, state: Buffer.from(state).toString('base64') });

      // Broadcast user joined
      socket.to(room).emit('user-joined', { userId, displayName, socketId: socket.id });

      // Get current users in room
      const sockets = await io.in(room).fetchSockets();
      socket.emit('room-users', {
        documentId,
        users: sockets.map(s => s.id),
        count: sockets.length,
      });
    });

    // Handle document updates (CRDT)
    socket.on('document-update', async (data: { documentId: string; update: string }) => {
      const { documentId, update } = data;
      const room = `doc:${documentId}`;

      const doc = documents.get(documentId);
      if (doc) {
        const updateBytes = Buffer.from(update, 'base64');
        Y.applyUpdate(doc, new Uint8Array(updateBytes));

        // Persist to Redis
        const fullState = Y.encodeStateAsUpdate(doc);
        await documentStore.saveDocumentState(documentId, Buffer.from(fullState));

        // Broadcast to other clients in the room
        socket.to(room).emit('document-update', { documentId, update });
      }
    });

    // Handle cursor position updates
    socket.on('cursor-update', (data: { documentId: string; cursor: CursorPosition }) => {
      const room = `doc:${data.documentId}`;
      socket.to(room).emit('cursor-update', {
        socketId: socket.id,
        cursor: data.cursor,
      });
    });

    // Handle disconnect - use 'disconnecting' because Socket.IO v4 clears rooms before 'disconnect'
    socket.on('disconnecting', async () => {
      logger.info('client_disconnected', { socketId: socket.id });
      // Broadcast to all rooms this socket was in and clean up empty rooms
      for (const room of socket.rooms) {
        if (room.startsWith('doc:')) {
          socket.to(room).emit('user-left', { socketId: socket.id });
          // Check if room will be empty after this socket leaves (subtract 1 for current socket)
          const sockets = await io.in(room).fetchSockets();
          if (sockets.length <= 1) {
            const documentId = room.slice(4); // Remove 'doc:' prefix
            const doc = documents.get(documentId);
            if (doc) {
              const state = Y.encodeStateAsUpdate(doc);
              await documentStore.saveDocumentState(documentId, Buffer.from(state));
              documents.delete(documentId);
              logger.info('document_evicted', { documentId, reason: 'room_empty' });
            }
          }
        }
      }
    });

    // Leave document
    socket.on('leave-document', async (data: { documentId: string }) => {
      const room = `doc:${data.documentId}`;
      socket.leave(room);
      socket.to(room).emit('user-left', { socketId: socket.id });
      logger.info('user_left_document', { documentId: data.documentId, socketId: socket.id });

      // Clean up Y.Doc if room is now empty
      const sockets = await io.in(room).fetchSockets();
      if (sockets.length === 0) {
        const doc = documents.get(data.documentId);
        if (doc) {
          const state = Y.encodeStateAsUpdate(doc);
          await documentStore.saveDocumentState(data.documentId, Buffer.from(state));
          documents.delete(data.documentId);
          logger.info('document_evicted', { documentId: data.documentId, reason: 'room_empty' });
        }
      }
    });
  });

  // Periodically persist all active documents
  setInterval(async () => {
    for (const [documentId, doc] of documents) {
      try {
        const state = Y.encodeStateAsUpdate(doc);
        await documentStore.saveDocumentState(documentId, Buffer.from(state));
      } catch (err) {
        logger.error('periodic_save_failed', { documentId, error: String(err) });
      }
    }
  }, 30000); // Every 30 seconds
}
