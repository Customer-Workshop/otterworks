package com.otterworks.ticketing.seats.events;

import com.fasterxml.jackson.databind.JsonNode;
import com.otterworks.ticketing.seats.domain.Dtos.InboxResult;
import com.otterworks.ticketing.seats.domain.HoldService;
import com.otterworks.ticketing.seats.domain.SeatsException;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.List;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * HTTP inboxes for the events seats consumes. Idempotent on (event, orderRef): the inbox row is
 * inserted in the same transaction as the state change, so a replay finds the row and is acknowledged
 * as a duplicate without touching inventory.
 */
@Service
public class InboxService {

    private static final Logger LOG = LoggerFactory.getLogger(InboxService.class);
    public static final String PAYMENT_FAILED = "payment-failed";
    public static final String ORDER_CONFIRMED = "order-confirmed";

    private final JdbcTemplate jdbc;
    private final HoldService holds;
    private final MeterRegistry registry;

    public InboxService(JdbcTemplate jdbc, HoldService holds, MeterRegistry registry) {
        this.jdbc = jdbc;
        this.holds = holds;
        this.registry = registry;
    }

    /** payment-failed: the hold is RELEASED and its HELD seats return to AVAILABLE with order_ref cleared. */
    @Transactional
    public InboxResult paymentFailed(JsonNode payload) {
        String orderRef = required(payload, "orderRef");
        String holdRef = required(payload, "holdRef");
        if (!claim(PAYMENT_FAILED, orderRef, payload)) {
            return duplicate(PAYMENT_FAILED, orderRef);
        }
        Optional<List<Long>> released = holds.release(holdRef, "RELEASED");
        if (released.isEmpty()) {
            LOG.warn("payment-failed for {} but hold {} is not ACTIVE; ignored", orderRef, holdRef);
        }
        return done(PAYMENT_FAILED, orderRef, released.isPresent(),
                released.map(ids -> ids.size() + " seats released").orElse("hold not ACTIVE; ignored"));
    }

    /** order-confirmed: the hold is CONVERTED and its seats SOLD with order_ref stamped. */
    @Transactional
    public InboxResult orderConfirmed(JsonNode payload) {
        String orderRef = required(payload, "orderRef");
        String holdRef = required(payload, "holdRef");
        if (!claim(ORDER_CONFIRMED, orderRef, payload)) {
            return duplicate(ORDER_CONFIRMED, orderRef);
        }
        boolean applied = holds.convert(holdRef, orderRef);
        if (!applied) {
            LOG.warn("order-confirmed for {} but hold {} is not ACTIVE; ignored", orderRef, holdRef);
        }
        return done(ORDER_CONFIRMED, orderRef, applied, applied ? "hold converted, seats sold" : "hold not ACTIVE; ignored");
    }

    private boolean claim(String event, String key, JsonNode payload) {
        int inserted = jdbc.update("""
                INSERT INTO inbox (event_name, event_key, payload, applied) VALUES (?, ?, ?::jsonb, false)
                ON CONFLICT (event_name, event_key) DO NOTHING""", event, key, payload.toString());
        return inserted == 1;
    }

    private InboxResult done(String event, String key, boolean applied, String detail) {
        jdbc.update("UPDATE inbox SET applied = ? WHERE event_name = ? AND event_key = ?", applied, event, key);
        registry.counter("seats_inbox_events_total", "event", event, "result", applied ? "applied" : "ignored").increment();
        return new InboxResult(event, key, applied, detail);
    }

    private InboxResult duplicate(String event, String key) {
        registry.counter("seats_inbox_events_total", "event", event, "result", "duplicate").increment();
        return new InboxResult(event, key, false, "duplicate; already processed");
    }

    private static String required(JsonNode payload, String field) {
        JsonNode v = payload == null ? null : payload.get(field);
        if (v == null || v.isNull() || v.asText().isBlank()) {
            throw SeatsException.badRequest(field + " is required");
        }
        return v.asText();
    }
}
