package com.boxoffice.confirmations.domain;

import com.boxoffice.confirmations.events.DeliveryException;
import com.boxoffice.confirmations.events.InboxDelivery;
import com.boxoffice.confirmations.events.OrderConfirmedEvent;
import com.boxoffice.confirmations.events.OrderConfirmedPublisher;
import com.boxoffice.confirmations.events.PaymentCapturedEvent;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * The monolith's {@code ConfirmationBean.confirm} without the shared schema: tickets and the confirmation row are
 * written in one local transaction keyed by {@code orderRef}; the seat/hold/order side effects that used to be
 * three UPDATEs on other contexts' tables travel as {@code order-confirmed} to Kafka and to the orders and seats
 * inboxes. A replay for a known {@code orderRef} issues nothing and re-drives the event.
 */
@Service
public class FulfilmentService {

    private static final Logger log = LoggerFactory.getLogger(FulfilmentService.class);
    private static final DateTimeFormatter ISO_UTC = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'");

    private final FulfilmentRepository repo;
    private final TransactionTemplate tx;
    private final OrderConfirmedPublisher publisher;
    private final InboxDelivery inboxes;
    private final Clock clock;
    private final Counter ticketsIssued;
    private final Counter ordersConfirmed;
    private final Counter replays;
    private final Counter deliveryFailures;
    private final Timer inboxTimer;

    public FulfilmentService(FulfilmentRepository repo, TransactionTemplate tx, OrderConfirmedPublisher publisher,
                             InboxDelivery inboxes, Clock clock, MeterRegistry registry) {
        this.repo = repo;
        this.tx = tx;
        this.publisher = publisher;
        this.inboxes = inboxes;
        this.clock = clock;
        this.ticketsIssued = registry.counter("confirmations_tickets_issued_total");
        this.ordersConfirmed = registry.counter("confirmations_orders_confirmed_total");
        this.replays = registry.counter("confirmations_inbox_replays_total");
        this.deliveryFailures = registry.counter("confirmations_delivery_failures_total");
        this.inboxTimer = registry.timer("confirmations_inbox_seconds", "event", "payment-captured");
    }

    /** Result of one inbox request: what is stored, whether it already was, and where the event went. */
    public record Outcome(Confirmation confirmation, List<Ticket> tickets, boolean replay, String topic,
                          Map<String, Integer> delivered) {

        public OrderConfirmedEvent event() {
            return FulfilmentService.toEvent(confirmation, tickets);
        }
    }

    public Outcome onPaymentCaptured(PaymentCapturedEvent event) {
        return inboxTimer.record(() -> handle(event));
    }

    private Outcome handle(PaymentCapturedEvent event) {
        String ref = event.orderRef();
        Stored stored;
        try {
            stored = tx.execute(status -> issue(event));
        } catch (DuplicateKeyException e) {
            // two deliveries raced; the loser reads what the winner committed
            log.info("orderRef={} issued concurrently; replaying", ref);
            stored = tx.execute(status -> existing(ref).orElseThrow(() -> new DuplicateOrderException(ref, e)));
        }
        if (stored.replay()) {
            replays.increment();
        } else {
            ticketsIssued.increment(stored.tickets().size());
            ordersConfirmed.increment();
        }
        OrderConfirmedEvent out = toEvent(stored.confirmation(), stored.tickets());
        String topic;
        Map<String, Integer> delivered;
        try {
            topic = publisher.publish(out);
            delivered = inboxes.deliver(out);
        } catch (DeliveryException e) {
            deliveryFailures.increment();
            throw e;
        }
        log.info("orderRef={} tickets={} replay={} topic={} delivered={}", ref, stored.tickets().size(), stored.replay(), topic, delivered);
        return new Outcome(stored.confirmation(), stored.tickets(), stored.replay(), topic, delivered);
    }

    private record Stored(Confirmation confirmation, List<Ticket> tickets, boolean replay) {
    }

    private Stored issue(PaymentCapturedEvent event) {
        Optional<Stored> already = existing(event.orderRef());
        if (already.isPresent()) {
            return already.get();
        }
        LocalDateTime now = LocalDateTime.now(clock);
        PaymentCapturedEvent.Order order = event.order();
        List<Ticket> tickets = new ArrayList<>(order.items().size());
        for (PaymentCapturedEvent.Item item : order.items()) {
            String code = Refs.next("TK");
            Ticket t = new Ticket(code, event.orderRef(), item.seatInventoryId(),
                    MonolithFormats.barcode(code, event.orderRef(), item.seatInventoryId()), now);
            repo.insertTicket(t);
            tickets.add(t);
        }
        Confirmation c = new Confirmation(event.orderRef(), order.holdRef(), order.performanceId(), "EMAIL",
                order.customerEmail(), MonolithFormats.subject(order.eventTitle()),
                MonolithFormats.body(event.orderRef(), tickets.size(), order.eventTitle(), order.venueName(),
                        order.startsAt(), order.totalCents()),
                "QUEUED", null, now);
        repo.insertConfirmation(c);
        return new Stored(c, tickets, false);
    }

    private Optional<Stored> existing(String orderRef) {
        return repo.findConfirmation(orderRef).map(c -> new Stored(c, repo.findTickets(orderRef), true));
    }

    @Transactional(readOnly = true)
    public Optional<Outcome> find(String orderRef) {
        return repo.findConfirmation(orderRef)
                .map(c -> new Outcome(c, repo.findTickets(orderRef), true, null, Map.of()));
    }

    @Transactional(readOnly = true)
    public Map<String, Object> stats() {
        long queued = repo.countConfirmations();
        long sent = repo.countConfirmationsSent();
        return Map.of(
                "ticketsIssued", repo.countTickets(),
                "ordersConfirmed", queued,
                "confirmationsQueued", queued - sent,
                "confirmationsSent", sent);
    }

    static OrderConfirmedEvent toEvent(Confirmation c, List<Ticket> tickets) {
        return new OrderConfirmedEvent(c.orderRef(), c.holdRef(), c.performanceId(), tickets.size(),
                tickets.stream().map(t -> new OrderConfirmedEvent.Ticket(t.ticketCode(), t.seatInventoryId(), t.barcode())).toList(),
                c.recipient(), iso(c.createdAt()));
    }

    public static String iso(LocalDateTime utc) {
        return utc == null ? null : utc.atOffset(ZoneOffset.UTC).format(ISO_UTC);
    }
}
