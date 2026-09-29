package com.boxoffice.payments.repo;

import com.boxoffice.payments.domain.DeliveryTarget;
import com.boxoffice.payments.domain.OutcomeDelivery;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

/** outcome_deliveries: the outbox the InboxRelay drains. Callers own the transaction boundaries. */
@Repository
public class DeliveryRepository {

    private static final RowMapper<OutcomeDelivery> DELIVERY = (rs, i) -> new OutcomeDelivery(
            rs.getLong("id"), rs.getString("order_ref"), DeliveryTarget.valueOf(rs.getString("target")),
            rs.getString("event"), rs.getString("payload"), rs.getInt("attempts"),
            instant(rs, "next_attempt_at"), instant(rs, "delivered_at"), instant(rs, "given_up_at"), instant(rs, "created_at"));

    private final JdbcTemplate jdbc;

    public DeliveryRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** No-op when a row for (orderRef, target) already exists: a redelivered record never enqueues twice. */
    public void enqueue(String orderRef, DeliveryTarget target, String event, String payload, Instant at) {
        jdbc.update("""
                INSERT INTO outcome_deliveries (order_ref, target, event, payload, next_attempt_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING""",
                orderRef, target.name(), event, payload, ts(at), ts(at));
    }

    /** Lock a batch of due rows (skipping rows another replica holds) and push their next attempt out by the lease. */
    public List<OutcomeDelivery> claim(int batchSize, Instant now, Instant leaseUntil) {
        List<OutcomeDelivery> due = jdbc.query("""
                SELECT * FROM outcome_deliveries
                WHERE delivered_at IS NULL AND given_up_at IS NULL AND next_attempt_at <= ?
                ORDER BY id LIMIT ? FOR UPDATE SKIP LOCKED""", DELIVERY, ts(now), batchSize);
        for (OutcomeDelivery d : due) {
            jdbc.update("UPDATE outcome_deliveries SET next_attempt_at = ? WHERE id = ?", ts(leaseUntil), d.id());
        }
        return due;
    }

    public void markDelivered(long id, Instant at) {
        jdbc.update("UPDATE outcome_deliveries SET delivered_at = ?, attempts = attempts + 1, last_error = NULL WHERE id = ?",
                ts(at), id);
    }

    public void markFailed(long id, Instant nextAttemptAt, String error) {
        jdbc.update("UPDATE outcome_deliveries SET attempts = attempts + 1, next_attempt_at = ?, last_error = ? WHERE id = ?",
                ts(nextAttemptAt), truncate(error), id);
    }

    public void markGivenUp(long id, Instant at, String error) {
        jdbc.update("UPDATE outcome_deliveries SET attempts = attempts + 1, given_up_at = ?, last_error = ? WHERE id = ?",
                ts(at), truncate(error), id);
    }

    public long pendingCount() {
        Long n = jdbc.queryForObject(
                "SELECT COUNT(*) FROM outcome_deliveries WHERE delivered_at IS NULL AND given_up_at IS NULL", Long.class);
        return n == null ? 0 : n;
    }

    public long givenUpCount() {
        Long n = jdbc.queryForObject("SELECT COUNT(*) FROM outcome_deliveries WHERE given_up_at IS NOT NULL", Long.class);
        return n == null ? 0 : n;
    }

    public List<OutcomeDelivery> forOrder(String orderRef) {
        return jdbc.query("SELECT * FROM outcome_deliveries WHERE order_ref = ? ORDER BY id", DELIVERY, orderRef);
    }

    private static String truncate(String s) {
        return s == null ? null : s.length() > 255 ? s.substring(0, 255) : s;
    }

    private static OffsetDateTime ts(Instant at) {
        return at.atOffset(ZoneOffset.UTC);
    }

    private static Instant instant(ResultSet rs, String column) throws SQLException {
        OffsetDateTime t = rs.getObject(column, OffsetDateTime.class);
        return t == null ? null : t.toInstant();
    }
}
