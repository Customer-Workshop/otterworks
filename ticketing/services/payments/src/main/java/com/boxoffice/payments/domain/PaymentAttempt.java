package com.boxoffice.payments.domain;

import java.time.Instant;

public record PaymentAttempt(long id, String orderRef, int attemptNo, String outcome, int latencyMs, Instant createdAt) {
}
