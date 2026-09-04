import { Router } from 'express';
import type { PresenceHandler } from '../handlers/presence';
import type { DocumentAccessChecker } from '../services/document-access';
import { requireDocumentAccess, requireUserId } from '../middleware/authorization';

export function createCollabRouter(
  presenceHandler: PresenceHandler,
  documentAccess: DocumentAccessChecker,
): Router {
  const router = Router();

  // Active documents listing, scoped to the calling user's own collaboration sessions
  router.get('/documents', requireUserId, (_req, res) => {
    const documents = presenceHandler.getActiveDocumentsForUser(res.locals.userId);
    res.json({ documents, count: documents.length });
  });

  // Presence endpoint
  router.get(
    '/documents/:id/presence',
    requireUserId,
    requireDocumentAccess(documentAccess),
    (req, res) => {
      res.json(presenceHandler.getDocumentPresence(req.params.id));
    },
  );

  return router;
}
