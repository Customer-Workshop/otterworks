package com.boxoffice.payments.domain;

import java.time.Instant;

public record Payment(
        long id,
        String orderRef,
        String holdRef,
        long amountCents,
        String currency,
        PaymentStatus status,
        String gatewayRef,
        String cardLast4,
        String provider,
        int duplicateDeliveries,
        Instant createdAt) {
}
