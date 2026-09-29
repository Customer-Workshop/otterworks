package com.boxoffice.confirmations.events;

import java.util.List;

/** {@code <token>-order-confirmed} payload (key = orderRef); also POSTed to orders and seats {@code /events/order-confirmed}. */
public record OrderConfirmedEvent(
        String orderRef,
        String holdRef,
        long performanceId,
        int ticketCount,
        List<Ticket> tickets,
        String recipient,
        String confirmedAt) {

    public record Ticket(String ticketCode, long seatInventoryId, String barcode) {
    }
}
