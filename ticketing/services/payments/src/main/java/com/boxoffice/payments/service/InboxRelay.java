package com.boxoffice.payments.service;

import com.boxoffice.payments.config.PaymentsProperties;
import com.boxoffice.payments.domain.OutcomeDelivery;
import com.boxoffice.payments.repo.DeliveryRepository;
import jakarta.annotation.PreDestroy;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.client.RestClient;

/**
 * Drains outcome_deliveries: every replica leases a batch of due rows ({@code FOR UPDATE SKIP LOCKED}), POSTs each
 * payload to its inbox with bounded connect/read timeouts, and either marks it delivered or schedules the next
 * attempt with exponential backoff. After {@code payments.relay.max-attempts} the row is abandoned (given_up_at) and
 * the Kafka record stays the durable outcome. A replica that dies mid-batch simply lets its leases expire.
 */
@Component
public class InboxRelay {

    private static final Logger log = LoggerFactory.getLogger(InboxRelay.class);

    private final DeliveryRepository deliveries;
    private final OutcomeOutbox outbox;
    private final RestClient http;
    private final PaymentMetrics metrics;
    private final Clock clock;
    private final TransactionTemplate tx;
    private final PaymentsProperties.Relay cfg;
    private final ExecutorService pool;

    public InboxRelay(DeliveryRepository deliveries, OutcomeOutbox outbox, RestClient inboxRestClient, PaymentMetrics metrics,
                      Clock clock, TransactionTemplate tx, PaymentsProperties props) {
        this.deliveries = deliveries;
        this.outbox = outbox;
        this.http = inboxRestClient;
        this.metrics = metrics;
        this.clock = clock;
        this.tx = tx;
        this.cfg = props.relay();
        this.pool = Executors.newFixedThreadPool(Math.max(1, cfg.threads()), r -> {
            Thread t = new Thread(r, "inbox-relay");
            t.setDaemon(true);
            return t;
        });
        metrics.pendingDeliveries(deliveries::pendingCount);
    }

    @Scheduled(fixedDelayString = "${payments.relay.poll-ms}")
    public void relayDue() {
        List<OutcomeDelivery> batch;
        do {
            batch = claim();
            if (batch.isEmpty()) {
                return;
            }
            deliver(batch);
        } while (batch.size() == cfg.batchSize());
    }

    /** Visible for tests: one leased batch, delivered synchronously; returns how many rows were taken. */
    public int relayOnce() {
        List<OutcomeDelivery> batch = claim();
        deliver(batch);
        return batch.size();
    }

    private List<OutcomeDelivery> claim() {
        Instant now = clock.instant();
        List<OutcomeDelivery> claimed = tx.execute(s -> deliveries.claim(cfg.batchSize(), now, now.plusMillis(cfg.leaseMs())));
        return claimed == null ? List.of() : claimed;
    }

    private void deliver(List<OutcomeDelivery> batch) {
        List<Callable<Void>> work = new ArrayList<>(batch.size());
        for (OutcomeDelivery d : batch) {
            work.add(() -> { deliverOne(d); return null; });
        }
        try {
            for (Future<Void> f : pool.invokeAll(work)) {
                try {
                    f.get();
                } catch (ExecutionException e) {
                    log.error("relay task failed", e.getCause());
                }
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private void deliverOne(OutcomeDelivery d) {
        String url = outbox.urlFor(d.target(), d.event());
        if (url == null) {
            deliveries.markDelivered(d.id(), clock.instant());
            return;
        }
        try {
            http.post().uri(url).contentType(MediaType.APPLICATION_JSON).body(d.payload()).retrieve().toBodilessEntity();
        } catch (RuntimeException e) {
            failed(d, url, e);
            return;
        }
        deliveries.markDelivered(d.id(), clock.instant());
        metrics.delivery(d.target().name(), "delivered");
        log.info("delivered {} for {} to {} (attempt {})", d.event(), d.orderRef(), d.target(), d.attempts() + 1);
    }

    private void failed(OutcomeDelivery d, String url, RuntimeException e) {
        int attempt = d.attempts() + 1;
        Instant now = clock.instant();
        if (attempt >= cfg.maxAttempts()) {
            deliveries.markGivenUp(d.id(), now, e.toString());
            metrics.delivery(d.target().name(), "given_up");
            log.error("giving up on {} for {} after {} attempts: {}", d.event(), d.orderRef(), attempt, e.toString());
            return;
        }
        Duration backoff = backoff(attempt);
        deliveries.markFailed(d.id(), now.plus(backoff), e.toString());
        metrics.delivery(d.target().name(), "retry");
        log.warn("inbox POST {} failed (attempt {}), retrying in {}: {}", url, attempt, backoff, e.toString());
    }

    Duration backoff(int attempt) {
        long ms = cfg.backoffMs() << Math.min(attempt - 1, 20);
        return Duration.ofMillis(Math.min(Math.max(ms, cfg.backoffMs()), cfg.maxBackoffMs()));
    }

    @PreDestroy
    void shutdown() {
        pool.shutdownNow();
    }
}
