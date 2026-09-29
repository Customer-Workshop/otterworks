package com.boxoffice.confirmations.api;

import com.boxoffice.confirmations.domain.FulfilmentService;
import com.boxoffice.confirmations.events.PaymentCapturedEvent;
import jakarta.validation.Valid;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Inbox for the events this service consumes. payments POSTs here before committing its offset. */
@RestController
@RequestMapping("/events")
public class InboxController {

    private final FulfilmentService fulfilment;

    public InboxController(FulfilmentService fulfilment) {
        this.fulfilment = fulfilment;
    }

    /** 201 when tickets were issued, 200 when the orderRef was already confirmed (replay: same tickets, re-delivered). */
    @PostMapping("/payment-captured")
    public ResponseEntity<Map<String, Object>> paymentCaptured(@Valid @RequestBody PaymentCapturedEvent event) {
        FulfilmentService.Outcome out = fulfilment.onPaymentCaptured(event);
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("orderRef", out.confirmation().orderRef());
        body.put("status", "CONFIRMED");
        body.put("ticketCount", out.tickets().size());
        body.put("tickets", Views.tickets(out.tickets()));
        body.put("replay", out.replay());
        body.put("confirmedAt", FulfilmentService.iso(out.confirmation().createdAt()));
        body.put("publishedTo", out.topic());
        body.put("delivered", out.delivered());
        return ResponseEntity.status(out.replay() ? HttpStatus.OK : HttpStatus.CREATED).body(body);
    }
}
