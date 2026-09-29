package com.otterworks.ticketing.orders.stats;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;

/** Reconciliation counts for this service's slice of the former monolith-wide /api/stats. */
@Service
public class StatsService {

    private final JdbcClient jdbc;

    public StatsService(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public Map<String, Object> stats() {
        Map<String, Long> byStatus = new TreeMap<>();
        jdbc.sql("SELECT status, count(*) FROM orders GROUP BY status")
                .query(rs -> {
                    byStatus.put(rs.getString(1), rs.getLong(2));
                });
        Map<String, Long> byOutcome = new TreeMap<>();
        jdbc.sql("SELECT payment_outcome, count(*) FROM orders GROUP BY payment_outcome")
                .query(rs -> {
                    byOutcome.put(rs.getString(1), rs.getLong(2));
                });
        long total = byStatus.values().stream().mapToLong(Long::longValue).sum();
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("ordersTotal", total);
        m.put("ordersByStatus", byStatus);
        m.put("ordersByPaymentOutcome", byOutcome);
        m.put("orderedCents", scalar("SELECT coalesce(sum(total_cents), 0) FROM orders"));
        m.put("confirmedCents", scalar("SELECT coalesce(sum(total_cents), 0) FROM orders WHERE status = 'CONFIRMED'"));
        m.put("seatsOrdered", scalar("SELECT count(*) FROM order_items"));
        m.put("ticketsStamped", scalar("SELECT count(*) FROM order_items WHERE ticket_code IS NOT NULL"));
        m.put("outboxUnpublished", scalar("SELECT count(*) FROM outbox WHERE published_at IS NULL"));
        m.put("outboxPublished", scalar("SELECT count(*) FROM outbox WHERE published_at IS NOT NULL"));
        m.put("promoUses", scalar("SELECT coalesce(sum(used_count), 0) FROM promo_codes"));
        return m;
    }

    private long scalar(String sql) {
        return jdbc.sql(sql).query(Long.class).single();
    }
}
