import type { Request, RequestHandler } from 'express';
import type { DocumentAccessChecker } from '../services/document-access';

/** Identity header injected by the api-gateway after it verifies the caller's JWT. */
export const USER_ID_HEADER = 'x-user-id';

/** Room-name prefix used by the y-websocket clients. */
export const ROOM_PREFIX = 'document-';

export function getCallerId(req: Request): string | null {
  const raw = req.headers[USER_ID_HEADER];
  const value = Array.isArray(raw) ? raw[0] : raw;
  return value && value.trim() ? value.trim() : null;
}

/**
 * The document id behind a y-websocket room name. Clients join `document-<id>`
 * (see the client-app editor), while document-service is keyed by `<id>` alone.
 */
export function documentIdFromRoom(room: string): string {
  return room.startsWith(ROOM_PREFIX) ? room.slice(ROOM_PREFIX.length) : room;
}

export function getBearerToken(req: Request): string | undefined {
  const header = req.headers.authorization;
  return header?.startsWith('Bearer ') ? header.slice('Bearer '.length) : undefined;
}

export const requireUserId: RequestHandler = (req, res, next) => {
  const userId = getCallerId(req);
  if (!userId) {
    res.status(401).json({ error: 'Authentication required' });
    return;
  }
  res.locals.userId = userId;
  next();
};

/** Requires that the caller resolved by requireUserId may access req.params[paramName]. */
export function requireDocumentAccess(
  documentAccess: DocumentAccessChecker,
  paramName = 'id',
): RequestHandler {
  return (req, res, next) => {
    const userId = res.locals.userId as string;
    const documentId = req.params[paramName];

    documentAccess
      .checkAccess(documentId, { userId, token: getBearerToken(req) })
      .then((decision) => {
        if (decision === 'allow') {
          next();
          return;
        }
        if (decision === 'not-found') {
          res.status(404).json({ error: 'Document not found' });
          return;
        }
        res.status(403).json({ error: 'Access denied' });
      })
      .catch(next);
  };
}
