package com.boxoffice.payments.repo;

import com.boxoffice.payments.domain.Payment;
import com.boxoffice.payments.domain.PaymentAttempt;
import com.boxoffice.payments.domain.PaymentStats;
import com.boxoffice.payments.domain.PaymentStatus;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class PaymentRepository {

    private static final RowMapper<Payment> PAYMENT = (rs, i) -> new Payment(
            rs.getLong("id"), rs.getString("order_ref"), rs.getString("hold_ref"), rs.getLong("amount_cents"),
            rs.getString("currency"), PaymentStatus.valueOf(rs.getString("status")), rs.getString("gateway_ref"),
            rs.getString("card_last4"), rs.getString("provider"), rs.getInt("duplicate_deliveries"),
            instant(rs, "created_at"));

    private static final RowMapper<PaymentAttempt> ATTEMPT = (rs, i) -> new PaymentAttempt(
            rs.getLong("id"), rs.getString("order_ref"), rs.getInt("attempt_no"), rs.getString("outcome"),
            rs.getInt("latency_ms"), instant(rs, "created_at"));

    private final JdbcTemplate jdbc;

    public PaymentRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<Payment> findByOrderRef(String orderRef) {
        return jdbc.query("SELECT * FROM payments WHERE order_ref = ?", PAYMENT, orderRef).stream().findFirst();
    }

    public List<PaymentAttempt> attemptsFor(String orderRef) {
        return jdbc.query("SELECT * FROM payment_attempts WHERE order_ref = ? ORDER BY attempt_no", ATTEMPT, orderRef);
    }

    public int nextAttemptNo(String orderRef) {
        Integer n = jdbc.queryForObject("SELECT COALESCE(MAX(attempt_no), 0) + 1 FROM payment_attempts WHERE order_ref = ?",
                Integer.class, orderRef);
        return n == null ? 1 : n;
    }

    public void insertAttempt(String orderRef, int attemptNo, String outcome, int latencyMs, Instant at) {
        jdbc.update("INSERT INTO payment_attempts (order_ref, attempt_no, outcome, latency_ms, created_at) VALUES (?, ?, ?, ?, ?)",
                orderRef, attemptNo, outcome, latencyMs, at.atOffset(java.time.ZoneOffset.UTC));
    }

    public void insertPayment(String orderRef, String holdRef, long amountCents, String currency, PaymentStatus status,
                              String gatewayRef, String cardLast4, Instant at) {
        jdbc.update("""
                INSERT INTO payments (order_ref, hold_ref, amount_cents, currency, status, gateway_ref, card_last4, provider, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'SYNTH', ?)""",
                orderRef, holdRef, amountCents, currency, status.name(), gatewayRef, cardLast4, at.atOffset(java.time.ZoneOffset.UTC));
    }

    public void incrementDuplicateDeliveries(String orderRef) {
        jdbc.update("UPDATE payments SET duplicate_deliveries = duplicate_deliveries + 1 WHERE order_ref = ?", orderRef);
    }

    public PaymentStats stats() {
        return jdbc.queryForObject("""
                SELECT
                  (SELECT COUNT(*) FROM payments WHERE status = 'CAPTURED') AS captured,
                  (SELECT COALESCE(SUM(amount_cents), 0) FROM payments WHERE status = 'CAPTURED') AS captured_cents,
                  (SELECT COUNT(*) FROM payments WHERE status = 'DECLINED') AS declined,
                  (SELECT COUNT(*) FROM payments WHERE status = 'TIMEOUT') AS timeout,
                  (SELECT COUNT(*) FROM payments WHERE status = 'EXPIRED') AS expired,
                  (SELECT COUNT(*) FROM payment_attempts) AS attempts,
                  (SELECT COALESCE(SUM(duplicate_deliveries), 0) FROM payments) AS duplicates
                """, (rs, i) -> new PaymentStats(rs.getLong("captured"), rs.getLong("captured_cents"), rs.getLong("declined"),
                rs.getLong("timeout"), rs.getLong("expired"), rs.getLong("attempts"), rs.getLong("duplicates")));
    }

    private static Instant instant(ResultSet rs, String column) throws SQLException {
        OffsetDateTime t = rs.getObject(column, OffsetDateTime.class);
        return t == null ? null : t.toInstant();
    }
}
