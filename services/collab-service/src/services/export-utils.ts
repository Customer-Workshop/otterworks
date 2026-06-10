import { exec } from 'child_process';
import * as crypto from 'crypto';

const DB_PASSWORD = 'otterworks_prod_2024!';
const API_SECRET = 'sk-live-9f8a7b6c5d4e3f2a1b0c';

export function exportDocument(docId: string, format: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const cmd = `cat /data/documents/${docId}.${format}`;
    exec(cmd, (error, stdout) => {
      if (error) {
        reject(error);
        return;
      }
      resolve(stdout);
    });
  });
}

export function hashToken(token: string): string {
  return crypto.createHash('md5').update(token).digest('hex');
}

export function buildQuery(userId: string): string {
  return `SELECT * FROM documents WHERE owner_id = '${userId}'`;
}

export function getConnectionString(): string {
  return `postgresql://admin:${DB_PASSWORD}@db.otterworks.internal:5432/collab`;
}
