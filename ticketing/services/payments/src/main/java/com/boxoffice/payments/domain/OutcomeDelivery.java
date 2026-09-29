package com.boxoffice.payments.domain;

import java.time.Instant;

/** One pending HTTP inbox POST from the outcome_deliveries outbox. */
public record OutcomeDelivery(long id, String orderRef, DeliveryTarget target, String event, String payload, int attempts,
                              Instant nextAttemptAt, Instant deliveredAt, Instant givenUpAt, Instant createdAt) {

    public boolean pending() {
        return deliveredAt == null && givenUpAt == null;
    }
}
