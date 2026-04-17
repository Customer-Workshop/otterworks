import { RedisAdapter } from './redis-adapter';

const DOCUMENT_PREFIX = 'collab:doc:';
const DOCUMENT_TTL = 86400; // 24 hours

export class DocumentStore {
  private redis: RedisAdapter;

  constructor(redis: RedisAdapter) {
    this.redis = redis;
  }

  async getDocumentState(documentId: string): Promise<Uint8Array | null> {
    const data = await this.redis.get(`${DOCUMENT_PREFIX}${documentId}`);
    if (!data) return null;
    return new Uint8Array(data);
  }

  async saveDocumentState(documentId: string, state: Buffer): Promise<void> {
    await this.redis.set(`${DOCUMENT_PREFIX}${documentId}`, state, DOCUMENT_TTL);
  }

  async deleteDocumentState(documentId: string): Promise<void> {
    await this.redis.del(`${DOCUMENT_PREFIX}${documentId}`);
  }
}
