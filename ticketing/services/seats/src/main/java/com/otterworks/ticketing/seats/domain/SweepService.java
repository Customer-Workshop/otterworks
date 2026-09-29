package com.otterworks.ticketing.seats.domain;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.otterworks.ticketing.seats.config.SeatsProperties;
import com.otterworks.ticketing.seats.domain.Dtos.HoldExpired;
import com.otterworks.ticketing.seats.domain.Dtos.SweepResult;
import com.otterworks.ticketing.seats.events.HoldExpiredPublisher;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * HoldExpiryBean.releaseExpired as an endpoint: expire up to {@code sweepBatchSize} ACTIVE holds whose
 * expires_at has passed, in one transaction that also records one hold-expired event per hold. After
 * commit every pending event (this batch plus earlier failures) is published to Kafka and delivered to
 * the orders inbox; whatever fails stays pending and is retried by the next sweep (at-least-once).
 */
@Service
public class SweepService {

    private static final Logger LOG = LoggerFactory.getLogger(SweepService.class);

    private final JdbcTemplate jdbc;
    private final TransactionTemplate tx;
    private final HoldService holds;
    private final HoldExpiredPublisher publisher;
    private final SeatsProperties props;
    private final ObjectMapper json;
    private final Counter expired;

    public SweepService(JdbcTemplate jdbc, TransactionTemplate tx, HoldService holds, HoldExpiredPublisher publisher,
                        SeatsProperties props, ObjectMapper json, MeterRegistry registry) {
        this.jdbc = jdbc;
        this.tx = tx;
        this.holds = holds;
        this.publisher = publisher;
        this.props = props;
        this.json = json;
        this.expired = registry.counter("seats_holds_expired_total");
    }

    public SweepResult sweep() {
        Integer released = tx.execute(status -> expireBatch());
        int n = released == null ? 0 : released;
        expired.increment(n);
        if (n > 0) {
            LOG.info("released {} expired holds", n);
        }
        deliverPending();
        return new SweepResult(n);
    }

    int expireBatch() {
        List<Map<String, Object>> rows = holds.expiredActiveHolds(props.sweepBatchSize());
        Instant now = Instant.now();
        for (Map<String, Object> h : rows) {
            long holdId = ((Number) h.get("id")).longValue();
            String orderRef = (String) h.get("order_ref");
            List<Long> seatIds = holds.releaseLocked(holdId, "EXPIRED");
            HoldExpired event = new HoldExpired((String) h.get("hold_ref"),
                    ((Number) h.get("performance_id")).longValue(), orderRef, seatIds, now);
            String key = orderRef != null ? orderRef : event.holdRef();
            jdbc.update("""
                    INSERT INTO hold_expired_events (hold_id, event_key, payload) VALUES (?, ?, ?::jsonb)
                    ON CONFLICT (hold_id) DO NOTHING""", holdId, key, write(event));
        }
        return rows.size();
    }

    /** Publish/deliver every event that has not yet completed both legs; each leg is stamped independently. */
    public void deliverPending() {
        List<Map<String, Object>> pending = jdbc.queryForList("""
                SELECT hold_id, event_key, payload::text AS payload, kafka_published_at, orders_delivered_at
                FROM hold_expired_events
                WHERE kafka_published_at IS NULL OR orders_delivered_at IS NULL
                ORDER BY created_at LIMIT ?""", props.sweepBatchSize());
        for (Map<String, Object> e : pending) {
            long holdId = ((Number) e.get("hold_id")).longValue();
            String key = (String) e.get("event_key");
            String payload = (String) e.get("payload");
            jdbc.update("UPDATE hold_expired_events SET attempts = attempts + 1 WHERE hold_id = ?", holdId);
            if (e.get("kafka_published_at") == null && publisher.publish(key, payload)) {
                jdbc.update("UPDATE hold_expired_events SET kafka_published_at = now() WHERE hold_id = ?", holdId);
            }
            if (e.get("orders_delivered_at") == null && publisher.deliverToOrders(payload)) {
                jdbc.update("UPDATE hold_expired_events SET orders_delivered_at = now() WHERE hold_id = ?", holdId);
            }
        }
    }

    private String write(HoldExpired event) {
        try {
            return json.writeValueAsString(event);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(ex);
        }
    }
}
