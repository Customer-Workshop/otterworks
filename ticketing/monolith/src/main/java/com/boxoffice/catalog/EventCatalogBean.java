package com.boxoffice.catalog;

import com.boxoffice.common.AuditLog;
import com.boxoffice.common.Db;
import jakarta.ejb.Stateless;
import java.util.List;
import java.util.Map;

/** Events, performances and venues. Read by nearly every page. */
@Stateless
public class EventCatalogBean {

    public List<Map<String, Object>> onSaleEvents() {
        return Db.query("""
                SELECT e.id, e.code, e.title, e.category, pr.name AS promoter_name,
                       MIN(p.starts_at) AS first_show, COUNT(p.id) AS performance_count
                FROM events e
                JOIN promoters pr ON pr.id = e.promoter_id
                JOIN performances p ON p.event_id = e.id
                WHERE e.status = 'ON_SALE'
                GROUP BY e.id, e.code, e.title, e.category, pr.name
                ORDER BY MIN(p.starts_at)""");
    }

    public List<Map<String, Object>> search(String q) {
        return Db.query("""
                SELECT e.id, e.code, e.title, e.category
                FROM events e
                LEFT JOIN event_performers ep ON ep.event_id = e.id
                LEFT JOIN performers pf ON pf.id = ep.performer_id
                WHERE lower(e.title) LIKE ? OR lower(pf.name) LIKE ?
                GROUP BY e.id, e.code, e.title, e.category ORDER BY e.title""",
                "%" + q.toLowerCase() + "%", "%" + q.toLowerCase() + "%");
    }

    public Map<String, Object> event(long eventId) {
        return Db.one("""
                SELECT e.*, pr.name AS promoter_name FROM events e
                JOIN promoters pr ON pr.id = e.promoter_id WHERE e.id = ?""", eventId);
    }

    public List<Map<String, Object>> performers(long eventId) {
        return Db.query("""
                SELECT pf.name, pf.genre FROM event_performers ep
                JOIN performers pf ON pf.id = ep.performer_id
                WHERE ep.event_id = ? ORDER BY ep.billing_order""", eventId);
    }

    public List<Map<String, Object>> performances(long eventId) {
        return Db.query("""
                SELECT p.id, p.starts_at, p.doors_at, p.status, v.name AS venue_name, v.city,
                       (SELECT COUNT(*) FROM seat_inventory si
                         WHERE si.performance_id = p.id AND si.status = 'AVAILABLE') AS available
                FROM performances p JOIN venues v ON v.id = p.venue_id
                WHERE p.event_id = ? ORDER BY p.starts_at""", eventId);
    }

    public Map<String, Object> performance(long performanceId) {
        return Db.one("""
                SELECT p.*, e.title AS event_title, e.code AS event_code, e.promoter_id,
                       v.name AS venue_name, v.city, v.capacity
                FROM performances p
                JOIN events e ON e.id = p.event_id
                JOIN venues v ON v.id = p.venue_id
                WHERE p.id = ?""", performanceId);
    }

    public List<Map<String, Object>> venues() {
        return Db.query("SELECT * FROM venues ORDER BY name");
    }

    public List<Map<String, Object>> allPerformances() {
        return Db.query("""
                SELECT p.id, p.starts_at, p.status, e.title AS event_title, v.name AS venue_name
                FROM performances p JOIN events e ON e.id = p.event_id JOIN venues v ON v.id = p.venue_id
                ORDER BY p.starts_at""");
    }

    public void updatePerformance(long performanceId, String status, int maxPerOrder) {
        Db.update("UPDATE performances SET status = ?, max_per_order = ? WHERE id = ?",
                status, maxPerOrder, performanceId);
        AuditLog.record("catalog", "PERFORMANCE_UPDATED", "perf:" + performanceId, status);
    }
}
