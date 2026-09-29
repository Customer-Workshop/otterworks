package com.boxoffice.confirmations.events;

import com.boxoffice.confirmations.config.ConfirmationsProperties;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.LinkedHashMap;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

/**
 * Hands order-confirmed to the orders and seats inboxes inside the payment-captured request, so payments
 * only commits its offset once both sides have converted the hold and closed the order.
 */
@Component
public class InboxDelivery {

    private static final Logger log = LoggerFactory.getLogger(InboxDelivery.class);

    private final RestClient http;
    private final Map<String, String> targets;
    private final MeterRegistry registry;

    public InboxDelivery(RestClient inboxRestClient, ConfirmationsProperties props, MeterRegistry registry) {
        this.http = inboxRestClient;
        this.registry = registry;
        Map<String, String> t = new LinkedHashMap<>();
        t.put("orders", props.ordersInboxUrl());
        t.put("seats", props.seatsInboxUrl());
        this.targets = java.util.Collections.unmodifiableMap(t);
    }

    public Map<String, String> targets() {
        return targets;
    }

    /** Delivers to every inbox; the first failure is raised after all targets were attempted. */
    public Map<String, Integer> deliver(OrderConfirmedEvent event) {
        Map<String, Integer> statuses = new LinkedHashMap<>();
        DeliveryException failure = null;
        for (Map.Entry<String, String> target : targets.entrySet()) {
            try {
                int status = http.post().uri(target.getValue())
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(event)
                        .retrieve()
                        .toBodilessEntity()
                        .getStatusCode().value();
                statuses.put(target.getKey(), status);
                registry.counter("confirmations_inbox_deliveries_total", "target", target.getKey(), "outcome", "ok").increment();
            } catch (RestClientResponseException e) {
                statuses.put(target.getKey(), e.getStatusCode().value());
                registry.counter("confirmations_inbox_deliveries_total", "target", target.getKey(), "outcome", "rejected").increment();
                log.warn("inbox {} rejected order-confirmed orderRef={} status={}", target.getKey(), event.orderRef(), e.getStatusCode().value());
                failure = failure == null ? new DeliveryException(target.getKey(), "HTTP " + e.getStatusCode().value(), e) : failure;
            } catch (RuntimeException e) {
                registry.counter("confirmations_inbox_deliveries_total", "target", target.getKey(), "outcome", "error").increment();
                log.warn("inbox {} unreachable for orderRef={}: {}", target.getKey(), event.orderRef(), e.toString());
                failure = failure == null ? new DeliveryException(target.getKey(), e.getMessage() == null ? e.toString() : e.getMessage(), e) : failure;
            }
        }
        if (failure != null) {
            throw failure;
        }
        return statuses;
    }
}
