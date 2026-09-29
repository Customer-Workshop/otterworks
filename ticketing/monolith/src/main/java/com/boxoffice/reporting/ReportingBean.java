package com.boxoffice.reporting;

import com.boxoffice.common.Db;
import jakarta.ejb.Stateless;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Back-office reports. Reads across sales, payment, fulfillment and inventory tables. */
@Stateless
public class ReportingBean {

    public List<Map<String, Object>> salesByPerformance() {
        return Db.query("""
                SELECT e.title, p.id AS performance_id, p.starts_at, v.name AS venue_name,
                       COUNT(DISTINCT o.id) FILTER (WHERE o.status = 'CONFIRMED') AS confirmed_orders,
                       COUNT(t.id) AS tickets, COALESCE(SUM(pay.amount_cents) FILTER (WHERE pay.status = 'CAPTURED'), 0) AS captured_cents
                FROM performances p
                JOIN events e ON e.id = p.event_id
                JOIN venues v ON v.id = p.venue_id
                LEFT JOIN orders o ON o.performance_id = p.id
                LEFT JOIN payments pay ON pay.order_id = o.id
                LEFT JOIN tickets t ON t.order_id = o.id
                GROUP BY e.title, p.id, p.starts_at, v.name
                ORDER BY confirmed_orders DESC, p.starts_at LIMIT 50""");
    }

    public List<Map<String, Object>> dailyTotals() {
        return Db.query("""
                SELECT CAST(o.created_at AS DATE) AS day, COUNT(*) AS orders,
                       COUNT(*) FILTER (WHERE o.status = 'CONFIRMED') AS confirmed,
                       COALESCE(SUM(o.total_cents) FILTER (WHERE o.status = 'CONFIRMED'), 0) AS revenue_cents
                FROM orders o GROUP BY CAST(o.created_at AS DATE) ORDER BY day DESC LIMIT 14""");
    }

    /** Reconciliation counters: orders by status, captured payments, issued tickets, queued emails. */
    public Map<String, Object> stats() {
        Map<String, Object> out = new LinkedHashMap<>();
        Map<String, Object> byStatus = new LinkedHashMap<>();
        for (Map<String, Object> r : Db.query("SELECT status, COUNT(*) AS n FROM orders GROUP BY status ORDER BY status")) {
            byStatus.put((String) r.get("status"), r.get("n"));
        }
        out.put("ordersTotal", Db.scalarLong("SELECT COUNT(*) FROM orders"));
        out.put("ordersByStatus", byStatus);
        out.put("paymentsCaptured", Db.scalarLong("SELECT COUNT(*) FROM payments WHERE status = 'CAPTURED'"));
        out.put("capturedCents", Db.scalarLong("SELECT COALESCE(SUM(amount_cents), 0) FROM payments WHERE status = 'CAPTURED'"));
        out.put("ticketsIssued", Db.scalarLong("SELECT COUNT(*) FROM tickets"));
        out.put("confirmationsQueued", Db.scalarLong("SELECT COUNT(*) FROM confirmations"));
        out.put("seatsSold", Db.scalarLong("SELECT COUNT(*) FROM seat_inventory WHERE status = 'SOLD'"));
        out.put("seatsHeld", Db.scalarLong("SELECT COUNT(*) FROM seat_inventory WHERE status = 'HELD'"));
        return out;
    }
}
