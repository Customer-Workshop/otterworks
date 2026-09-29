package com.otterworks.ticketing.orders.pricing;

import java.util.List;

public record Quote(long performanceId, List<Line> lines, long subtotalCents, long serviceFeeCents,
                    long facilityFeeCents, long deliveryFeeCents, long feesCents, long totalCents,
                    Long promoCodeId, String promoCode, Long deliveryMethodId) {

    public record Line(long seatInventoryId, long priceZoneId, String zoneCode, String zoneName, String section,
                       String rowLabel, int seatNumber, long priceCents) {
    }

    public record Fee(String feeType, long amountCents) {
    }

    /** Fee rows exactly as the monolith writes them: SERVICE, FACILITY, DELIVERY (delivery only when &gt; 0). */
    public List<Fee> fees() {
        List<Fee> fees = new java.util.ArrayList<>(3);
        fees.add(new Fee("SERVICE", serviceFeeCents));
        fees.add(new Fee("FACILITY", facilityFeeCents));
        if (deliveryFeeCents > 0) {
            fees.add(new Fee("DELIVERY", deliveryFeeCents));
        }
        return fees;
    }
}
