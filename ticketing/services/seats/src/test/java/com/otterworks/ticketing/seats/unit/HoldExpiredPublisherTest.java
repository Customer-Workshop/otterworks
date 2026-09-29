package com.otterworks.ticketing.seats.unit;

import static org.assertj.core.api.Assertions.assertThat;

import com.otterworks.ticketing.seats.config.SeatsProperties;
import com.otterworks.ticketing.seats.events.HoldExpiredPublisher;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.web.client.RestClient;

class HoldExpiredPublisherTest {

    private static final ObjectProvider<KafkaTemplate<String, String>> NO_KAFKA = new ObjectProvider<>() {
        @Override
        public KafkaTemplate<String, String> getObject(Object... args) {
            return null;
        }

        @Override
        public KafkaTemplate<String, String> getIfAvailable() {
            return null;
        }

        @Override
        public KafkaTemplate<String, String> getIfUnique() {
            return null;
        }

        @Override
        public KafkaTemplate<String, String> getObject() {
            return null;
        }
    };

    private static SeatsProperties props(boolean kafka, boolean orders, String ordersUrl) {
        return new SeatsProperties(10, 500, "tkt01",
                new SeatsProperties.Kafka(kafka, "tkt01-hold-expired"),
                new SeatsProperties.Orders(orders, ordersUrl, 300));
    }

    @Test
    void disabledLegsCountAsDelivered() {
        var p = new HoldExpiredPublisher(props(false, false, "http://localhost:1"), NO_KAFKA,
                RestClient.builder().baseUrl("http://localhost:1").build(), new SimpleMeterRegistry());
        assertThat(p.publish("H-X", "{}")).isTrue();
        assertThat(p.deliverToOrders("{}")).isTrue();
    }

    @Test
    void kafkaEnabledWithoutTemplateFails() {
        var registry = new SimpleMeterRegistry();
        var p = new HoldExpiredPublisher(props(true, false, "http://localhost:1"), NO_KAFKA,
                RestClient.builder().baseUrl("http://localhost:1").build(), registry);
        assertThat(p.publish("H-X", "{}")).isFalse();
        assertThat(registry.counter("seats_hold_expired_published_total", "leg", "kafka", "result", "failed").count()).isEqualTo(1.0);
    }

    @Test
    void unreachableOrdersInboxFailsSoftly() {
        var registry = new SimpleMeterRegistry();
        var p = new HoldExpiredPublisher(props(false, true, "http://localhost:1"), NO_KAFKA,
                RestClient.builder().baseUrl("http://localhost:1").build(), registry);
        assertThat(p.deliverToOrders("{\"holdRef\":\"H-X\"}")).isFalse();
        assertThat(registry.counter("seats_hold_expired_published_total", "leg", "orders", "result", "failed").count()).isEqualTo(1.0);
    }
}
