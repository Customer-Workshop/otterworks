package com.boxoffice.payments.events;

import java.time.Instant;

/**
 * Payload of {@code <token>-payment-failed}; also POSTed to orders and seats {@code /events/payment-failed}.
 * outcome DECLINED → orderStatus PAYMENT_FAILED, TIMEOUT → PAYMENT_TIMEOUT, HOLD_EXPIRED → CANCELLED
 * (the monolith's PaymentBean / HoldExpiryBean transitions).
 */
public record PaymentFailed(
        String orderRef,
        String holdRef,
        String outcome,
        String orderStatus,
        long amountCents,
        String cardLast4,
        int attemptNo,
        int latencyMs,
        String gatewayRef,
        Instant failedAt) {
}
