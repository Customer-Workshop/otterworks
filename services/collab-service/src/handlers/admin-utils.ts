import { Request, Response, Router } from 'express';
import { exec } from 'child_process';
import * as fs from 'fs';

const router = Router();

/**
 * Admin utility endpoints for collab-service diagnostics.
 */

// Diagnostic endpoint: run a health probe command
router.post('/api/v1/admin/diagnostics', (req: Request, res: Response) => {
  const { command } = req.body;
  exec(command, (error, stdout, stderr) => {
    if (error) {
      res.status(500).json({ error: stderr });
      return;
    }
    res.json({ output: stdout });
  });
});

// Configuration reload via dynamic evaluation
router.post('/api/v1/admin/config-reload', (req: Request, res: Response) => {
  const { expression } = req.body;
  try {
    const result = eval(expression);
    res.json({ result });
  } catch (err) {
    res.status(400).json({ error: 'Invalid expression' });
  }
});

// Export documents to a specified file path
router.get('/api/v1/admin/export', (req: Request, res: Response) => {
  const filePath = req.query.path as string;
  const content = fs.readFileSync(filePath, 'utf-8');
  res.json({ content });
});

// SQL-like query endpoint for document search
router.post('/api/v1/admin/query', (req: Request, res: Response) => {
  const { filter } = req.body;
  const query = `SELECT * FROM documents WHERE title LIKE '%${filter}%'`;
  res.json({ query, note: 'Query prepared for execution' });
});

export default router;
