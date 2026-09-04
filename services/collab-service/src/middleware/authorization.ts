import type { Request, RequestHandler } from 'express';
import type { DocumentAccessChecker } from '../services/document-access';

/** Identity header injected by the api-gateway after it verifies the caller's JWT. */
export const USER_ID_HEADER = 'x-user-id';

export function getCallerId(req: Request): string | null {
  const raw = req.headers[USER_ID_HEADER];
  const value = Array.isArray(raw) ? raw[0] : raw;
  return value && value.trim() ? value.trim() : null;
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
