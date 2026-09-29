package com.boxoffice.payments.domain;

/** payments.status. CAPTURED/DECLINED/TIMEOUT are the monolith's; EXPIRED is the hold-lapsed case. */
public enum PaymentStatus {
    CAPTURED("APPROVED", null, null),
    DECLINED("DECLINED", "DECLINED", "PAYMENT_FAILED"),
    TIMEOUT("TIMEOUT", "TIMEOUT", "PAYMENT_TIMEOUT"),
    EXPIRED("HOLD_EXPIRED", "HOLD_EXPIRED", "CANCELLED");

    private final String attemptOutcome;
    private final String failureOutcome;
    private final String orderStatus;

    PaymentStatus(String attemptOutcome, String failureOutcome, String orderStatus) {
        this.attemptOutcome = attemptOutcome;
        this.failureOutcome = failureOutcome;
        this.orderStatus = orderStatus;
    }

    /** payment_attempts.outcome as the monolith records it (APPROVED / DECLINED / TIMEOUT). */
    public String attemptOutcome() {
        return attemptOutcome;
    }

    /** payment-failed.outcome, null when the payment was captured. */
    public String failureOutcome() {
        return failureOutcome;
    }

    /** payment-failed.orderStatus, null when the payment was captured. */
    public String orderStatus() {
        return orderStatus;
    }

    public boolean captured() {
        return this == CAPTURED;
    }
}
