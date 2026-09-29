package com.boxoffice.payments.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Runtime knobs. Gateway names and defaults are the monolith's (PAYMENT_TIMEOUT_MS, GATEWAY_MIN_MS,
 * GATEWAY_MAX_MS, GATEWAY_DECLINE_PCT); topics carry the run token prefix from CONVENTIONS.md.
 */
@ConfigurationProperties(prefix = "payments")
public record PaymentsProperties(String token, Topics topics, Inbox inbox, Gateway gateway) {

    public record Topics(String orderPlaced, String paymentCaptured, String paymentFailed) {
    }

    /** Base URLs of the HTTP inboxes; an empty URL disables that delivery (local runs). */
    public record Inbox(String confirmationsUrl, String ordersUrl, String seatsUrl) {
    }

    public record Gateway(int timeoutMs, int minMs, int maxMs, int declinePct) {
    }
}
