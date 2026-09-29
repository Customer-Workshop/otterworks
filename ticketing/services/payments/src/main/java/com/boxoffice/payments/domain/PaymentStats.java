package com.boxoffice.payments.domain;

/** {@code GET /stats}: the reconciliation counters this service owns. */
public record PaymentStats(
        long paymentsCaptured,
        long capturedCents,
        long paymentsDeclined,
        long paymentsTimeout,
        long paymentsExpired,
        long attempts,
        long duplicatesSuppressed,
        long deliveriesPending,
        long deliveriesGivenUp) {
}
