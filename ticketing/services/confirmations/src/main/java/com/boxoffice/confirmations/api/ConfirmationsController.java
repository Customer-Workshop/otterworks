package com.boxoffice.confirmations.api;

import com.boxoffice.confirmations.domain.FulfilmentService;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ConfirmationsController {

    private final FulfilmentService fulfilment;

    public ConfirmationsController(FulfilmentService fulfilment) {
        this.fulfilment = fulfilment;
    }

    @GetMapping("/api/confirmations/{orderRef}")
    public Map<String, Object> byOrderRef(@PathVariable String orderRef) {
        FulfilmentService.Outcome out = fulfilment.find(orderRef).orElseThrow(() -> new NotFoundException(orderRef));
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("orderRef", out.confirmation().orderRef());
        body.put("holdRef", out.confirmation().holdRef());
        body.put("performanceId", out.confirmation().performanceId());
        body.put("ticketCount", out.tickets().size());
        body.put("tickets", Views.tickets(out.tickets()));
        body.put("confirmation", Views.confirmation(out.confirmation()));
        return body;
    }

    /** Reconciliation counters, same names as the monolith's {@code /api/stats} for the rows this service now owns. */
    @GetMapping("/stats")
    public Map<String, Object> stats() {
        return fulfilment.stats();
    }
}
