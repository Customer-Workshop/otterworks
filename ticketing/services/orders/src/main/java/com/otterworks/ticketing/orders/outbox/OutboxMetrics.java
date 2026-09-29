package com.otterworks.ticketing.orders.outbox;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;

/** orders_outbox_unpublished (gauge, read from the table on scrape) and orders_outbox_published_total (counter). */
@Component
public class OutboxMetrics {

    private static final Duration CACHE_TTL = Duration.ofSeconds(2);

    private final OutboxRepository outbox;
    private final Counter published;
    private final Counter placed;
    private final AtomicLong cachedUnpublished = new AtomicLong();
    private volatile Instant cachedAt = Instant.EPOCH;

    public OutboxMetrics(OutboxRepository outbox, MeterRegistry registry) {
        this.outbox = outbox;
        Gauge.builder("orders.outbox.unpublished", this, OutboxMetrics::unpublished)
                .description("Outbox rows not yet published to Kafka").register(registry);
        this.published = Counter.builder("orders.outbox.published")
                .description("Outbox rows published to Kafka by this relay").register(registry);
        this.placed = Counter.builder("orders.placed")
                .description("Orders placed (PENDING_PAYMENT written with an outbox row)").register(registry);
    }

    public double unpublished() {
        Instant now = Instant.now();
        if (Duration.between(cachedAt, now).compareTo(CACHE_TTL) > 0) {
            try {
                cachedUnpublished.set(outbox.countUnpublished());
            } catch (RuntimeException e) {
                return Double.NaN;
            }
            cachedAt = now;
        }
        return cachedUnpublished.get();
    }

    public void published(int count) {
        published.increment(count);
    }

    public void placed() {
        placed.increment();
    }
}
