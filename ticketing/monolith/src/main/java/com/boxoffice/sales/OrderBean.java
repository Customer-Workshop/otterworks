package com.boxoffice.sales;

import com.boxoffice.common.AuditLog;
import com.boxoffice.common.Db;
import com.boxoffice.common.Refs;
import com.boxoffice.pricing.PricingBean;
import jakarta.ejb.Stateless;
import java.util.List;
import java.util.Map;

/** Order placement and lookup. Writes orders, order_items, order_fees and stamps seat_inventory. */
@Stateless
public class OrderBean {

    public long place(long customerId, long holdId, PricingBean.Quote q, String channel) {
        String ref = Refs.next("BO");
        long orderId = Db.insert("""
                INSERT INTO orders (order_ref, customer_id, performance_id, hold_id, delivery_method_id, promo_code_id,
                                    status, subtotal_cents, fees_cents, total_cents, channel)
                VALUES (?, ?, ?, ?, ?, ?, 'PENDING_PAYMENT', ?, ?, ?, ?)""",
                ref, customerId, q.performanceId, holdId, q.deliveryMethodId, q.promoCodeId,
                q.subtotalCents, q.feesCents, q.totalCents, channel);
        for (PricingBean.Line line : q.lines) {
            Db.update("INSERT INTO order_items (order_id, seat_inventory_id, price_zone_id, price_cents) VALUES (?, ?, ?, ?)",
                    orderId, line.seatInventoryId, line.priceZoneId, line.priceCents);
            Db.update("UPDATE seat_inventory SET order_id = ?, updated_at = now() WHERE id = ?", orderId, line.seatInventoryId);
        }
        Db.update("INSERT INTO order_fees (order_id, fee_type, amount_cents) VALUES (?, 'SERVICE', ?)", orderId, q.serviceFeeCents);
        Db.update("INSERT INTO order_fees (order_id, fee_type, amount_cents) VALUES (?, 'FACILITY', ?)", orderId, q.facilityFeeCents);
        if (q.deliveryFeeCents > 0) {
            Db.update("INSERT INTO order_fees (order_id, fee_type, amount_cents) VALUES (?, 'DELIVERY', ?)", orderId, q.deliveryFeeCents);
        }
        if (q.promoCodeId != null) {
            Db.update("UPDATE promo_codes SET used_count = used_count + 1 WHERE id = ?", q.promoCodeId);
        }
        AuditLog.record("sales", "ORDER_PLACED", ref, "total=" + q.totalCents);
        return orderId;
    }

    public void setStatus(long orderId, String status) {
        Db.update("UPDATE orders SET status = ?, updated_at = now() WHERE id = ?", status, orderId);
    }

    public Map<String, Object> byId(long orderId) {
        return Db.one("SELECT * FROM orders WHERE id = ?", orderId);
    }

    public Map<String, Object> byRef(String ref) {
        return Db.one("""
                SELECT o.*, c.email, e.title AS event_title, p.starts_at, v.name AS venue_name
                FROM orders o
                JOIN customers c ON c.id = o.customer_id
                JOIN performances p ON p.id = o.performance_id
                JOIN events e ON e.id = p.event_id
                JOIN venues v ON v.id = p.venue_id
                WHERE o.order_ref = ?""", ref);
    }

    public List<Map<String, Object>> items(long orderId) {
        return Db.query("""
                SELECT oi.price_cents, vs.code AS section, s.row_label, s.seat_number, pz.name AS zone, t.ticket_code
                FROM order_items oi
                JOIN seat_inventory si ON si.id = oi.seat_inventory_id
                JOIN seats s ON s.id = si.seat_id
                JOIN venue_sections vs ON vs.id = s.section_id
                JOIN price_zones pz ON pz.id = oi.price_zone_id
                LEFT JOIN tickets t ON t.seat_inventory_id = si.id AND t.order_id = oi.order_id
                WHERE oi.order_id = ? ORDER BY vs.code, s.row_label, s.seat_number""", orderId);
    }

    public List<Map<String, Object>> fees(long orderId) {
        return Db.query("SELECT fee_type, amount_cents FROM order_fees WHERE order_id = ?", orderId);
    }

    public List<Map<String, Object>> recent(int limit) {
        return Db.query("""
                SELECT o.order_ref, o.status, o.total_cents, o.channel, o.created_at, e.title AS event_title
                FROM orders o JOIN performances p ON p.id = o.performance_id JOIN events e ON e.id = p.event_id
                ORDER BY o.created_at DESC LIMIT ?""", limit);
    }
}
