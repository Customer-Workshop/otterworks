package com.boxoffice.payments.events;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.time.Instant;
import java.util.List;

/** Payload of {@code <token>-order-placed} (contract: decomposition.json, event order-placed). */
@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderPlaced(
        String orderRef,
        String clientRef,
        String customerEmail,
        Long performanceId,
        String eventTitle,
        String venueName,
        String startsAt,
        String holdRef,
        Instant holdExpiresAt,
        String channel,
        List<Item> items,
        List<Fee> fees,
        Long subtotalCents,
        Long feesCents,
        long totalCents,
        String currency,
        String cardLast4,
        Instant placedAt) {

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Item(Long seatInventoryId, Long priceZoneId, String zoneCode, String zoneName, String section,
                       String rowLabel, Integer seatNumber, Long priceCents) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Fee(String feeType, Long amountCents) {
    }

    public List<Item> itemsOrEmpty() {
        return items == null ? List.of() : items;
    }

    public String currencyOrDefault() {
        return currency == null || currency.isBlank() ? "USD" : currency;
    }
}
