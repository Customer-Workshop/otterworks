package com.otterworks.ticketing.seats.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.otterworks.ticketing.seats.support.SeededServiceTest;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseEntity;

/**
 * Event-side contracts: the payment-failed / order-confirmed inboxes reproduce SeatHoldBean.release /
 * ConfirmationBean.confirm idempotently, and the sweep reproduces HoldExpiryBean (<=500 per call) while
 * recording the hold-expired payload with the shared field names.
 */
class InboxAndSweepContractTest extends SeededServiceTest {

    private Map<String, Object> paymentFailed(String orderRef, String holdRef, String outcome) {
        return Map.of("orderRef", orderRef, "holdRef", holdRef, "outcome", outcome,
                "orderStatus", outcome.equals("TIMEOUT") ? "PAYMENT_TIMEOUT" : "PAYMENT_FAILED",
                "amountCents", 42836, "cardLast4", "0000", "attemptNo", 1, "latencyMs", 250, "failedAt", "2026-01-01T00:00:00Z");
    }

    private Map<String, Object> orderConfirmed(String orderRef, String holdRef, long performanceId, int n) {
        return Map.of("orderRef", orderRef, "holdRef", holdRef, "performanceId", performanceId, "ticketCount", n,
                "tickets", List.of(), "recipient", "fan00001@example.test", "confirmedAt", "2026-01-01T00:00:00Z");
    }

    private String newHold(long performanceId, int quantity) {
        ResponseEntity<JsonNode> r = post("/api/holds", hold(performanceId, quantity, null));
        assertThat(r.getStatusCode().value()).isEqualTo(201);
        return r.getBody().get("holdRef").asText();
    }

    @Test
    void getHoldShowsActiveFlagSeatsAndExpiry() {
        String ref = newHold(1, 2);
        JsonNode v = get("/api/holds/" + ref).getBody();
        assertThat(v.get("holdRef").asText()).isEqualTo(ref);
        assertThat(v.get("status").asText()).isEqualTo("ACTIVE");
        assertThat(v.get("active").asBoolean()).isTrue();
        assertThat(v.get("seats")).hasSize(2);
        assertThat(v.get("seats").get(0).get("section").asText()).isEqualTo("A01");
        assertThat(v.get("expiresAt").asText()).isNotBlank();
        // HOLD_MINUTES = 10 as in the monolith
        java.time.Instant exp = java.time.Instant.parse(v.get("expiresAt").asText());
        assertThat(exp).isBetween(java.time.Instant.now().plusSeconds(9 * 60), java.time.Instant.now().plusSeconds(11 * 60));
        assertThat(get("/api/holds/H-NOPE000000").getStatusCode().value()).isEqualTo(404);
    }

    @Test
    void paymentFailedReleasesSeatsAndIsIdempotent() {
        String ref = newHold(1, 3);
        ResponseEntity<JsonNode> first = post("/events/payment-failed", paymentFailed("BO-A1", ref, "DECLINED"));
        assertThat(first.getStatusCode().value()).isEqualTo(200);
        assertThat(first.getBody().get("applied").asBoolean()).isTrue();
        JsonNode v = get("/api/holds/" + ref).getBody();
        assertThat(v.get("status").asText()).isEqualTo("RELEASED");
        assertThat(v.get("active").asBoolean()).isFalse();
        assertThat(get("/api/performances/1/availability").getBody().get("held").asLong()).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM seat_inventory WHERE hold_id IS NOT NULL OR order_ref IS NOT NULL", Long.class)).isZero();

        ResponseEntity<JsonNode> replay = post("/events/payment-failed", paymentFailed("BO-A1", ref, "DECLINED"));
        assertThat(replay.getStatusCode().value()).isEqualTo(200);
        assertThat(replay.getBody().get("applied").asBoolean()).isFalse();
        assertThat(replay.getBody().get("detail").asText()).contains("duplicate");
        assertThat(get("/stats").getBody().get("holdsByStatus").get("RELEASED").asLong()).isEqualTo(1);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM inbox", Long.class)).isEqualTo(1L);
    }

