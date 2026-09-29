package com.otterworks.ticketing.seats.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "seats")
public record SeatsProperties(int holdMinutes, int sweepBatchSize, String token, Kafka kafka, Orders orders) {

    public record Kafka(boolean enabled, String topicHoldExpired) {
    }

    public record Orders(boolean enabled, String baseUrl, int timeoutMs) {
    }
}
