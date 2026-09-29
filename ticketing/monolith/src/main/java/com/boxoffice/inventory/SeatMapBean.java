package com.boxoffice.inventory;

import com.boxoffice.common.Db;
import jakarta.ejb.Stateless;
import java.util.List;
import java.util.Map;

/** Seat map rendering data: sections, zones, prices and live availability. */
@Stateless
public class SeatMapBean {

    public List<Map<String, Object>> sections(long performanceId) {
        return Db.query("""
                SELECT vs.code, vs.name, pz.code AS zone, ppl.face_value_cents,
                       COUNT(*) FILTER (WHERE si.status = 'AVAILABLE') AS available,
                       COUNT(*) FILTER (WHERE si.status = 'HELD') AS held,
                       COUNT(*) FILTER (WHERE si.status = 'SOLD') AS sold,
                       COUNT(*) AS total
                FROM seat_inventory si
                JOIN seats s ON s.id = si.seat_id
                JOIN venue_sections vs ON vs.id = s.section_id
                JOIN price_zones pz ON pz.id = s.price_zone_id
                JOIN performance_price_levels ppl
                     ON ppl.performance_id = si.performance_id AND ppl.price_zone_id = pz.id
                WHERE si.performance_id = ?
                GROUP BY vs.code, vs.name, pz.code, ppl.face_value_cents
                ORDER BY vs.code, pz.code""", performanceId);
    }

    public long available(long performanceId) {
        return Db.scalarLong("SELECT COUNT(*) FROM seat_inventory WHERE performance_id = ? AND status = 'AVAILABLE'",
                performanceId);
    }

    public Map<String, Object> counts(long performanceId) {
        return Db.one("""
                SELECT COUNT(*) FILTER (WHERE status = 'AVAILABLE') AS available,
                       COUNT(*) FILTER (WHERE status = 'HELD') AS held,
                       COUNT(*) FILTER (WHERE status = 'SOLD') AS sold
                FROM seat_inventory WHERE performance_id = ?""", performanceId);
    }
}
