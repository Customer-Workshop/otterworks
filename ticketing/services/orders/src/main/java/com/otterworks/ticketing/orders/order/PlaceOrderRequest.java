package com.otterworks.ticketing.orders.order;

/** Normalised placement command shared by /api/purchase (fresh hold) and /api/orders (existing hold). */
public record PlaceOrderRequest(Long performanceId, String holdRef, String email, int quantity, String section,
                                String promoCode, String delivery, String cardLast4, String clientRef,
                                String channel) {

    public static final int DEFAULT_QUANTITY = 2;
    public static final String DEFAULT_DELIVERY = "MOBILE";
    public static final String DEFAULT_CARD_LAST4 = "4242";

    public String normalisedEmail() {
        return email.trim().toLowerCase();
    }

    public String deliveryOrDefault() {
        return delivery == null || delivery.isBlank() ? DEFAULT_DELIVERY : delivery;
    }

    public String cardLast4OrDefault() {
        return cardLast4 == null || cardLast4.isBlank() ? DEFAULT_CARD_LAST4 : cardLast4;
    }

    public String clientRefOrNull() {
        return clientRef == null || clientRef.isBlank() ? null : clientRef.trim();
    }
}
