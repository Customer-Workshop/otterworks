package com.boxoffice.payments.service;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;
import java.util.function.Supplier;
import org.springframework.stereotype.Component;

/**
 * Prometheus names: payments_gateway_latency_seconds{outcome} histogram, payments_duplicates_suppressed_total,
 * payments_inbox_deliveries_total{target,result}, payments_inbox_deliveries_pending gauge.
 */
@Component
public class PaymentMetrics {

    private final MeterRegistry registry;
    private final Counter duplicatesSuppressed;

    public PaymentMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.duplicatesSuppressed = Counter.builder("payments.duplicates.suppressed")
                .description("order-placed records redelivered for an order that already has a payment")
                .register(registry);
    }

    public void gatewayLatency(String outcome, int latencyMs) {
        Timer.builder("payments.gateway.latency")
                .description("simulated card gateway round-trip")
                .tag("outcome", outcome)
                .publishPercentileHistogram()
                .register(registry)
                .record(Duration.ofMillis(latencyMs));
    }

    public void outcome(String status) {
        registry.counter("payments.outcomes", "status", status).increment();
    }

    public void duplicateSuppressed() {
        duplicatesSuppressed.increment();
    }

    public void delivery(String target, String result) {
        registry.counter("payments.inbox.deliveries", "target", target, "result", result).increment();
    }

    public void pendingDeliveries(Supplier<Number> pending) {
        registry.gauge("payments.inbox.deliveries.pending", pending, s -> s.get().doubleValue());
    }
}
