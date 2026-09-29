package com.otterworks.ticketing.orders.order;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class OrderStatusTest {

    @Test
    void failureOutcomesMapToTheMonolithStatuses() {
        assertThat(OrderStatus.forFailureOutcome("DECLINED")).isEqualTo(OrderStatus.PAYMENT_FAILED);
        assertThat(OrderStatus.forFailureOutcome("TIMEOUT")).isEqualTo(OrderStatus.PAYMENT_TIMEOUT);
        assertThat(OrderStatus.forFailureOutcome("HOLD_EXPIRED")).isEqualTo(OrderStatus.CANCELLED);
        assertThat(OrderStatus.forFailureOutcome("ANYTHING_ELSE")).isEqualTo(OrderStatus.PAYMENT_FAILED);
    }

    @Test
    void onlyPendingPaymentIsNonTerminal() {
        assertThat(OrderStatus.PENDING_PAYMENT.terminal()).isFalse();
        for (OrderStatus s : OrderStatus.values()) {
            if (s != OrderStatus.PENDING_PAYMENT) {
                assertThat(s.terminal()).as(s.name()).isTrue();
            }
        }
    }
}
