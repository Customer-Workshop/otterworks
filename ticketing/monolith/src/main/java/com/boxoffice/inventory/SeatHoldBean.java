package com.boxoffice.inventory;

import com.boxoffice.common.AuditLog;
import com.boxoffice.common.BoxOfficeException;
import com.boxoffice.common.Config;
import com.boxoffice.common.Db;
import com.boxoffice.common.Refs;
import jakarta.ejb.Stateless;
import java.sql.Timestamp;
import java.util.List;
import java.util.Map;

/**
 * Best-available seat holds. A hold locks seat_inventory rows for HOLD_MINUTES;
 * HoldExpiryBean returns them to AVAILABLE if the order never completes.
 */
@Stateless
public class SeatHoldBean {

    public long hold(long performanceId, Long customerId, int quantity, String sectionCode) {
        Map<String, Object> perf = Db.one("SELECT max_per_order, status FROM performances WHERE id = ?", performanceId);
        if (perf == null) {
            throw new BoxOfficeException("NOT_FOUND", "performance " + performanceId + " not found");
        }
        int max = ((Number) perf.get("max_per_order")).intValue();
        if (quantity < 1 || quantity > max) {
            throw new BoxOfficeException("BAD_QUANTITY", "quantity must be 1.." + max);
        }
        String sql = """
                SELECT si.id FROM seat_inventory si
                JOIN seats s ON s.id = si.seat_id
                JOIN venue_sections vs ON vs.id = s.section_id
                WHERE si.performance_id = ? AND si.status = 'AVAILABLE'
                """ + (sectionCode == null ? "" : " AND vs.code = ? ") + """
                ORDER BY vs.code, s.row_label, s.seat_number
                LIMIT ? FOR UPDATE OF si SKIP LOCKED""";
        List<Map<String, Object>> seats = sectionCode == null
                ? Db.query(sql, performanceId, quantity)
                : Db.query(sql, performanceId, sectionCode, quantity);
        if (seats.size() < quantity) {
            throw new BoxOfficeException("SOLD_OUT", "not enough seats available");
        }
        Timestamp expires = new Timestamp(System.currentTimeMillis() + Config.holdMinutes() * 60_000L);
        String ref = Refs.next("H");
        long holdId = Db.insert("""
                INSERT INTO seat_holds (hold_ref, performance_id, customer_id, status, expires_at)
                VALUES (?, ?, ?, 'ACTIVE', ?)""", ref, performanceId, customerId, expires);
        for (Map<String, Object> seat : seats) {
            long siId = ((Number) seat.get("id")).longValue();
            Db.update("UPDATE seat_inventory SET status = 'HELD', hold_id = ?, updated_at = now() WHERE id = ?",
                    holdId, siId);
            Db.update("INSERT INTO seat_hold_items (hold_id, seat_inventory_id) VALUES (?, ?)", holdId, siId);
        }
        AuditLog.record("inventory", "HOLD_CREATED", ref, quantity + " seats perf:" + performanceId);
        return holdId;
    }

    public Map<String, Object> hold(long holdId) {
        return Db.one("SELECT * FROM seat_holds WHERE id = ?", holdId);
    }

    public List<Map<String, Object>> items(long holdId) {
        return Db.query("""
                SELECT si.id AS seat_inventory_id, vs.code AS section, s.row_label, s.seat_number,
                       s.price_zone_id, pz.code AS zone
                FROM seat_hold_items hi
                JOIN seat_inventory si ON si.id = hi.seat_inventory_id
                JOIN seats s ON s.id = si.seat_id
                JOIN venue_sections vs ON vs.id = s.section_id
                JOIN price_zones pz ON pz.id = s.price_zone_id
                WHERE hi.hold_id = ? ORDER BY vs.code, s.row_label, s.seat_number""", holdId);
    }

    public boolean isActive(long holdId) {
        Map<String, Object> h = hold(holdId);
        return h != null && "ACTIVE".equals(h.get("status"))
                && ((Timestamp) h.get("expires_at")).after(Db.now());
    }

    public void release(long holdId, String newStatus) {
        Db.update("""
                UPDATE seat_inventory SET status = 'AVAILABLE', hold_id = NULL, order_id = NULL, updated_at = now()
                WHERE hold_id = ? AND status = 'HELD'""", holdId);
        Db.update("UPDATE seat_holds SET status = ? WHERE id = ?", newStatus, holdId);
        AuditLog.record("inventory", "HOLD_" + newStatus, "hold:" + holdId, null);
    }

    public void convert(long holdId) {
        Db.update("UPDATE seat_holds SET status = 'CONVERTED' WHERE id = ?", holdId);
    }
}
