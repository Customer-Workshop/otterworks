package com.otterworks.ticketing.orders.outbox;

import java.util.List;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class OutboxRepository {

    private final JdbcClient jdbc;

    public OutboxRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public long append(String aggregateRef, String eventName, String key, String payloadJson) {
        return jdbc.sql("""
                        INSERT INTO outbox (aggregate_ref, event_name, key, payload)
                        VALUES (:agg, :event, :key, CAST(:payload AS jsonb)) RETURNING id""")
                .param("agg", aggregateRef).param("event", eventName).param("key", key).param("payload", payloadJson)
                .query(Long.class).single();
    }

    /** Oldest unpublished rows, locked for this transaction so several relays never publish the same row. */
    public List<OutboxRow> lockUnpublished(int limit) {
        return jdbc.sql("""
                        SELECT id, aggregate_ref, event_name, key, payload::text
                        FROM outbox WHERE published_at IS NULL
                        ORDER BY id LIMIT :limit FOR UPDATE SKIP LOCKED""")
                .param("limit", limit)
                .query((rs, i) -> new OutboxRow(rs.getLong(1), rs.getString(2), rs.getString(3), rs.getString(4),
                        rs.getString(5)))
                .list();
    }

    public void markPublished(long id) {
        jdbc.sql("UPDATE outbox SET published_at = now() WHERE id = :id").param("id", id).update();
    }

    public long countUnpublished() {
        return jdbc.sql("SELECT count(*) FROM outbox WHERE published_at IS NULL").query(Long.class).single();
    }

    public long countPublished() {
        return jdbc.sql("SELECT count(*) FROM outbox WHERE published_at IS NOT NULL").query(Long.class).single();
    }

    public record OutboxRow(long id, String aggregateRef, String eventName, String key, String payload) {
    }
}
