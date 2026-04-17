import type { Server as SocketIOServer } from 'socket.io';
import type { Logger } from 'pino';
import { AwarenessService, type UserAwareness } from '../services/awareness';

export interface PresenceInfo {
  documentId: string;
  users: UserAwareness[];
  count: number;
}

export class PresenceHandler {
  private awareness: AwarenessService;
  private logger: Logger;

  constructor(awareness: AwarenessService, logger: Logger) {
    this.awareness = awareness;
    this.logger = logger;
  }

  getDocumentPresence(documentId: string): PresenceInfo {
    const users = this.awareness.getDocumentUsers(documentId);
    return {
      documentId,
      users,
      count: users.length,
    };
  }

  getActiveDocuments(): Array<{ documentId: string; userCount: number }> {
    const documentIds = this.awareness.getActiveDocumentIds();
    return documentIds.map((documentId) => ({
      documentId,
      userCount: this.awareness.getDocumentUserCount(documentId),
    }));
  }

  broadcastPresenceUpdate(io: SocketIOServer, documentId: string): void {
    const presence = this.getDocumentPresence(documentId);
    const room = `doc:${documentId}`;
    io.to(room).emit('presence-update', presence);
  }

  startCleanupInterval(
    io: SocketIOServer,
    intervalMs = 60000,
    maxIdleMs = 300000,
  ): NodeJS.Timeout {
    return setInterval(() => {
      const removed = this.awareness.cleanupStaleUsers(maxIdleMs);
      for (const entry of removed) {
        this.broadcastPresenceUpdate(io, entry.documentId);
        this.logger.info(
          { documentId: entry.documentId, userId: entry.userId },
          'stale_user_removed_from_presence',
        );
      }
    }, intervalMs);
  }
}
