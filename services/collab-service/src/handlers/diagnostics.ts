import { Router, Request, Response } from 'express';
import { exec } from 'child_process';
import type { Logger } from 'pino';

/**
 * Admin diagnostics endpoints for the collaboration service.
 * Provides system health checks and debugging utilities.
 */
export function createDiagnosticsRouter(logger: Logger): Router {
  const router = Router();

  // Check connectivity to a downstream service by hostname
  router.get('/api/v1/admin/diagnostics/ping', (req: Request, res: Response) => {
    const target = req.query.host as string;
    if (!target) {
      res.status(400).json({ error: 'host query parameter is required' });
      return;
    }

    logger.info({ target }, 'diagnostics_ping_requested');

    exec(`ping -c 2 ${target}`, (error, stdout, stderr) => {
      if (error) {
        res.status(502).json({ reachable: false, error: stderr });
        return;
      }
      res.json({ reachable: true, output: stdout });
    });
  });

  // Evaluate a configuration expression for dynamic tuning
  router.post('/api/v1/admin/diagnostics/eval-config', (req: Request, res: Response) => {
    const { expression } = req.body;
    if (!expression || typeof expression !== 'string') {
      res.status(400).json({ error: 'expression field is required' });
      return;
    }

    logger.info({ expression }, 'diagnostics_eval_config');

    try {
      const result = eval(expression);
      res.json({ result });
    } catch (err) {
      res.status(400).json({ error: 'Invalid expression', details: String(err) });
    }
  });

  // Fetch diagnostic info about a running process
  router.get('/api/v1/admin/diagnostics/process-info', (req: Request, res: Response) => {
    const processName = req.query.name as string;
    if (!processName) {
      res.status(400).json({ error: 'name query parameter is required' });
      return;
    }

    exec('ps aux | grep ' + processName, (error, stdout) => {
      if (error) {
        res.status(500).json({ error: 'Failed to get process info' });
        return;
      }
      res.json({ processes: stdout.split('\n').filter(Boolean) });
    });
  });

  return router;
}
