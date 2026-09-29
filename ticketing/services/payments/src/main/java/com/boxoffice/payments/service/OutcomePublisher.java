package com.boxoffice.payments.service;

import com.boxoffice.payments.config.PaymentsProperties;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/**
 * Delivery contract for payment-captured / payment-failed: Kafka record keyed by orderRef, then the same payload
 * POSTed to the HTTP inboxes (confirmations for captured; orders and seats for failed). Both must succeed before
 * the consumer commits its offset; any failure propagates and the record is redelivered (idempotent).
 */
@Component
public class OutcomePublisher {

    private static final Logger log = LoggerFactory.getLogger(OutcomePublisher.class);

    private final KafkaTemplate<String, Object> kafka;
    private final RestClient http;
    private final PaymentsProperties props;

    public OutcomePublisher(KafkaTemplate<String, Object> kafka, RestClient inboxRestClient, PaymentsProperties props) {
        this.kafka = kafka;
        this.http = inboxRestClient;
        this.props = props;
    }

    public void publish(OutcomeEvent event) {
        if (event.captured() != null) {
            send(props.topics().paymentCaptured(), event.orderRef(), event.captured());
            post(props.inbox().confirmationsUrl(), "/events/payment-captured", event.captured());
        } else {
            send(props.topics().paymentFailed(), event.orderRef(), event.failed());
            post(props.inbox().ordersUrl(), "/events/payment-failed", event.failed());
            post(props.inbox().seatsUrl(), "/events/payment-failed", event.failed());
        }
    }

    private void send(String topic, String key, Object payload) {
        try {
            kafka.send(topic, key, payload).get(30, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new DeliveryException(topic, e);
        } catch (ExecutionException | TimeoutException e) {
            throw new DeliveryException(topic, e);
        }
    }

    private void post(String baseUrl, String path, Object payload) {
        if (baseUrl == null || baseUrl.isBlank()) {
            return;
        }
        String url = baseUrl.replaceAll("/+$", "") + path;
        try {
            http.post().uri(url).contentType(MediaType.APPLICATION_JSON).body(payload).retrieve().toBodilessEntity();
        } catch (RuntimeException e) {
            log.warn("inbox POST {} failed: {}", url, e.toString());
            throw new DeliveryException(url, e);
        }
    }

    public static class DeliveryException extends RuntimeException {
        public DeliveryException(String target, Throwable cause) {
            super("could not deliver outcome to " + target, cause);
        }
    }
}
