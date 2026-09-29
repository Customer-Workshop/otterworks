package com.boxoffice.settlement;

import com.boxoffice.common.AuditLog;
import com.boxoffice.common.Db;
import com.boxoffice.common.Money;
import jakarta.ejb.Schedule;
import jakarta.ejb.Stateless;
import java.sql.Date;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.logging.Logger;

/**
 * Nightly promoter settlement. Aggregates yesterday's confirmed orders and refunds per promoter
 * straight from the sales, payment and catalog tables, then writes settlement batches and lines.
 */
@Stateless
public class SettlementBean {

    private static final Logger LOG = Logger.getLogger(SettlementBean.class.getName());

    @Schedule(hour = "2", minute = "15", persistent = false, info = "nightly-settlement")
    public void nightly() {
        List<String> r = run(LocalDate.now().minusDays(1));
        LOG.info("nightly settlement: " + r);
    }

    public List<String> run(LocalDate businessDate) {
        Date day = Date.valueOf(businessDate);
        List<String> summary = new ArrayList<>();
        List<Map<String, Object>> promoters = Db.query("SELECT id, code, commission_bp FROM promoters ORDER BY id");
        for (Map<String, Object> pr : promoters) {
            long promoterId = ((Number) pr.get("id")).longValue();
            int commissionBp = ((Number) pr.get("commission_bp")).intValue();
            Map<String, Object> totals = Db.one("""
                    SELECT COUNT(DISTINCT o.id) AS orders, COALESCE(SUM(o.subtotal_cents), 0) AS gross,
                           COALESCE(SUM(o.fees_cents), 0) AS fees
                    FROM orders o
                    JOIN payments pay ON pay.order_id = o.id AND pay.status IN ('CAPTURED', 'REFUNDED')
                    JOIN performances p ON p.id = o.performance_id
                    JOIN events e ON e.id = p.event_id
                    WHERE e.promoter_id = ? AND o.status IN ('CONFIRMED', 'REFUNDED')
                      AND CAST(o.created_at AS DATE) = ?""", promoterId, day);
            long refunds = Db.scalarLong("""
                    SELECT COALESCE(SUM(r.amount_cents), 0) FROM refunds r
                    JOIN payments pay ON pay.id = r.payment_id
                    JOIN orders o ON o.id = pay.order_id
                    JOIN performances p ON p.id = o.performance_id
                    JOIN events e ON e.id = p.event_id
                    WHERE e.promoter_id = ? AND CAST(r.created_at AS DATE) = ?""", promoterId, day);
            long gross = ((Number) totals.get("gross")).longValue();
            long fees = ((Number) totals.get("fees")).longValue();
            long commission = Money.percentOf(gross, commissionBp);
            long net = gross - commission - refunds;
            int orderCount = ((Number) totals.get("orders")).intValue();

            Db.update("DELETE FROM settlement_lines WHERE batch_id IN (SELECT id FROM settlement_batches WHERE business_date = ? AND promoter_id = ?)",
                    day, promoterId);
            Db.update("DELETE FROM settlement_batches WHERE business_date = ? AND promoter_id = ?", day, promoterId);
            long batchId = Db.insert("""
                    INSERT INTO settlement_batches (business_date, promoter_id, gross_cents, fees_cents, refunds_cents,
                                                    net_payout_cents, order_count, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'CLOSED')""", day, promoterId, gross, fees, refunds, net, orderCount);
            Db.update("""
                    INSERT INTO settlement_lines (batch_id, performance_id, tickets_sold, gross_cents, house_commission_cents)
                    SELECT ?, o.performance_id, COUNT(t.id), SUM(oi.price_cents), SUM(oi.price_cents) * ? / 10000
                    FROM orders o
                    JOIN order_items oi ON oi.order_id = o.id
                    LEFT JOIN tickets t ON t.order_id = o.id AND t.seat_inventory_id = oi.seat_inventory_id
                    JOIN performances p ON p.id = o.performance_id
                    JOIN events e ON e.id = p.event_id
                    WHERE e.promoter_id = ? AND o.status = 'CONFIRMED' AND CAST(o.created_at AS DATE) = ?
                    GROUP BY o.performance_id""", batchId, commissionBp, promoterId, day);
            summary.add(pr.get("code") + ": orders=" + orderCount + " gross=" + Money.format(gross) + " net=" + Money.format(net));
        }
        AuditLog.record("settlement", "SETTLEMENT_RUN", businessDate.toString(), String.join("; ", summary));
        return summary;
    }

    public List<Map<String, Object>> batches(int limit) {
        return Db.query("""
                SELECT b.*, pr.name AS promoter_name FROM settlement_batches b
                JOIN promoters pr ON pr.id = b.promoter_id
                ORDER BY b.business_date DESC, pr.name LIMIT ?""", limit);
    }
}
