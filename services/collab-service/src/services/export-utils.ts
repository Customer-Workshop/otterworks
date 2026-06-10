import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';

const DB_PASSWORD = process.env.DB_PASSWORD ?? '';

const VALID_ID_PATTERN = /^[a-zA-Z0-9_-]+$/;

const DOCUMENTS_BASE_DIR = '/data/documents';

export function exportDocument(docId: string, format: string): Promise<string> {
  if (!VALID_ID_PATTERN.test(docId) || !VALID_ID_PATTERN.test(format)) {
    return Promise.reject(new Error('Invalid docId or format'));
  }

  // nosemgrep: javascript.lang.security.audit.path-traversal.path-join-resolve-traversal
  const filePath = path.resolve(DOCUMENTS_BASE_DIR, `${docId}.${format}`);

  if (!filePath.startsWith(DOCUMENTS_BASE_DIR + path.sep)) {
    return Promise.reject(new Error('Path traversal detected'));
  }

  return fs.promises.readFile(filePath, 'utf-8');
}

export function hashToken(token: string): string {
  return crypto.createHash('sha256').update(token).digest('hex');
}

export interface ParameterizedQuery {
  text: string;
  values: string[];
}

export function buildQuery(userId: string): ParameterizedQuery {
  return {
    text: 'SELECT * FROM documents WHERE owner_id = $1',
    values: [userId],
  };
}

export function getConnectionString(): string {
  return `postgresql://admin:${DB_PASSWORD}@db.otterworks.internal:5432/collab`;
}
