package com.otterworks.ticketing.orders.outbox;

import com.otterworks.ticketing.orders.config.OrdersProperties;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * Drains the outbox to Kafka in id order: lock a batch (FOR UPDATE SKIP LOCKED), send the records with
 * acks=all, wait for every broker acknowledgement, stamp published_at, commit. A failed send rolls the
 * batch back, so rows stay unpublished and are retried on the next tick (at-least-once; consumers are
 * idempotent on the key). Runs only where {@code orders.relay.enabled=true} (the KEDA-scaled relay
 * Deployment), so it keeps draining while the request-driven Knative service is scaled to zero.
 */
@Component
@ConditionalOnProperty(prefix = "orders.relay", name = "enabled", havingValue = "true")
public class OutboxRelay {

    private static final Logger log = LoggerFactory.getLogger(OutboxRelay.class);

    private final OutboxRepository outbox;
    private final KafkaTemplate<String, String> kafka;
    private final TransactionTemplate tx;
    private final OrdersProperties props;
    private final OutboxMetrics metrics;

    public OutboxRelay(OutboxRepository outbox, KafkaTemplate<String, String> kafka, TransactionTemplate tx,
                       OrdersProperties props, OutboxMetrics metrics) {
        this.outbox = outbox;
        this.kafka = kafka;
        this.tx = tx;
        this.props = props;
        this.metrics = metrics;
    }

    @Scheduled(fixedDelayString = "${orders.relay.poll-interval:500ms}", initialDelayString = "2s")
    public void tick() {
        int batch = props.relay().batchSize();
        int published;
        do {
            published = drainBatch(batch);
        } while (published == batch);
    }

    /** Publishes one locked batch; returns how many rows were published (0 when idle or on failure). */
    public int drainBatch(int limit) {
        try {
            Integer count = tx.execute(status -> {
                List<OutboxRepository.OutboxRow> rows = outbox.lockUnpublished(limit);
                // sends are pipelined (idempotent producer keeps per-partition order); acks are awaited in id order
                List<CompletableFuture<SendResult<String, String>>> acks = new ArrayList<>(rows.size());
                for (OutboxRepository.OutboxRow row : rows) {
                    acks.add(kafka.send(props.topicFor(row.eventName()), row.key(), row.payload()));
                }
                for (int i = 0; i < rows.size(); i++) {
                    await(rows.get(i), acks.get(i));
                    outbox.markPublished(rows.get(i).id());
                }
                return rows.size();
            });
            int n = count == null ? 0 : count;
            if (n > 0) {
                metrics.published(n);
                log.info("outbox relay published {} row(s)", n);
            }
            return n;
        } catch (RuntimeException e) {
            log.warn("outbox relay batch failed, will retry: {}", e.toString());
            return 0;
        }
    }

    private void await(OutboxRepository.OutboxRow row, CompletableFuture<SendResult<String, String>> ack) {
        String topic = props.topicFor(row.eventName());
        try {
            ack.get(props.relay().sendTimeout().toMillis(), TimeUnit.MILLISECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("interrupted while publishing outbox row " + row.id(), e);
        } catch (ExecutionException | TimeoutException e) {
            throw new IllegalStateException("publish of outbox row " + row.id() + " to " + topic + " failed", e);
        }
    }
}
