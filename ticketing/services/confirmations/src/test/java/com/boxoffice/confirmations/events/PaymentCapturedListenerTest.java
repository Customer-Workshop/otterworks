package com.boxoffice.confirmations.events;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.boxoffice.confirmations.domain.Confirmation;
import com.boxoffice.confirmations.domain.FulfilmentService;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import jakarta.validation.Validation;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.kafka.support.Acknowledgment;

class PaymentCapturedListenerTest {

    private FulfilmentService fulfilment;
    private Acknowledgment ack;
    private SimpleMeterRegistry registry;
    private PaymentCapturedListener listener;

    @BeforeEach
    void setUp() {
        fulfilment = mock(FulfilmentService.class);
        ack = mock(Acknowledgment.class);
        registry = new SimpleMeterRegistry();
        listener = new PaymentCapturedListener(fulfilment, Validation.buildDefaultValidatorFactory().getValidator(), registry);
    }

    private static PaymentCapturedEvent captured(String ref, PaymentCapturedEvent.Order order) {
        return new PaymentCapturedEvent(ref, "PAY-1", 42836L, "USD", "4242", 1, 80L, "2026-09-29T01:22:50Z", order);
    }

    private static PaymentCapturedEvent.Order order() {
        return new PaymentCapturedEvent.Order("fan@example.test", 7L, "Hollow Pines Ensemble: Winter Songs",
                "Riverbend Hall", "2026-12-20T19:30:00Z", "HD-1", 42836L,
                List.of(new PaymentCapturedEvent.Item(11L, "H1", "R01", 1, "P1")));
    }

    private static ConsumerRecord<String, PaymentCapturedEvent> record(String key, PaymentCapturedEvent value) {
        return new ConsumerRecord<>("tkt01-payment-captured", 2, 17L, key, value);
    }

    private static FulfilmentService.Outcome outcome(String ref, boolean replay, String topic) {
        Confirmation c = new Confirmation(ref, "HD-1", 7L, "EMAIL", "fan@example.test", "s", "b", "QUEUED", null, LocalDateTime.now());
        return new FulfilmentService.Outcome(c, List.of(), replay, topic, Map.of());
    }

    @Test
    void validRecordIsHandledOnTheConsumerPathThenAcknowledged() {
        PaymentCapturedEvent event = captured("BO-A", order());
        when(fulfilment.onPaymentCapturedRecord(event)).thenReturn(outcome("BO-A", false, "tkt01-order-confirmed"));

        listener.onPaymentCaptured(record("BO-A", event), ack);

        verify(fulfilment).onPaymentCapturedRecord(event);
        verify(fulfilment, never()).onPaymentCaptured(any());
        verify(ack).acknowledge();
    }

    @Test
    void undecodableRecordIsSkippedAndAcknowledged() {
        listener.onPaymentCaptured(record("BO-B", null), ack);

        verify(fulfilment, never()).onPaymentCapturedRecord(any());
        verify(ack).acknowledge();
        assertThat(registry.counter("confirmations_consumer_records_total", "outcome", "skipped").count()).isEqualTo(1.0);
    }

    @Test
    void recordFailingValidationIsSkippedAndAcknowledged() {
        PaymentCapturedEvent noOrder = captured("BO-C", null);

        listener.onPaymentCaptured(record("BO-C", noOrder), ack);

        verify(fulfilment, never()).onPaymentCapturedRecord(any());
        verify(ack).acknowledge();
        assertThat(registry.counter("confirmations_consumer_records_total", "outcome", "skipped").count()).isEqualTo(1.0);
    }

    @Test
    void deliveryFailureLeavesTheOffsetUncommitted() {
        PaymentCapturedEvent event = captured("BO-D", order());
        when(fulfilment.onPaymentCapturedRecord(event)).thenThrow(new DeliveryException("seats", "HTTP 503", null));

        assertThatThrownBy(() -> listener.onPaymentCaptured(record("BO-D", event), ack)).isInstanceOf(DeliveryException.class);

        verify(ack, never()).acknowledge();
    }
}
