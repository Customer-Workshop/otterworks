package com.otterworks.ticketing.orders.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "orders")
public record OrdersProperties(String token, String channel, Seats seats, Relay relay) {

    public record Seats(String baseUrl, Duration connectTimeout, Duration readTimeout) {
    }

    public record Relay(boolean enabled, Duration pollInterval, int batchSize, Duration sendTimeout) {
    }

    /** Kafka topic for an event name, e.g. {@code tkt01-order-placed}. */
    public String topicFor(String eventName) {
        return token + "-" + eventName;
    }
}
