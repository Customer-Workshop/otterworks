package com.boxoffice.confirmations.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.boxoffice.confirmations.events.DeliveryException;
import com.boxoffice.confirmations.events.InboxDelivery;
import com.boxoffice.confirmations.events.OrderConfirmedEvent;
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
import org.mockito.ArgumentCaptor;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

class FulfilmentServiceTest {

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

    private static PaymentCapturedEvent captured(String ref, long... seats) {
        List<PaymentCapturedEvent.Item> items = java.util.Arrays.stream(seats)
                .mapToObj(s -> new PaymentCapturedEvent.Item(s, "H1", "R01", (int) (s % 10), "P1")).toList();
        return new PaymentCapturedEvent(ref, "PAY-1", 42836L, "USD", "4242", 1, 80L, "2026-09-29T01:22:50Z",
                new PaymentCapturedEvent.Order("fan@example.test", 7L, "Hollow Pines Ensemble: Winter Songs",
                        "Ossery Hall", "2026-10-20 20:00:00.0", "HD-SEED000005", 42836L, items));
    }

    @Test
    void issuesOneTicketPerSeatAndQueuesTheConfirmation() {
        when(repo.findConfirmation("BO-A")).thenReturn(Optional.empty());

        FulfilmentService.Outcome out = service.onPaymentCaptured(captured("BO-A", 120006, 120015));

        assertThat(out.replay()).isFalse();
        assertThat(out.tickets()).hasSize(2).extracting(Ticket::seatInventoryId).containsExactly(120006L, 120015L);
        assertThat(out.tickets()).allSatisfy(t -> {
            assertThat(t.ticketCode()).matches("^TK-[" + Refs.ALPHABET + "]{10}$");
            assertThat(t.barcode()).isEqualTo(MonolithFormats.barcode(t.ticketCode(), "BO-A", t.seatInventoryId()));
            assertThat(t.issuedAt()).isEqualTo(NOW);
        });
        Confirmation c = out.confirmation();
        assertThat(c.orderRef()).isEqualTo("BO-A");
        assertThat(c.holdRef()).isEqualTo("HD-SEED000005");
        assertThat(c.performanceId()).isEqualTo(7L);
        assertThat(c.channel()).isEqualTo("EMAIL");
        assertThat(c.recipient()).isEqualTo("fan@example.test");
        assertThat(c.subject()).isEqualTo("Your tickets for Hollow Pines Ensemble: Winter Songs");
        assertThat(c.body()).isEqualTo("Order BO-A: 2 ticket(s) for Hollow Pines Ensemble: Winter Songs at Ossery Hall on 2026-10-20 20:00:00.0. Total $428.36.");
        assertThat(c.status()).isEqualTo("QUEUED");
        assertThat(c.sentAt()).isNull();
        verify(repo, times(2)).insertTicket(any());
        verify(repo).insertConfirmation(any());
        assertThat(registry.counter("confirmations_tickets_issued_total").count()).isEqualTo(2.0);
        assertThat(registry.counter("confirmations_orders_confirmed_total").count()).isEqualTo(1.0);
    }

    @Test
    void publishesThenDeliversOrderConfirmedWithTheIssuedTickets() {
        when(repo.findConfirmation("BO-A")).thenReturn(Optional.empty());

        FulfilmentService.Outcome out = service.onPaymentCaptured(captured("BO-A", 4));

        ArgumentCaptor<OrderConfirmedEvent> published = ArgumentCaptor.forClass(OrderConfirmedEvent.class);
        ArgumentCaptor<OrderConfirmedEvent> delivered = ArgumentCaptor.forClass(OrderConfirmedEvent.class);
        verify(publisher).publish(published.capture());
        verify(inboxes).deliver(delivered.capture());
        OrderConfirmedEvent e = published.getValue();
        assertThat(e).isEqualTo(delivered.getValue());
        assertThat(e.orderRef()).isEqualTo("BO-A");
        assertThat(e.holdRef()).isEqualTo("HD-SEED000005");
        assertThat(e.performanceId()).isEqualTo(7L);
        assertThat(e.ticketCount()).isEqualTo(1);
        assertThat(e.tickets()).singleElement().satisfies(t -> {
            assertThat(t.ticketCode()).isEqualTo(out.tickets().get(0).ticketCode());
            assertThat(t.seatInventoryId()).isEqualTo(4L);
            assertThat(t.barcode()).isEqualTo(out.tickets().get(0).barcode());
        });
        assertThat(e.recipient()).isEqualTo("fan@example.test");
        assertThat(e.confirmedAt()).isEqualTo("2026-09-29T01:22:50.500Z");
        assertThat(out.topic()).isEqualTo("tkt01-order-confirmed");
        assertThat(out.delivered()).containsEntry("orders", 200).containsEntry("seats", 200);
    }

