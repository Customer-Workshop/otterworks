package com.boxoffice.payments.events;

import java.time.Instant;
import java.util.List;

/** Payload of {@code <token>-payment-captured}; also POSTed to confirmations {@code /events/payment-captured}. */
public record PaymentCaptured(
        String orderRef,
        String gatewayRef,
        long amountCents,
        String currency,
        String cardLast4,
        int attemptNo,
        int latencyMs,
        Instant capturedAt,
        Order order) {

    public record Order(String customerEmail, Long performanceId, String eventTitle, String venueName, String startsAt,
                        String holdRef, long totalCents, List<Item> items) {
    }

    public record Item(Long seatInventoryId, String section, String rowLabel, Integer seatNumber, String zoneCode) {
    }

    public static PaymentCaptured from(OrderPlaced placed, String gatewayRef, int attemptNo, int latencyMs, Instant capturedAt) {
        List<Item> items = placed.itemsOrEmpty().stream()
                .map(i -> new Item(i.seatInventoryId(), i.section(), i.rowLabel(), i.seatNumber(), i.zoneCode()))
                .toList();
        Order order = new Order(placed.customerEmail(), placed.performanceId(), placed.eventTitle(), placed.venueName(),
                placed.startsAt(), placed.holdRef(), placed.totalCents(), items);
        return new PaymentCaptured(placed.orderRef(), gatewayRef, placed.totalCents(), placed.currencyOrDefault(),
                placed.cardLast4(), attemptNo, latencyMs, capturedAt, order);
    }
}
