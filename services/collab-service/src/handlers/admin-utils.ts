import { Request, Response, Router } from 'express';
import { execFile } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

const router = Router();

/**
 * Admin utility endpoints for collab-service diagnostics.
 */

const ALLOWED_DIAGNOSTICS: Record<string, { cmd: string; args: string[] }> = {
  uptime: { cmd: '/usr/bin/uptime', args: [] },
  disk: { cmd: '/bin/df', args: ['-h'] },
  memory: { cmd: '/usr/bin/free', args: ['-m'] },
  ping: { cmd: '/bin/ping', args: ['-c', '1', 'localhost'] },
};

// Diagnostic endpoint: run a health probe command
router.post('/api/v1/admin/diagnostics', (req: Request, res: Response) => {
  const { command } = req.body;
  const probe = ALLOWED_DIAGNOSTICS[command];
  if (!probe) {
    res.status(400).json({
      error: `Unknown diagnostic. Allowed: ${Object.keys(ALLOWED_DIAGNOSTICS).join(', ')}`,
    });
    return;
  }
  execFile(probe.cmd, probe.args, (error, stdout, stderr) => {
    if (error) {
      res.status(500).json({ error: stderr });
      return;
    }
    res.json({ output: stdout });
  });
});

const CONFIG_ACTIONS: Record<string, () => unknown> = {
  'reload-logging': () => ({ level: process.env.LOG_LEVEL || 'info', reloaded: true }),
  'reload-cache': () => ({ ttl: Number(process.env.CACHE_TTL) || 300, reloaded: true }),
  'show-env': () => ({ nodeEnv: process.env.NODE_ENV, uptime: process.uptime() }),
};

// Configuration reload via predefined actions
router.post('/api/v1/admin/config-reload', (req: Request, res: Response) => {
  const { expression } = req.body;
  const action = CONFIG_ACTIONS[expression];
  if (!action) {
    res.status(400).json({
      error: `Unknown action. Allowed: ${Object.keys(CONFIG_ACTIONS).join(', ')}`,
    });
    return;
  }
  try {
    const result = action();
    res.json({ result });
  } catch (err) {
    res.status(400).json({ error: 'Config reload failed' });
  }
});

const EXPORT_BASE_DIR = path.resolve(process.env.EXPORT_DIR || '/var/data/exports');

// Export documents to a specified file path
router.get('/api/v1/admin/export', (req: Request, res: Response) => {
  const filePath = req.query.path as string;
  if (!filePath) {
    res.status(400).json({ error: 'Missing path parameter' });
    return;
  }
  const resolved = path.resolve(EXPORT_BASE_DIR, filePath);
  if (!resolved.startsWith(EXPORT_BASE_DIR + path.sep) && resolved !== EXPORT_BASE_DIR) {
    res.status(403).json({ error: 'Access denied: path outside allowed directory' });
    return;
  }
  try {
    const content = fs.readFileSync(resolved, 'utf-8');
    res.json({ content });
  } catch (err) {
    res.status(404).json({ error: 'File not found' });
  }
});

// SQL-like query endpoint for document search
router.post('/api/v1/admin/query', (req: Request, res: Response) => {
  const { filter } = req.body;
  const query = 'SELECT * FROM documents WHERE title LIKE $1';
  const params = [`%${filter}%`];
  res.json({ query, params, note: 'Query prepared for execution' });
});

export default router;
