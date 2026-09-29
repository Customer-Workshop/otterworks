package com.boxoffice.fulfillment;

import com.boxoffice.common.AuditLog;
import com.boxoffice.common.Db;
import com.boxoffice.common.Money;
import com.boxoffice.common.Refs;
import jakarta.ejb.Stateless;
import java.util.List;
import java.util.Map;

/**
 * Issues tickets for a paid order, marks the seats SOLD, converts the hold, confirms the order
 * and queues the confirmation email. All in the caller's transaction.
 */
@Stateless
public class ConfirmationBean {

    public int confirm(long orderId) {
        Map<String, Object> o = Db.one("""
                SELECT o.order_ref, o.hold_id, o.total_cents, c.email, c.full_name, e.title, p.starts_at, v.name AS venue
                FROM orders o
                JOIN customers c ON c.id = o.customer_id
                JOIN performances p ON p.id = o.performance_id
                JOIN events e ON e.id = p.event_id
                JOIN venues v ON v.id = p.venue_id
                WHERE o.id = ?""", orderId);
        List<Map<String, Object>> items = Db.query("SELECT seat_inventory_id FROM order_items WHERE order_id = ?", orderId);
        for (Map<String, Object> item : items) {
            long siId = ((Number) item.get("seat_inventory_id")).longValue();
            String code = Refs.next("TK");
            Db.update("INSERT INTO tickets (ticket_code, order_id, seat_inventory_id, barcode) VALUES (?, ?, ?, ?)",
                    code, orderId, siId, Integer.toHexString((code + orderId).hashCode()) + "-" + siId);
            Db.update("UPDATE seat_inventory SET status = 'SOLD', updated_at = now() WHERE id = ?", siId);
        }
        Db.update("UPDATE seat_holds SET status = 'CONVERTED' WHERE id = ?", o.get("hold_id"));
        Db.update("UPDATE orders SET status = 'CONFIRMED', updated_at = now() WHERE id = ?", orderId);
        Db.update("""
                INSERT INTO confirmations (order_id, recipient, subject, body) VALUES (?, ?, ?, ?)""",
                orderId, o.get("email"), "Your tickets for " + o.get("title"),
                "Order " + o.get("order_ref") + ": " + items.size() + " ticket(s) for " + o.get("title") + " at "
                        + o.get("venue") + " on " + o.get("starts_at") + ". Total " + Money.format(o.get("total_cents")) + ".");
        AuditLog.record("fulfillment", "ORDER_CONFIRMED", (String) o.get("order_ref"), items.size() + " tickets");
        return items.size();
    }

    public List<Map<String, Object>> pendingEmails(int limit) {
        return Db.query("SELECT * FROM confirmations WHERE sent_at IS NULL ORDER BY created_at LIMIT ?", limit);
    }
}
