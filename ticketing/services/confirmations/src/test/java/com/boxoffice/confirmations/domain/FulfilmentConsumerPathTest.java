package com.boxoffice.confirmations.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.boxoffice.confirmations.events.InboxDelivery;
import com.boxoffice.confirmations.events.OrderConfirmedPublisher;
import com.boxoffice.confirmations.events.PaymentCapturedEvent;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** The Kafka path of {@link FulfilmentService}: same transaction, but a delivered replay re-drives nothing. */
class FulfilmentConsumerPathTest {

    private static final Clock CLOCK = Clock.fixed(Instant.parse("2026-09-29T01:22:50.500Z"), ZoneOffset.UTC);
    private static final LocalDateTime NOW = LocalDateTime.of(2026, 9, 29, 1, 22, 50, 500_000_000);

    private FulfilmentRepository repo;
    private OrderConfirmedPublisher publisher;
    private InboxDelivery inboxes;
    private SimpleMeterRegistry registry;
    private FulfilmentService service;

    @BeforeEach
    void setUp() {
        repo = mock(FulfilmentRepository.class);
        publisher = mock(OrderConfirmedPublisher.class);
        inboxes = mock(InboxDelivery.class);
        registry = new SimpleMeterRegistry();
        when(publisher.publish(any())).thenReturn("tkt01-order-confirmed");
        when(inboxes.deliver(any())).thenReturn(Map.of("orders", 200, "seats", 200));
        service = new FulfilmentService(repo, new TransactionTemplate(mock(PlatformTransactionManager.class)),
                publisher, inboxes, CLOCK, registry);
    }

    private static PaymentCapturedEvent captured(String ref) {
        return new PaymentCapturedEvent(ref, "PAY-1", 42836L, "USD", "4242", 1, 80L, "2026-09-29T01:22:50Z",
                new PaymentCapturedEvent.Order("fan@example.test", 7L, "Hollow Pines Ensemble: Winter Songs",
                        "Riverbend Hall", "2026-12-20T19:30:00Z", "HD-1", 42836L,
                        List.of(new PaymentCapturedEvent.Item(11L, "H1", "R01", 1, "P1"))));
    }

    private static Confirmation existing(String ref) {
        return new Confirmation(ref, "HD-1", 7L, "EMAIL", "fan@example.test", "s", "b", "QUEUED", null, NOW);
    }

    private static Ticket ticket(String ref) {
        return new Ticket("TK-1", ref, 11L, "BARCODE", NOW);
    }

    @Test
    void firstRecordIssuesTicketsDeliversAndMarksDelivered() {
        when(repo.findConfirmation("BO-A")).thenReturn(Optional.empty());

        FulfilmentService.Outcome out = service.onPaymentCapturedRecord(captured("BO-A"));

        assertThat(out.replay()).isFalse();
        assertThat(out.topic()).isEqualTo("tkt01-order-confirmed");
        verify(repo).insertConfirmation(any());
        verify(publisher).publish(any());
        verify(inboxes).deliver(any());
        verify(repo).markDelivered(eq("BO-A"), eq(NOW));
        assertThat(registry.counter("confirmations_consumer_records_total", "outcome", "issued").count()).isEqualTo(1.0);
    }

    @Test
    void redeliveredRecordForADeliveredOrderIsANoop() {
        when(repo.findConfirmation("BO-A")).thenReturn(Optional.of(existing("BO-A")));
        when(repo.findTickets("BO-A")).thenReturn(List.of(ticket("BO-A")));
        when(repo.isDelivered("BO-A")).thenReturn(true);

        FulfilmentService.Outcome out = service.onPaymentCapturedRecord(captured("BO-A"));

        assertThat(out.replay()).isTrue();
        assertThat(out.topic()).isNull();
        assertThat(out.tickets()).hasSize(1);
        verify(repo, never()).insertTicket(any());
        verify(publisher, never()).publish(any());
        verify(inboxes, never()).deliver(any());
        verify(repo, never()).markDelivered(anyString(), any());
        assertThat(registry.counter("confirmations_consumer_records_total", "outcome", "noop").count()).isEqualTo(1.0);
    }

    @Test
    void redeliveredRecordForAnUndeliveredOrderRedrivesTheEvent() {
        when(repo.findConfirmation("BO-A")).thenReturn(Optional.of(existing("BO-A")));
        when(repo.findTickets("BO-A")).thenReturn(List.of(ticket("BO-A")));
        when(repo.isDelivered("BO-A")).thenReturn(false);

        FulfilmentService.Outcome out = service.onPaymentCapturedRecord(captured("BO-A"));

        assertThat(out.replay()).isTrue();
        assertThat(out.topic()).isEqualTo("tkt01-order-confirmed");
        verify(repo, never()).insertTicket(any());
        verify(publisher).publish(any());
        verify(inboxes).deliver(any());
        verify(repo).markDelivered(eq("BO-A"), eq(NOW));
        assertThat(registry.counter("confirmations_consumer_records_total", "outcome", "redriven").count()).isEqualTo(1.0);
    }

    @Test
    void inboxReplayStillRedrivesEvenWhenDelivered() {
        when(repo.findConfirmation("BO-A")).thenReturn(Optional.of(existing("BO-A")));
        when(repo.findTickets("BO-A")).thenReturn(List.of(ticket("BO-A")));
        when(repo.isDelivered("BO-A")).thenReturn(true);

        FulfilmentService.Outcome out = service.onPaymentCaptured(captured("BO-A"));

        assertThat(out.replay()).isTrue();
        assertThat(out.topic()).isEqualTo("tkt01-order-confirmed");
        verify(repo, never()).isDelivered(anyString());
        verify(publisher).publish(any());
        verify(inboxes).deliver(any());
    }
}
