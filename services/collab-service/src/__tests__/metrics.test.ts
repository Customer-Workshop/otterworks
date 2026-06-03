import { MetricsCollector } from '../metrics';

describe('MetricsCollector', () => {
  let metrics: MetricsCollector;

  beforeEach(() => {
    metrics = new MetricsCollector();
  });

  afterEach(() => {
    metrics.registry.clear();
  });

  describe('constructor', () => {
    it('should initialize all metric instances', () => {
      expect(metrics.activeConnections).toBeDefined();
      expect(metrics.activeRooms).toBeDefined();
      expect(metrics.messagesTotal).toBeDefined();
      expect(metrics.documentUpdatesTotal).toBeDefined();
      expect(metrics.documentSyncDuration).toBeDefined();
      expect(metrics.presenceUpdatesTotal).toBeDefined();
      expect(metrics.commentAnnotationsTotal).toBeDefined();
      expect(metrics.connectionErrors).toBeDefined();
      expect(metrics.persistenceOperations).toBeDefined();
      expect(metrics.persistenceDuration).toBeDefined();
    });

    it('should register metrics in the registry', async () => {
      const output = await metrics.getMetrics();
      expect(output).toContain('collab_active_connections');
      expect(output).toContain('collab_active_rooms');
      expect(output).toContain('collab_messages_total');
      expect(output).toContain('collab_document_updates_total');
      expect(output).toContain('collab_document_sync_duration_seconds');
      expect(output).toContain('collab_presence_updates_total');
      expect(output).toContain('collab_comment_annotations_total');
      expect(output).toContain('collab_connection_errors_total');
      expect(output).toContain('collab_persistence_operations_total');
      expect(output).toContain('collab_persistence_duration_seconds');
    });
  });

  describe('activeConnections gauge', () => {
    it('should increment and decrement', async () => {
      metrics.activeConnections.inc();
      metrics.activeConnections.inc();
      metrics.activeConnections.dec();

      const output = await metrics.getMetrics();
      expect(output).toContain('collab_active_connections 1');
    });
  });

  describe('messagesTotal counter', () => {
    it('should count messages by type', async () => {
      metrics.messagesTotal.inc({ type: 'document-update' });
      metrics.messagesTotal.inc({ type: 'document-update' });
      metrics.messagesTotal.inc({ type: 'cursor-update' });

      const output = await metrics.getMetrics();
      expect(output).toContain('collab_messages_total{type="document-update"} 2');
      expect(output).toContain('collab_messages_total{type="cursor-update"} 1');
    });
  });

  describe('documentSyncDuration histogram', () => {
    it('should observe durations', async () => {
      metrics.documentSyncDuration.observe(0.003);
      metrics.documentSyncDuration.observe(0.05);

      const output = await metrics.getMetrics();
      expect(output).toContain('collab_document_sync_duration_seconds_count 2');
    });
  });

  describe('connectionErrors counter', () => {
    it('should count errors by reason', async () => {
      metrics.connectionErrors.inc({ reason: 'auth_failed' });
      metrics.connectionErrors.inc({ reason: 'timeout' });
      metrics.connectionErrors.inc({ reason: 'auth_failed' });

      const output = await metrics.getMetrics();
      expect(output).toContain('collab_connection_errors_total{reason="auth_failed"} 2');
      expect(output).toContain('collab_connection_errors_total{reason="timeout"} 1');
    });
  });

  describe('persistenceOperations counter', () => {
    it('should count by operation and status', async () => {
      metrics.persistenceOperations.inc({ operation: 'save', status: 'success' });
      metrics.persistenceOperations.inc({ operation: 'save', status: 'failure' });
      metrics.persistenceOperations.inc({ operation: 'load', status: 'success' });

      const output = await metrics.getMetrics();
      expect(output).toContain(
        'collab_persistence_operations_total{operation="save",status="success"} 1',
      );
      expect(output).toContain(
        'collab_persistence_operations_total{operation="save",status="failure"} 1',
      );
      expect(output).toContain(
        'collab_persistence_operations_total{operation="load",status="success"} 1',
      );
    });
  });

  describe('getMetrics', () => {
    it('should return a string in Prometheus exposition format', async () => {
      const output = await metrics.getMetrics();
      expect(typeof output).toBe('string');
      expect(output).toContain('# HELP');
      expect(output).toContain('# TYPE');
    });
  });

  describe('getContentType', () => {
    it('should return the Prometheus content type', () => {
      const contentType = metrics.getContentType();
      expect(contentType).toContain('text/plain');
    });
  });
});