    @Test
    void timeoutOutcomeReleasesLikeDecline() {
        String ref = newHold(1, 2);
        assertThat(post("/events/payment-failed", paymentFailed("BO-T1", ref, "TIMEOUT")).getBody().get("applied").asBoolean()).isTrue();
        assertThat(get("/api/holds/" + ref).getBody().get("status").asText()).isEqualTo("RELEASED");
        assertThat(get("/api/performances/1/availability").getBody().get("available").asLong()).isEqualTo(20_000L);
    }

    @Test
    void orderConfirmedSellsSeatsStampsOrderRefAndIsIdempotent() {
        String ref = newHold(1, 2);
        ResponseEntity<JsonNode> first = post("/events/order-confirmed", orderConfirmed("BO-C1", ref, 1, 2));
        assertThat(first.getBody().get("applied").asBoolean()).isTrue();
        JsonNode v = get("/api/holds/" + ref).getBody();
        assertThat(v.get("status").asText()).isEqualTo("CONVERTED");
        assertThat(v.get("orderRef").asText()).isEqualTo("BO-C1");
        assertThat(get("/api/performances/1/availability").getBody().get("sold").asLong()).isEqualTo(2);
        assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM seat_inventory si JOIN seat_holds h ON h.id = si.hold_id WHERE h.hold_ref = ? AND si.status = 'SOLD' AND si.order_ref = 'BO-C1'",
                Long.class, ref)).isEqualTo(2L);

        ResponseEntity<JsonNode> replay = post("/events/order-confirmed", orderConfirmed("BO-C1", ref, 1, 2));
        assertThat(replay.getBody().get("applied").asBoolean()).isFalse();
        assertThat(get("/api/performances/1/availability").getBody().get("sold").asLong()).isEqualTo(2);
        // a late payment-failed for a converted hold is ignored, seats stay SOLD
        assertThat(post("/events/payment-failed", paymentFailed("BO-C1", ref, "DECLINED")).getBody().get("applied").asBoolean()).isFalse();
        assertThat(get("/api/performances/1/availability").getBody().get("sold").asLong()).isEqualTo(2);
    }

    @Test
    void orderConfirmedForAnExpiredHoldIsIgnored() {
        String ref = newHold(1, 2);
        jdbc.update("UPDATE seat_holds SET expires_at = now() - interval '1 minute' WHERE hold_ref = ?", ref);
        assertThat(get("/api/holds/" + ref).getBody().get("active").asBoolean()).isFalse();
        assertThat(post("/api/holds/sweep", null).getBody().get("released").asInt()).isEqualTo(1);
        ResponseEntity<JsonNode> r = post("/events/order-confirmed", orderConfirmed("BO-L1", ref, 1, 2));
        assertThat(r.getStatusCode().value()).isEqualTo(200);
        assertThat(r.getBody().get("applied").asBoolean()).isFalse();
        assertThat(get("/api/holds/" + ref).getBody().get("status").asText()).isEqualTo("EXPIRED");
        assertThat(get("/api/performances/1/availability").getBody().get("sold").asLong()).isZero();
    }

    @Test
    void inboxRejectsPayloadsWithoutKeys() {
        ResponseEntity<JsonNode> r = post("/events/payment-failed", Map.of("holdRef", "H-X"));
        assertThat(r.getStatusCode().value()).isEqualTo(400);
        assertThat(r.getBody().get("error").asText()).isEqualTo("BAD_REQUEST");
        assertThat(postRaw("/api/holds", "{not json").getStatusCode().value()).isEqualTo(400);
    }

    @Test
    void sweepRecordsHoldExpiredWithContractPayloadAndKey() throws Exception {
        String plain = newHold(1, 2);
        String withOrder = newHold(1, 1);
        assertThat(post("/api/holds/" + withOrder + "/order", Map.of("orderRef", "BO-PENDING")).getBody().get("attached").asBoolean()).isTrue();
        jdbc.update("UPDATE seat_holds SET expires_at = now() - interval '1 minute' WHERE status = 'ACTIVE'");
        assertThat(post("/api/holds/sweep", null).getBody().get("released").asInt()).isEqualTo(2);

        List<Map<String, Object>> events = jdbc.queryForList("""
                SELECT h.hold_ref, e.event_key, e.payload::text AS payload, e.kafka_published_at, e.orders_delivered_at
                FROM hold_expired_events e JOIN seat_holds h ON h.id = e.hold_id ORDER BY h.id""");
        assertThat(events).hasSize(2);
        JsonNode p0 = json.readTree((String) events.get(0).get("payload"));
        assertThat(events.get(0).get("event_key")).isEqualTo(plain);
        assertThat(p0.fieldNames()).toIterable().containsExactlyInAnyOrder("holdRef", "performanceId", "orderRef", "seatInventoryIds", "expiredAt");
        assertThat(p0.get("holdRef").asText()).isEqualTo(plain);
        assertThat(p0.get("performanceId").asLong()).isEqualTo(1);
        assertThat(p0.get("orderRef").isNull()).isTrue();
        assertThat(p0.get("seatInventoryIds")).hasSize(2);
        assertThat(p0.get("expiredAt").asText()).endsWith("Z");

        JsonNode p1 = json.readTree((String) events.get(1).get("payload"));
        assertThat(events.get(1).get("event_key")).isEqualTo("BO-PENDING");
        assertThat(p1.get("orderRef").asText()).isEqualTo("BO-PENDING");
        // both legs disabled in the test profile count as delivered; nothing stays pending
        events.forEach(e -> {
            assertThat(e.get("kafka_published_at")).isNotNull();
            assertThat(e.get("orders_delivered_at")).isNotNull();
        });
        JsonNode stats = get("/stats").getBody();
        assertThat(stats.get("holdExpiredPending").asLong()).isZero();
        assertThat(stats.get("holdsByStatus").get("EXPIRED").asLong()).isEqualTo(2);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM seat_inventory WHERE order_ref = 'BO-PENDING'", Long.class)).isZero();
    }

    @Test
    void sweepReleasesAtMostFiveHundredHoldsPerCall() {
        // 501 single-seat ACTIVE holds on performance 2, already past their expiry
        jdbc.update("""
                INSERT INTO seat_holds (hold_ref, performance_id, status, expires_at)
                SELECT 'H-EXP' || lpad(g::text, 6, '0'), 2, 'ACTIVE', now() - interval '5 minutes' FROM generate_series(1, 501) g""");
        jdbc.update("""
                WITH picked AS (
                  SELECT si.id AS si_id, h.id AS hold_id
                  FROM (SELECT id, row_number() OVER (ORDER BY id) AS rn FROM seat_inventory WHERE performance_id = 2 AND status = 'AVAILABLE' LIMIT 501) x
                  JOIN seat_inventory si ON si.id = x.id
                  JOIN (SELECT id, row_number() OVER (ORDER BY id) AS rn FROM seat_holds WHERE hold_ref LIKE 'H-EXP%') h ON h.rn = x.rn),
                upd AS (UPDATE seat_inventory si SET status = 'HELD', hold_id = p.hold_id FROM picked p WHERE si.id = p.si_id RETURNING si.id)
                INSERT INTO seat_hold_items (hold_id, seat_inventory_id) SELECT hold_id, si_id FROM picked""");
        assertThat(get("/api/performances/2/availability").getBody().get("held").asLong()).isEqualTo(501);

        assertThat(post("/api/holds/sweep", null).getBody().get("released").asInt()).isEqualTo(500);
        assertThat(get("/api/performances/2/availability").getBody().get("held").asLong()).isEqualTo(1);
        assertThat(post("/api/holds/sweep", null).getBody().get("released").asInt()).isEqualTo(1);
        assertThat(get("/api/performances/2/availability").getBody().get("held").asLong()).isZero();
        assertThat(post("/api/holds/sweep", null).getBody().get("released").asInt()).isZero();
        assertThat(get("/stats").getBody().get("holdsByStatus").get("EXPIRED").asLong()).isEqualTo(501);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM hold_expired_events", Long.class)).isEqualTo(501L);
    }

    @Test
    void prometheusExposesSeatMetrics() {
        newHold(1, 1);
        ResponseEntity<String> r = http.getForEntity("/actuator/prometheus", String.class);
        assertThat(r.getStatusCode().value()).isEqualTo(200);
        assertThat(r.getBody()).contains("seats_holds_placed_total");
        assertThat(r.getBody()).contains("http_server_requests_seconds");
        assertThat(r.getBody()).contains("application=\"seats\"");
    }
}
