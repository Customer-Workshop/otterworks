package com.otterworks.ticketing.orders.order;

/** PENDING_PAYMENT → CONFIRMED | PAYMENT_FAILED | PAYMENT_TIMEOUT | CANCELLED; every other state is terminal. */
public enum OrderStatus {
    PENDING_PAYMENT, CONFIRMED, PAYMENT_FAILED, PAYMENT_TIMEOUT, CANCELLED;

    public boolean terminal() {
        return this != PENDING_PAYMENT;
    }

    /** Status implied by a payment-failed outcome when the event carries no orderStatus. */
    public static OrderStatus forFailureOutcome(String outcome) {
        return switch (outcome) {
            case "TIMEOUT" -> PAYMENT_TIMEOUT;
            case "HOLD_EXPIRED" -> CANCELLED;
            default -> PAYMENT_FAILED;
        };
    }
}
