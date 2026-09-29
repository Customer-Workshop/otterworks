package com.boxoffice.customer;

import com.boxoffice.common.AuditLog;
import com.boxoffice.common.Db;
import jakarta.ejb.Stateless;
import java.util.List;
import java.util.Map;

@Stateless
public class CustomerAccountBean {

    public long findOrCreate(String email, String fullName) {
        Map<String, Object> c = Db.one("SELECT id FROM customers WHERE email = ?", email.toLowerCase());
        if (c != null) {
            return ((Number) c.get("id")).longValue();
        }
        long id = Db.insert("INSERT INTO customers (email, full_name) VALUES (?, ?)", email.toLowerCase(), fullName);
        AuditLog.record("customer", "CUSTOMER_CREATED", "cust:" + id, null);
        return id;
    }

    public Map<String, Object> byEmail(String email) {
        return Db.one("SELECT * FROM customers WHERE email = ?", email.toLowerCase());
    }

    public List<Map<String, Object>> orders(long customerId) {
        return Db.query("""
                SELECT o.order_ref, o.status, o.total_cents, o.created_at, e.title AS event_title,
                       p.starts_at, v.name AS venue_name,
                       (SELECT COUNT(*) FROM tickets t WHERE t.order_id = o.id) AS ticket_count
                FROM orders o
                JOIN performances p ON p.id = o.performance_id
                JOIN events e ON e.id = p.event_id
                JOIN venues v ON v.id = p.venue_id
                WHERE o.customer_id = ? ORDER BY o.created_at DESC""", customerId);
    }

    public List<Map<String, Object>> addresses(long customerId) {
        return Db.query("SELECT * FROM customer_addresses WHERE customer_id = ?", customerId);
    }
}
