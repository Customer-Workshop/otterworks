package com.otterworks.ticketing.seats.api;

import com.fasterxml.jackson.databind.JsonNode;
import com.otterworks.ticketing.seats.domain.Dtos.InboxResult;
import com.otterworks.ticketing.seats.events.InboxService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/** HTTP inboxes; payloads are the shared event contracts, keyed by orderRef. */
@RestController
public class EventsController {

    private final InboxService inbox;

    public EventsController(InboxService inbox) {
        this.inbox = inbox;
    }

    @PostMapping("/events/payment-failed")
    public InboxResult paymentFailed(@RequestBody JsonNode payload) {
        return inbox.paymentFailed(payload);
    }

    @PostMapping("/events/order-confirmed")
    public InboxResult orderConfirmed(@RequestBody JsonNode payload) {
        return inbox.orderConfirmed(payload);
    }
}
