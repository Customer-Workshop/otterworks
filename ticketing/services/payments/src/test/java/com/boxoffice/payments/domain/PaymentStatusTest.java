package com.boxoffice.payments.domain;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class PaymentStatusTest {

    @Test
    void failureOutcomesMapToTheMonolithOrderTransitions() {
        assertThat(PaymentStatus.DECLINED.failureOutcome()).isEqualTo("DECLINED");
        assertThat(PaymentStatus.DECLINED.orderStatus()).isEqualTo("PAYMENT_FAILED");
        assertThat(PaymentStatus.TIMEOUT.failureOutcome()).isEqualTo("TIMEOUT");
        assertThat(PaymentStatus.TIMEOUT.orderStatus()).isEqualTo("PAYMENT_TIMEOUT");
        assertThat(PaymentStatus.EXPIRED.failureOutcome()).isEqualTo("HOLD_EXPIRED");
        assertThat(PaymentStatus.EXPIRED.orderStatus()).isEqualTo("CANCELLED");
    }

    @Test
    void capturedHasNoFailureMapping() {
        assertThat(PaymentStatus.CAPTURED.captured()).isTrue();
        assertThat(PaymentStatus.CAPTURED.failureOutcome()).isNull();
        assertThat(PaymentStatus.CAPTURED.orderStatus()).isNull();
        assertThat(PaymentStatus.CAPTURED.attemptOutcome()).isEqualTo("APPROVED");
    }
}
