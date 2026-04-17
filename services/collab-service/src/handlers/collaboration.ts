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

  io.on('connection', (socket: Socket) => {
    logger.info('client_connected', { socketId: socket.id });

    // Join a document room
    socket.on('join-document', async (data: { documentId: string; userId: string; displayName: string }) => {
      const { documentId, userId, displayName } = data;
      const room = `doc:${documentId}`;

      await socket.join(room);
      logger.info('user_joined_document', { documentId, userId, socketId: socket.id });

      // Get or create Yjs document
      let doc = documents.get(documentId);
      if (!doc) {
        doc = new Y.Doc();
        // Load existing state from Redis
        const savedState = await documentStore.getDocumentState(documentId);
        if (savedState) {
          Y.applyUpdate(doc, savedState);
        }
        documents.set(documentId, doc);
      }

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
    socket.on('disconnecting', () => {
      logger.info('client_disconnected', { socketId: socket.id });
      // Broadcast to all rooms this socket was in
      socket.rooms.forEach(room => {
        if (room.startsWith('doc:')) {
          socket.to(room).emit('user-left', { socketId: socket.id });
        }
      });
    });

    // Leave document
    socket.on('leave-document', (data: { documentId: string }) => {
      const room = `doc:${data.documentId}`;
      socket.leave(room);
      socket.to(room).emit('user-left', { socketId: socket.id });
      logger.info('user_left_document', { documentId: data.documentId, socketId: socket.id });
    });
  });

  // Periodically persist all active documents
  setInterval(async () => {
    for (const [documentId, doc] of documents) {
      const state = Y.encodeStateAsUpdate(doc);
      await documentStore.saveDocumentState(documentId, Buffer.from(state));
    }
  }, 30000); // Every 30 seconds
}
