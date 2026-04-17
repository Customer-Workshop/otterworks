import { Registry, Counter, Gauge, Histogram, collectDefaultMetrics } from 'prom-client';

export class MetricsCollector {
  readonly registry: Registry;
  readonly activeConnections: Gauge;
  readonly activeRooms: Gauge;
  readonly messagesTotal: Counter;
  readonly documentUpdatesTotal: Counter;
  readonly documentSyncDuration: Histogram;
  readonly presenceUpdatesTotal: Counter;
  readonly commentAnnotationsTotal: Counter;
  readonly connectionErrors: Counter;
  readonly persistenceOperations: Counter;
  readonly persistenceDuration: Histogram;

  constructor() {
    this.registry = new Registry();

    collectDefaultMetrics({ register: this.registry });

    this.activeConnections = new Gauge({
      name: 'collab_active_connections',
      help: 'Number of active WebSocket connections',
      registers: [this.registry],
    });

    this.activeRooms = new Gauge({
      name: 'collab_active_rooms',
      help: 'Number of active document rooms',
      registers: [this.registry],
    });

    this.messagesTotal = new Counter({
      name: 'collab_messages_total',
      help: 'Total number of WebSocket messages processed',
      labelNames: ['type'] as const,
      registers: [this.registry],
    });

    this.documentUpdatesTotal = new Counter({
      name: 'collab_document_updates_total',
      help: 'Total number of document CRDT updates applied',
      registers: [this.registry],
    });

    this.documentSyncDuration = new Histogram({
      name: 'collab_document_sync_duration_seconds',
      help: 'Duration of document sync operations',
      buckets: [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1],
      registers: [this.registry],
    });

    this.presenceUpdatesTotal = new Counter({
      name: 'collab_presence_updates_total',
      help: 'Total number of presence updates',
      registers: [this.registry],
    });

    this.commentAnnotationsTotal = new Counter({
      name: 'collab_comment_annotations_total',
      help: 'Total number of comment annotation events',
      labelNames: ['action'] as const,
      registers: [this.registry],
    });

    this.connectionErrors = new Counter({
      name: 'collab_connection_errors_total',
      help: 'Total number of connection errors',
      labelNames: ['reason'] as const,
      registers: [this.registry],
    });

    this.persistenceOperations = new Counter({
      name: 'collab_persistence_operations_total',
      help: 'Total number of persistence operations',
      labelNames: ['operation', 'status'] as const,
      registers: [this.registry],
    });

    this.persistenceDuration = new Histogram({
      name: 'collab_persistence_duration_seconds',
      help: 'Duration of persistence operations',
      labelNames: ['operation'] as const,
      buckets: [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 5],
      registers: [this.registry],
    });
  }

  async getMetrics(): Promise<string> {
    return this.registry.metrics();
  }

  getContentType(): string {
    return this.registry.contentType;
  }
}
