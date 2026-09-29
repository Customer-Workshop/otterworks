package com.otterworks.ticketing.orders.pricing;

import com.otterworks.ticketing.orders.api.OrdersException;
import com.otterworks.ticketing.orders.seats.SeatsClient.HeldSeat;
import com.otterworks.ticketing.orders.seats.SeatsClient.Hold;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;

/**
 * Prices a hold the way the monolith's PricingBean does, but from the seats service's zone tally
 * instead of a local seat_inventory scan: line = face × (demand_factor_bp + uplift) / 10000 HALF_UP,
 * promo (if valid and not exhausted) off the subtotal, then 12% service fee, 250c facility fee per
 * seat and the delivery method's fee.
 */
@Service
public class PricingService {

    public static final int SERVICE_FEE_BP = 1200;
    public static final long FACILITY_FEE_CENTS = 250;
    public static final String DEFAULT_DELIVERY = "MOBILE";

    private final JdbcClient jdbc;

    public PricingService(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public Quote quote(long performanceId, Hold hold, String promoCode, String deliveryCode) {
        Map<Long, PriceLevel> levels = new HashMap<>();
        jdbc.sql("SELECT price_zone_id, face_value_cents, demand_factor_bp FROM performance_price_levels WHERE performance_id = :p")
                .param("p", performanceId)
                .query((rs, i) -> new PriceLevel(rs.getLong(1), rs.getLong(2), rs.getInt(3)))
                .list().forEach(l -> levels.put(l.priceZoneId(), l));

        Map<Long, Integer> uplift = new HashMap<>();
        hold.zoneTally().forEach(t -> uplift.put(t.priceZoneId(), DemandPricing.upliftBp(t.notAvailable(), t.total())));

        List<Quote.Line> lines = new ArrayList<>();
        long subtotal = 0;
        for (HeldSeat seat : hold.seats()) {
            PriceLevel level = levels.get(seat.priceZoneId());
            if (level == null) {
                throw new OrdersException("PRICE_LEVEL_MISSING",
                        "no price level for performance " + performanceId + " zone " + seat.priceZoneId());
            }
            long price = DemandPricing.linePrice(level.faceValueCents(), level.demandFactorBp(),
                    uplift.getOrDefault(seat.priceZoneId(), 0));
            lines.add(new Quote.Line(seat.seatInventoryId(), seat.priceZoneId(), seat.zoneCode(), seat.zoneName(),
                    seat.section(), seat.rowLabel(), seat.seatNumber(), price));
            subtotal += price;
        }

        Long promoId = null;
        String appliedPromo = null;
        if (promoCode != null && !promoCode.isBlank()) {
            Optional<Promo> promo = jdbc.sql("""
                            SELECT id, code, percent_off FROM promo_codes
                            WHERE code = :code AND valid_until > now() AND used_count < max_uses""")
                    .param("code", promoCode)
                    .query((rs, i) -> new Promo(rs.getLong(1), rs.getString(2), rs.getInt(3)))
                    .optional();
            if (promo.isPresent()) {
                promoId = promo.get().id();
                appliedPromo = promo.get().code();
                subtotal -= Money.percentOf(subtotal, promo.get().percentOff() * 100);
            }
        }

        long serviceFee = Money.percentOf(subtotal, SERVICE_FEE_BP);
        long facilityFee = FACILITY_FEE_CENTS * lines.size();
        Long deliveryId = null;
        long deliveryFee = 0;
        Optional<Delivery> delivery = jdbc.sql("SELECT id, fee_cents FROM delivery_methods WHERE code = :code")
                .param("code", deliveryCode == null ? DEFAULT_DELIVERY : deliveryCode)
                .query((rs, i) -> new Delivery(rs.getLong(1), rs.getLong(2)))
                .optional();
        if (delivery.isPresent()) {
            deliveryId = delivery.get().id();
            deliveryFee = delivery.get().feeCents();
        }
        long fees = serviceFee + facilityFee + deliveryFee;
        return new Quote(performanceId, lines, subtotal, serviceFee, facilityFee, deliveryFee, fees, subtotal + fees,
                promoId, appliedPromo, deliveryId);
    }

    record PriceLevel(long priceZoneId, long faceValueCents, int demandFactorBp) {
    }

    record Promo(long id, String code, int percentOff) {
    }

    record Delivery(long id, long feeCents) {
    }
}
