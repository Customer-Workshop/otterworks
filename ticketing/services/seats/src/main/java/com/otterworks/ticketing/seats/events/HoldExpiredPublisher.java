package com.otterworks.ticketing.seats.events;

import com.otterworks.ticketing.seats.config.SeatsProperties;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.http.MediaType;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/**
 * The two legs of the hold-expired delivery rule: the Kafka record on {@code <token>-hold-expired}
 * (durable fact, read by dashboards and future monolith adapters) and the HTTP inbox
 * {@code POST /events/hold-expired} on orders. Each leg reports success independently.
 */
@Component
public class HoldExpiredPublisher {

    private static final Logger LOG = LoggerFactory.getLogger(HoldExpiredPublisher.class);

    private final SeatsProperties props;
    private final ObjectProvider<KafkaTemplate<String, String>> kafka;
    private final RestClient orders;
    private final Counter kafkaOk;
    private final Counter kafkaFailed;
    private final Counter ordersOk;
    private final Counter ordersFailed;

    public HoldExpiredPublisher(SeatsProperties props, ObjectProvider<KafkaTemplate<String, String>> kafka,
                                RestClient ordersRestClient, MeterRegistry registry) {
        this.props = props;
        this.kafka = kafka;
        this.orders = ordersRestClient;
        this.kafkaOk = registry.counter("seats_hold_expired_published_total", "leg", "kafka", "result", "ok");
        this.kafkaFailed = registry.counter("seats_hold_expired_published_total", "leg", "kafka", "result", "failed");
        this.ordersOk = registry.counter("seats_hold_expired_published_total", "leg", "orders", "result", "ok");
        this.ordersFailed = registry.counter("seats_hold_expired_published_total", "leg", "orders", "result", "failed");
    }

    public boolean publish(String key, String payload) {
        if (!props.kafka().enabled()) {
            return true;
        }
        KafkaTemplate<String, String> template = kafka.getIfAvailable();
        if (template == null) {
            LOG.warn("kafka enabled but no KafkaTemplate available");
            kafkaFailed.increment();
            return false;
        }
        try {
            template.send(props.kafka().topicHoldExpired(), key, payload).get(10, TimeUnit.SECONDS);
            kafkaOk.increment();
            return true;
        } catch (Exception e) {
            LOG.warn("hold-expired kafka publish failed for key {}: {}", key, e.toString());
            kafkaFailed.increment();
            return false;
        }
    }

    public boolean deliverToOrders(String payload) {
        if (!props.orders().enabled()) {
            return true;
        }
        try {
            orders.post().uri("/events/hold-expired")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(payload)
                    .retrieve()
                    .toBodilessEntity();
            ordersOk.increment();
            return true;
        } catch (Exception e) {
            LOG.warn("hold-expired delivery to orders failed: {}", e.toString());
            ordersFailed.increment();
            return false;
        }
    }
}