    @Test
    void replayReturnsExistingTicketsWithoutIssuingAndRedelivers() {
        Confirmation existing = new Confirmation("BO-A", "HD-1", 7L, "EMAIL", "fan@example.test", "s", "b", "QUEUED", null, NOW);
        List<Ticket> tickets = List.of(new Ticket("TK-EXISTING01", "BO-A", 120006L, "bc-120006", NOW));
        when(repo.findConfirmation("BO-A")).thenReturn(Optional.of(existing));
        when(repo.findTickets("BO-A")).thenReturn(tickets);

        FulfilmentService.Outcome out = service.onPaymentCaptured(captured("BO-A", 120006));

        assertThat(out.replay()).isTrue();
        assertThat(out.tickets()).isEqualTo(tickets);
        assertThat(out.confirmation()).isEqualTo(existing);
        verify(repo, never()).insertTicket(any());
        verify(repo, never()).insertConfirmation(any());
        verify(publisher).publish(any());
        verify(inboxes).deliver(any());
        assertThat(registry.counter("confirmations_inbox_replays_total").count()).isEqualTo(1.0);
        assertThat(registry.counter("confirmations_tickets_issued_total").count()).isZero();
    }

    @Test
    void concurrentDuplicateFallsBackToReplayOfTheWinner() {
        Confirmation winner = new Confirmation("BO-A", "HD-1", 7L, "EMAIL", "fan@example.test", "s", "b", "QUEUED", null, NOW);
        when(repo.findConfirmation("BO-A")).thenReturn(Optional.empty(), Optional.of(winner));
        when(repo.findTickets("BO-A")).thenReturn(List.of(new Ticket("TK-WINNER0001", "BO-A", 4L, "bc", NOW)));
        org.mockito.Mockito.doThrow(new DuplicateKeyException("confirmations_order_ref_key")).when(repo).insertConfirmation(any());

        FulfilmentService.Outcome out = service.onPaymentCaptured(captured("BO-A", 4));

        assertThat(out.replay()).isTrue();
        assertThat(out.tickets()).extracting(Ticket::ticketCode).containsExactly("TK-WINNER0001");
    }

    @Test
    void deliveryFailureSurfacesAfterTicketsAreCommitted() {
        when(repo.findConfirmation("BO-A")).thenReturn(Optional.empty());
        when(inboxes.deliver(any())).thenThrow(new DeliveryException("seats", "HTTP 503", null));

        assertThatThrownBy(() -> service.onPaymentCaptured(captured("BO-A", 4)))
                .isInstanceOf(DeliveryException.class)
                .hasMessageContaining("seats");
        verify(repo).insertConfirmation(any());
        verify(publisher).publish(any());
        assertThat(registry.counter("confirmations_delivery_failures_total").count()).isEqualTo(1.0);
    }

    @Test
    void statsSplitQueuedFromSent() {
        when(repo.countTickets()).thenReturn(12L);
        when(repo.countConfirmations()).thenReturn(6L);
        when(repo.countConfirmationsSent()).thenReturn(0L);

        assertThat(service.stats()).containsEntry("ticketsIssued", 12L).containsEntry("ordersConfirmed", 6L)
                .containsEntry("confirmationsQueued", 6L).containsEntry("confirmationsSent", 0L);
    }

    @Test
    void findIsEmptyForUnknownOrderRef() {
        when(repo.findConfirmation(anyString())).thenReturn(Optional.empty());
        assertThat(service.find("BO-UNKNOWN0000")).isEmpty();
    }
}
