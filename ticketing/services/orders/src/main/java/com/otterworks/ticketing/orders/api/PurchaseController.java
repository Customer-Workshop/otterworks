package com.otterworks.ticketing.orders.api;

import com.fasterxml.jackson.databind.JsonNode;
import com.otterworks.ticketing.orders.config.OrdersProperties;
import com.otterworks.ticketing.orders.order.OrderRecord;
import com.otterworks.ticketing.orders.order.OrderService;
import com.otterworks.ticketing.orders.order.OrderView;
import com.otterworks.ticketing.orders.order.PlaceOrderRequest;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class PurchaseController {

    private final OrderService orders;
    private final OrdersProperties props;

    public PurchaseController(OrderService orders, OrdersProperties props) {
        this.orders = orders;
        this.props = props;
    }

    /**
     * Legacy purchase: {performanceId,email,quantity?,section?,promoCode?,delivery?,cardLast4?,clientRef?}.
     * Answers 202 with the PENDING_PAYMENT order; payment converges asynchronously.
     */
    @PostMapping("/purchase")
    public ResponseEntity<Map<String, Object>> purchase(@RequestBody JsonNode body) {
        requireObject(body);
        JsonNode perf = body.path("performanceId");
        if (!perf.isNumber() && !(perf.isTextual() && perf.asText().matches("\\d+"))) {
            throw new OrdersException("BAD_REQUEST", "performanceId is required");
        }
        PlaceOrderRequest req = new PlaceOrderRequest(
                perf.asLong(), null, requireEmail(body),
                body.path("quantity").asInt(PlaceOrderRequest.DEFAULT_QUANTITY),
                text(body, "section"), text(body, "promoCode"), text(body, "delivery"),
                text(body, "cardLast4"), text(body, "clientRef"), props.channel());
        return accepted(orders.purchase(req));
    }

    /** Place from an existing hold: {holdRef,email,promoCode?,delivery?,cardLast4?,clientRef?}. */
    @PostMapping("/orders")
    public ResponseEntity<Map<String, Object>> placeFromHold(@RequestBody JsonNode body) {
        requireObject(body);
        String holdRef = text(body, "holdRef");
        if (holdRef == null || holdRef.isBlank()) {
            throw new OrdersException("BAD_REQUEST", "holdRef is required");
        }
        PlaceOrderRequest req = new PlaceOrderRequest(
                null, holdRef, requireEmail(body), 0, null,
                text(body, "promoCode"), text(body, "delivery"), text(body, "cardLast4"), text(body, "clientRef"),
                props.channel());
        return accepted(orders.placeFromHold(req));
    }

    @GetMapping("/orders/{ref}")
    public Map<String, Object> order(@PathVariable String ref) {
        return orders.view(ref);
    }

    private ResponseEntity<Map<String, Object>> accepted(OrderRecord o) {
        long tickets = 0;
        if ("CONFIRMED".equals(o.status()) && orders.view(o.orderRef()).get("tickets") instanceof Long stamped) {
            tickets = stamped;
        }
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(OrderView.summary(o, tickets));
    }

    private static void requireObject(JsonNode body) {
        if (body == null || !body.isObject()) {
            throw new OrdersException("BAD_REQUEST", "invalid JSON");
        }
    }

    private static String requireEmail(JsonNode body) {
        String email = text(body, "email");
        if (email == null || email.isBlank() || !email.contains("@")) {
            throw new OrdersException("BAD_REQUEST", "email is required");
        }
        return email;
    }

    private static String text(JsonNode body, String field) {
        JsonNode n = body.path(field);
        return n.isMissingNode() || n.isNull() ? null : n.asText();
    }
}
