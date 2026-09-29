package com.otterworks.ticketing.orders.inbox;

import com.fasterxml.jackson.databind.JsonNode;
import com.otterworks.ticketing.orders.order.OrderRecord;
import com.otterworks.ticketing.orders.order.OrderRepository;
import com.otterworks.ticketing.orders.order.OrderStatus;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * HTTP inboxes for the events orders consumes. Every handler is idempotent on the key: a transition is
 * applied only from PENDING_PAYMENT, replays and terminal-state deliveries are acknowledged as no-ops.
 */
@Service
public class InboxService {

    private static final Logger log = LoggerFactory.getLogger(InboxService.class);

    private final OrderRepository orders;

    public InboxService(OrderRepository orders) {
        this.orders = orders;
    }

    /** payment-failed: {orderRef, holdRef, outcome DECLINED|TIMEOUT|HOLD_EXPIRED, orderStatus?, ...}. */
    @Transactional
    public Map<String, Object> paymentFailed(JsonNode event) {
        String orderRef = required(event, "orderRef");
        String outcome = event.path("outcome").asText("DECLINED");
        OrderStatus target = event.path("orderStatus").isTextual()
                ? parseStatus(event.path("orderStatus").asText(), outcome)
                : OrderStatus.forFailureOutcome(outcome);
        int applied = orders.transitionByRef(orderRef, target, outcome);
        return ack(orderRef, applied > 0, "payment-failed");
    }

    /** order-confirmed: {orderRef, holdRef, performanceId, ticketCount, tickets[]{ticketCode,seatInventoryId,barcode}, ...}. */
    @Transactional
    public Map<String, Object> orderConfirmed(JsonNode event) {
        String orderRef = required(event, "orderRef");
        int applied = orders.transitionByRef(orderRef, OrderStatus.CONFIRMED, "APPROVED");
        Optional<OrderRecord> order = orders.byRef(orderRef);
        int stamped = 0;
        if (order.isPresent()) {
            for (JsonNode t : event.path("tickets")) {
                if (t.path("ticketCode").isTextual() && t.path("seatInventoryId").canConvertToLong()) {
                    stamped += orders.stampTicket(order.get().id(), t.path("seatInventoryId").asLong(),
                            t.path("ticketCode").asText());
                }
            }
        }
        Map<String, Object> ack = ack(orderRef, applied > 0, "order-confirmed");
        ack.put("ticketsStamped", stamped);
        return ack;
    }

    /** hold-expired: {holdRef, performanceId, orderRef?, seatInventoryIds[], expiredAt}. */
    @Transactional
    public Map<String, Object> holdExpired(JsonNode event) {
        String holdRef = required(event, "holdRef");
        int cancelled = orders.cancelPendingByHold(holdRef);
        Map<String, Object> ack = new LinkedHashMap<>();
        ack.put("event", "hold-expired");
        ack.put("holdRef", holdRef);
        ack.put("cancelled", cancelled);
        ack.put("applied", cancelled > 0);
        return ack;
    }

    private Map<String, Object> ack(String orderRef, boolean applied, String event) {
        Optional<OrderRecord> order = orders.byRef(orderRef);
        if (order.isEmpty()) {
            log.warn("{} for unknown order {} acknowledged as no-op", event, orderRef);
        }
        Map<String, Object> ack = new LinkedHashMap<>();
        ack.put("event", event);
        ack.put("orderRef", orderRef);
        ack.put("applied", applied);
        ack.put("known", order.isPresent());
        ack.put("status", order.map(OrderRecord::status).orElse(null));
        ack.put("paymentOutcome", order.map(OrderRecord::paymentOutcome).orElse(null));
        return ack;
    }

    private static OrderStatus parseStatus(String value, String outcome) {
        try {
            OrderStatus s = OrderStatus.valueOf(value);
            return s == OrderStatus.PENDING_PAYMENT || s == OrderStatus.CONFIRMED
                    ? OrderStatus.forFailureOutcome(outcome) : s;
        } catch (IllegalArgumentException e) {
            return OrderStatus.forFailureOutcome(outcome);
        }
    }

    private static String required(JsonNode event, String field) {
        JsonNode n = event == null ? null : event.path(field);
        if (n == null || !n.isTextual() || n.asText().isBlank()) {
            throw new com.otterworks.ticketing.orders.api.OrdersException("BAD_REQUEST", field + " is required");
        }
        return n.asText();
    }
}
