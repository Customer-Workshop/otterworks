package com.boxoffice.confirmations.domain;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class FulfilmentRepository {

    private final JdbcClient jdbc;

    public FulfilmentRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<Confirmation> findConfirmation(String orderRef) {
        return jdbc.sql("""
                        SELECT order_ref, hold_ref, performance_id, channel, recipient, subject, body, status, sent_at, created_at
                        FROM confirmations WHERE order_ref = :ref""")
                .param("ref", orderRef)
                .query((rs, i) -> new Confirmation(rs.getString("order_ref"), rs.getString("hold_ref"),
                        rs.getLong("performance_id"), rs.getString("channel"), rs.getString("recipient"),
                        rs.getString("subject"), rs.getString("body"), rs.getString("status"),
                        toLocal(rs.getTimestamp("sent_at")), toLocal(rs.getTimestamp("created_at"))))
                .optional();
    }

    public List<Ticket> findTickets(String orderRef) {
        return jdbc.sql("""
                        SELECT ticket_code, order_ref, seat_inventory_id, barcode, issued_at
                        FROM tickets WHERE order_ref = :ref ORDER BY id""")
                .param("ref", orderRef)
                .query((rs, i) -> new Ticket(rs.getString("ticket_code"), rs.getString("order_ref"),
                        rs.getLong("seat_inventory_id"), rs.getString("barcode"), toLocal(rs.getTimestamp("issued_at"))))
                .list();
    }

    public void insertTicket(Ticket t) {
        jdbc.sql("""
                        INSERT INTO tickets (ticket_code, order_ref, seat_inventory_id, barcode, issued_at)
                        VALUES (:code, :ref, :seat, :barcode, :issuedAt)""")
                .param("code", t.ticketCode()).param("ref", t.orderRef()).param("seat", t.seatInventoryId())
                .param("barcode", t.barcode()).param("issuedAt", Timestamp.valueOf(t.issuedAt()))
                .update();
    }

    public void insertConfirmation(Confirmation c) {
        jdbc.sql("""
                        INSERT INTO confirmations (order_ref, hold_ref, performance_id, channel, recipient, subject, body, status, created_at)
                        VALUES (:ref, :hold, :perf, :channel, :recipient, :subject, :body, :status, :createdAt)""")
                .param("ref", c.orderRef()).param("hold", c.holdRef()).param("perf", c.performanceId())
                .param("channel", c.channel()).param("recipient", c.recipient()).param("subject", c.subject())
                .param("body", c.body()).param("status", c.status()).param("createdAt", Timestamp.valueOf(c.createdAt()))
                .update();
    }

    public long countTickets() {
        return jdbc.sql("SELECT COUNT(*) FROM tickets").query(Long.class).single();
    }

    public long countConfirmations() {
        return jdbc.sql("SELECT COUNT(*) FROM confirmations").query(Long.class).single();
    }

    public long countConfirmationsSent() {
        return jdbc.sql("SELECT COUNT(*) FROM confirmations WHERE sent_at IS NOT NULL").query(Long.class).single();
    }

    private static LocalDateTime toLocal(Timestamp ts) {
        return ts == null ? null : ts.toLocalDateTime();
    }
}
