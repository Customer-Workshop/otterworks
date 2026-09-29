package com.otterworks.ticketing.orders.api;

import com.fasterxml.jackson.databind.JsonNode;
import com.otterworks.ticketing.orders.inbox.InboxService;
import java.util.Map;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** {@code POST /events/<event-name>}: the same JSON the producer put on Kafka, delivered over HTTP. */
@RestController
@RequestMapping("/events")
public class InboxController {

    private final InboxService inbox;

    public InboxController(InboxService inbox) {
        this.inbox = inbox;
    }

    @PostMapping("/payment-failed")
    public Map<String, Object> paymentFailed(@RequestBody JsonNode event) {
        return inbox.paymentFailed(event);
    }

    @PostMapping("/order-confirmed")
    public Map<String, Object> orderConfirmed(@RequestBody JsonNode event) {
        return inbox.orderConfirmed(event);
    }

    @PostMapping("/hold-expired")
    public Map<String, Object> holdExpired(@RequestBody JsonNode event) {
        return inbox.holdExpired(event);
    }
}
