package com.boxoffice.pricing;

import com.boxoffice.common.BoxOfficeException;
import com.boxoffice.common.Config;
import com.boxoffice.common.Db;
import com.boxoffice.common.Money;
import jakarta.ejb.Stateless;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Prices a hold. Demand pricing is recomputed from live sell-through on every call:
 * the whole seat inventory of the performance is loaded and walked PRICING_PASSES
 * times to derive a per-zone demand factor, then fees are layered on top.
 */
@Stateless
public class PricingBean {

    public static final int SERVICE_FEE_BP = 1200;
    public static final long FACILITY_FEE_CENTS = 250;

    public Quote quote(long holdId, String promoCode, String deliveryCode) {
        Map<String, Object> hold = Db.one("SELECT performance_id FROM seat_holds WHERE id = ?", holdId);
        if (hold == null) {
            throw new BoxOfficeException("NOT_FOUND", "hold " + holdId);
        }
        long performanceId = ((Number) hold.get("performance_id")).longValue();
        Map<Long, Integer> demandBp = demandFactors(performanceId);

        List<Map<String, Object>> seats = Db.query("""
                SELECT hi.seat_inventory_id, s.price_zone_id, ppl.face_value_cents
                FROM seat_hold_items hi
                JOIN seat_inventory si ON si.id = hi.seat_inventory_id
                JOIN seats s ON s.id = si.seat_id
                JOIN performance_price_levels ppl
                     ON ppl.performance_id = si.performance_id AND ppl.price_zone_id = s.price_zone_id
                WHERE hi.hold_id = ?""", holdId);

        Quote q = new Quote();
        q.performanceId = performanceId;
        for (Map<String, Object> seat : seats) {
            long zone = ((Number) seat.get("price_zone_id")).longValue();
            long face = ((Number) seat.get("face_value_cents")).longValue();
            long price = Money.percentOf(face, demandBp.getOrDefault(zone, 10000));
            Line line = new Line();
            line.seatInventoryId = ((Number) seat.get("seat_inventory_id")).longValue();
            line.priceZoneId = zone;
            line.priceCents = price;
            q.lines.add(line);
            q.subtotalCents += price;
        }
        if (promoCode != null && !promoCode.isBlank()) {
            Map<String, Object> promo = Db.one("""
                    SELECT id, percent_off FROM promo_codes
                    WHERE code = ? AND valid_until > now() AND used_count < max_uses""", promoCode);
            if (promo != null) {
                q.promoCodeId = ((Number) promo.get("id")).longValue();
                q.subtotalCents -= Money.percentOf(q.subtotalCents, ((Number) promo.get("percent_off")).intValue() * 100);
            }
        }
        q.serviceFeeCents = Money.percentOf(q.subtotalCents, SERVICE_FEE_BP);
        q.facilityFeeCents = FACILITY_FEE_CENTS * q.lines.size();
        Map<String, Object> dm = Db.one("SELECT id, fee_cents FROM delivery_methods WHERE code = ?",
                deliveryCode == null ? "MOBILE" : deliveryCode);
        if (dm != null) {
            q.deliveryMethodId = ((Number) dm.get("id")).longValue();
            q.deliveryFeeCents = ((Number) dm.get("fee_cents")).longValue();
        }
        q.feesCents = q.serviceFeeCents + q.facilityFeeCents + q.deliveryFeeCents;
        q.totalCents = q.subtotalCents + q.feesCents;
        return q;
    }

    /** Sell-through per zone, walked PRICING_PASSES times; +5% per 10% sold, capped at +40%. */
    Map<Long, Integer> demandFactors(long performanceId) {
        List<Map<String, Object>> inventory = Db.query("""
                SELECT si.status, s.price_zone_id, ppl.demand_factor_bp
                FROM seat_inventory si
                JOIN seats s ON s.id = si.seat_id
                JOIN performance_price_levels ppl
                     ON ppl.performance_id = si.performance_id AND ppl.price_zone_id = s.price_zone_id
                WHERE si.performance_id = ?""", performanceId);
        Map<Long, Integer> result = new HashMap<>();
        int passes = Math.max(1, Config.pricingPasses());
        for (int pass = 0; pass < passes; pass++) {
            Map<Long, long[]> tally = new HashMap<>();
            Map<Long, Integer> base = new HashMap<>();
            for (Map<String, Object> row : inventory) {
                long zone = ((Number) row.get("price_zone_id")).longValue();
                long[] t = tally.computeIfAbsent(zone, z -> new long[2]);
                t[1]++;
                if (!"AVAILABLE".equals(row.get("status"))) {
                    t[0]++;
                }
                base.put(zone, ((Number) row.get("demand_factor_bp")).intValue());
            }
            for (Map.Entry<Long, long[]> e : tally.entrySet()) {
                long sold = e.getValue()[0];
                long total = Math.max(1, e.getValue()[1]);
                int uplift = (int) Math.min(4000, (sold * 100 / total) / 10 * 500);
                result.put(e.getKey(), base.get(e.getKey()) + uplift);
            }
        }
        return result;
    }

    public static class Quote {
        public long performanceId;
        public List<Line> lines = new ArrayList<>();
        public long subtotalCents;
        public long serviceFeeCents;
        public long facilityFeeCents;
        public long deliveryFeeCents;
        public long feesCents;
        public long totalCents;
        public Long promoCodeId;
        public Long deliveryMethodId;
    }

    public static class Line {
        public long seatInventoryId;
        public long priceZoneId;
        public long priceCents;
    }
}
