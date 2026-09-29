package com.boxoffice.payments.service;

import com.boxoffice.payments.config.PaymentsProperties;
import com.boxoffice.payments.domain.DeliveryTarget;
import com.boxoffice.payments.repo.DeliveryRepository;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import org.springframework.kafka.support.JacksonUtils;
import org.springframework.stereotype.Component;

/**
 * Writes the HTTP inbox fan-out of an outcome into outcome_deliveries. Called inside the payment transaction so the
 * rows commit with the payment (or not at all); InboxRelay POSTs them afterwards. A blank inbox URL disables that
 * target (local runs), exactly as the synchronous delivery used to. Payloads are serialized with the same mapper as
 * the Kafka JsonSerializer, so an inbox receives byte-for-byte what the topic carries.
 */
@Component
public class OutcomeOutbox {

    public static final String PAYMENT_CAPTURED = "payment-captured";
    public static final String PAYMENT_FAILED = "payment-failed";

    private final DeliveryRepository deliveries;
    private final PaymentsProperties props;
    private final ObjectMapper json = JacksonUtils.enhancedObjectMapper();

    public OutcomeOutbox(DeliveryRepository deliveries, PaymentsProperties props) {
        this.deliveries = deliveries;
        this.props = props;
    }

    public void enqueue(OutcomeEvent event, Instant at) {
        if (event.captured() != null) {
            enqueue(event.orderRef(), DeliveryTarget.CONFIRMATIONS, props.inbox().confirmationsUrl(), PAYMENT_CAPTURED, event.captured(), at);
        } else {
            enqueue(event.orderRef(), DeliveryTarget.ORDERS, props.inbox().ordersUrl(), PAYMENT_FAILED, event.failed(), at);
            enqueue(event.orderRef(), DeliveryTarget.SEATS, props.inbox().seatsUrl(), PAYMENT_FAILED, event.failed(), at);
        }
    }

    /** Resolves the inbox URL for a stored delivery; null when that target is disabled. */
    public String urlFor(DeliveryTarget target, String event) {
        String base = switch (target) {
            case CONFIRMATIONS -> props.inbox().confirmationsUrl();
            case ORDERS -> props.inbox().ordersUrl();
            case SEATS -> props.inbox().seatsUrl();
        };
        if (base == null || base.isBlank()) {
            return null;
        }
        return base.replaceAll("/+$", "") + "/events/" + event;
    }

    private void enqueue(String orderRef, DeliveryTarget target, String baseUrl, String event, Object payload, Instant at) {
        if (baseUrl == null || baseUrl.isBlank()) {
            return;
        }
        try {
            deliveries.enqueue(orderRef, target, event, json.writeValueAsString(payload), at);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("cannot serialize " + event + " for " + orderRef, e);
        }
    }
}
