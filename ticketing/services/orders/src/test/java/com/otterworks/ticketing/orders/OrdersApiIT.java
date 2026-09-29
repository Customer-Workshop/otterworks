package com.otterworks.ticketing.orders;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.otterworks.ticketing.orders.support.IntegrationTestBase;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;

/** Behaviour the monolith never had to expose: idempotent placement and inboxes, hold-based placement, metrics. */
class OrdersApiIT extends IntegrationTestBase {

    @Test
    void sameClientRefReplaysTheOrderWithoutHoldingSeatsAgain() throws Exception {
        String clientRef = "k6-" + UUID.randomUUID();
        Map<String, Object> req = purchaseBody(1, 2, clientRef);
        stubHold(seatsStub.hold("HD-REPLAY0001", 1, 2, null, 0));

        Response first = post("/api/purchase", req);
        Response second = post("/api/purchase", req); // no second seats expectation: a second hold would fail verify()

        assertThat(first.status()).isEqualTo(202);
        assertThat(second.status()).isEqualTo(202);
        assertThat(second.body().path("orderRef").asText()).isEqualTo(first.body().path("orderRef").asText());
        assertThat(count("SELECT count(*) FROM orders WHERE client_ref = :r", clientRef)).isEqualTo(1);
        assertThat(count("SELECT count(*) FROM outbox WHERE aggregate_ref = :r", first.body().path("orderRef").asText()))
                .isEqualTo(1);
    }

    @Test
    void placementWritesOrderItemsFeesAndOutboxRowInOneTransaction() throws Exception {
        stubHold(seatsStub.hold("HD-ATOMIC0001", 1, 2, null, 0));
        Response placed = post("/api/purchase", purchaseBody(1, 2, null));
        String orderRef = placed.body().path("orderRef").asText();

        assertThat(count("SELECT count(*) FROM order_items oi JOIN orders o ON o.id = oi.order_id WHERE o.order_ref = :r", orderRef)).isEqualTo(2);
        assertThat(count("SELECT count(*) FROM order_fees of JOIN orders o ON o.id = of.order_id WHERE o.order_ref = :r", orderRef)).isEqualTo(2);
        String payload = jdbc.sql("SELECT payload::text FROM outbox WHERE aggregate_ref = :r AND published_at IS NULL")
                .param("r", orderRef).query(String.class).single();
        JsonNode event = json.readTree(payload);
        for (String field : List.of("orderRef", "clientRef", "customerEmail", "performanceId", "eventTitle", "venueName",
                "startsAt", "holdRef", "holdExpiresAt", "channel", "items", "fees", "subtotalCents", "feesCents",
                "totalCents", "currency", "cardLast4", "placedAt")) {
            assertThat(event.has(field)).as("order-placed field %s", field).isTrue();
        }
        assertThat(event.path("holdRef").asText()).isEqualTo("HD-ATOMIC0001");
        assertThat(event.path("totalCents").asLong()).isEqualTo(42836);
        assertThat(event.path("items").get(0).has("seatInventoryId")).isTrue();
        assertThat(event.path("items").get(0).has("priceZoneId")).isTrue();
        assertThat(event.path("fees").get(0).path("feeType").asText()).isEqualTo("SERVICE");
        assertThat(event.path("placedAt").asText()).endsWith("Z");
        assertThat(jdbc.sql("SELECT event_name FROM outbox WHERE aggregate_ref = :r").param("r", orderRef)
                .query(String.class).single()).isEqualTo("order-placed");
        assertThat(jdbc.sql("SELECT key FROM outbox WHERE aggregate_ref = :r").param("r", orderRef)
                .query(String.class).single()).isEqualTo(orderRef);
    }

    @Test
    void promoUseIsCountedAtPlacementRegardlessOfPaymentOutcome() throws Exception {
        long before = count("SELECT used_count FROM promo_codes WHERE code = 'HALLNIGHT'", null);
        stubHold(seatsStub.hold("HD-PROMO00001", 1, 2, null, 0));
        Map<String, Object> req = purchaseBody(1, 2, null);
        req.put("promoCode", "HALLNIGHT");
        req.put("cardLast4", "0000");
        Response placed = post("/api/purchase", req);
        assertThat(placed.body().path("totalCents").asLong()).isEqualTo(36486);
        post("/events/payment-failed", failed(placed.body().path("orderRef").asText(), "DECLINED", "PAYMENT_FAILED"));
        assertThat(count("SELECT used_count FROM promo_codes WHERE code = 'HALLNIGHT'", null)).isEqualTo(before + 1);
    }

    @Test
    void demandUpliftFollowsSeatsZoneTally() throws Exception {
        // 10% of P1 gone -> +5%: 18900 * 1.05 = 19845 per seat; 2 seats 39690; +12% 4763; +500 = 44953
        stubHold(seatsStub.hold("HD-UPLIFT0001", 1, 2, null, 398));
        Response placed = post("/api/purchase", purchaseBody(1, 2, null));
        assertThat(placed.body().path("totalCents").asLong()).isEqualTo(44953);
    }

    @Test
    void placeFromExistingHoldAndRejectInactiveHold() throws Exception {
        Map<String, Object> active = seatsStub.hold("HD-FROMHOLD01", 4, 3, null, 0);
        stubHoldLookup("HD-FROMHOLD01", active);
        Map<String, Object> req = new LinkedHashMap<>();
        req.put("holdRef", "HD-FROMHOLD01");
        req.put("email", "hold.orders@example.test");
        req.put("delivery", "PRINT");
        Response placed = post("/api/orders", req);
        assertThat(placed.status()).isEqualTo(202);
        // 3 x 18900 = 56700; service 6804; facility 750; print 150 = 64404
        assertThat(placed.body().path("totalCents").asLong()).isEqualTo(64404);
        Response view = get("/api/orders/" + placed.body().path("orderRef").asText());
        assertThat(view.body().path("fees").size()).isEqualTo(3);
        assertThat(view.body().path("hold_ref").asText()).isEqualTo("HD-FROMHOLD01");

        nextSeatsRound();
        Map<String, Object> expired = seatsStub.hold("HD-FROMHOLD02", 4, 2, null, 0);
        expired.put("status", "EXPIRED");
        expired.put("active", false);
        stubHoldLookup("HD-FROMHOLD02", expired);
        req.put("holdRef", "HD-FROMHOLD02");
        Response gone = post("/api/orders", req);
        assertThat(gone.status()).isEqualTo(410);
        assertThat(gone.body().path("error").asText()).isEqualTo("HOLD_EXPIRED");
    }

    @Test
    void inboxesAreIdempotentAndIgnoreTerminalStates() throws Exception {
        stubHold(seatsStub.hold("HD-INBOX00001", 1, 2, null, 0));
        Response placed = post("/api/purchase", purchaseBody(1, 2, null));
        String orderRef = placed.body().path("orderRef").asText();

        Response first = post("/events/payment-failed", failed(orderRef, "TIMEOUT", "PAYMENT_TIMEOUT"));
        assertThat(first.body().path("applied").asBoolean()).isTrue();
        assertThat(first.body().path("status").asText()).isEqualTo("PAYMENT_TIMEOUT");

        Response replay = post("/events/payment-failed", failed(orderRef, "TIMEOUT", "PAYMENT_TIMEOUT"));
        assertThat(replay.status()).isEqualTo(200);
        assertThat(replay.body().path("applied").asBoolean()).isFalse();

        Response lateConfirm = post("/events/order-confirmed", Map.of("orderRef", orderRef, "tickets", List.of()));
        assertThat(lateConfirm.body().path("applied").asBoolean()).isFalse();
        assertThat(get("/api/orders/" + orderRef).body().path("status").asText()).isEqualTo("PAYMENT_TIMEOUT");
        assertThat(get("/api/orders/" + orderRef).body().path("paymentOutcome").asText()).isEqualTo("TIMEOUT");

        Response unknown = post("/events/payment-failed", failed("BO-UNKNOWN0000", "DECLINED", "PAYMENT_FAILED"));
        assertThat(unknown.status()).isEqualTo(200);
        assertThat(unknown.body().path("known").asBoolean()).isFalse();
    }

    @Test
    void holdExpiredCancelsOnlyPendingOrdersOnThatHold() throws Exception {
        stubHold(seatsStub.hold("HD-EXPIRE0001", 1, 2, null, 0));
        Response pending = post("/api/purchase", purchaseBody(1, 2, null));
        nextSeatsRound();
        stubHold(seatsStub.hold("HD-EXPIRE0002", 1, 2, null, 0));
        Response confirmed = post("/api/purchase", purchaseBody(1, 2, null));
        post("/events/order-confirmed", Map.of("orderRef", confirmed.body().path("orderRef").asText(), "tickets", List.of()));

        Response sweep = post("/events/hold-expired", Map.of("holdRef", "HD-EXPIRE0001", "performanceId", 1,
                "seatInventoryIds", List.of(), "expiredAt", "2026-01-01T00:00:00Z"));
        assertThat(sweep.body().path("cancelled").asInt()).isEqualTo(1);
        Response again = post("/events/hold-expired", Map.of("holdRef", "HD-EXPIRE0001"));
        assertThat(again.body().path("cancelled").asInt()).isZero();
        Response other = post("/events/hold-expired", Map.of("holdRef", "HD-EXPIRE0002"));
        assertThat(other.body().path("cancelled").asInt()).isZero();

        JsonNode view = get("/api/orders/" + pending.body().path("orderRef").asText()).body();
        assertThat(view.path("status").asText()).isEqualTo("CANCELLED");
        assertThat(view.path("paymentOutcome").asText()).isEqualTo("HOLD_EXPIRED");
        assertThat(get("/api/orders/" + confirmed.body().path("orderRef").asText()).body().path("status").asText())
                .isEqualTo("CONFIRMED");
    }

    @Test
    void badRequestsAreRejectedBeforeSeatsIsCalled() throws Exception {
        assertThat(post("/api/purchase", Map.of("email", "no.performance@example.test")).status()).isEqualTo(400);
        assertThat(post("/api/purchase", Map.of("performanceId", 1)).body().path("error").asText()).isEqualTo("BAD_REQUEST");
        assertThat(post("/api/orders", Map.of("email", "no.hold@example.test")).status()).isEqualTo(400);
        assertThat(post("/api/purchase", "[1,2]").status()).isEqualTo(400);
    }

    @Test
    void healthAndPrometheusExposeOutboxMetrics() throws Exception {
        assertThat(get("/actuator/health").status()).isEqualTo(200);
        assertThat(get("/actuator/health/readiness").status()).isEqualTo(200);
        String metrics = mvc.perform(MockMvcRequestBuilders.get("/actuator/prometheus")).andReturn()
                .getResponse().getContentAsString();
        assertThat(metrics).contains("orders_outbox_unpublished");
        assertThat(metrics).contains("orders_outbox_published_total");
        assertThat(metrics).contains("orders_placed_total");
    }

    private Map<String, Object> purchaseBody(long performanceId, int quantity, String clientRef) {
        Map<String, Object> req = new LinkedHashMap<>();
        req.put("performanceId", performanceId);
        req.put("email", "Api.Orders+" + UUID.randomUUID().toString().substring(0, 6) + "@Example.Test");
        req.put("quantity", quantity);
        if (clientRef != null) {
            req.put("clientRef", clientRef);
        }
        return req;
    }

    private static Map<String, Object> failed(String orderRef, String outcome, String orderStatus) {
        Map<String, Object> e = new LinkedHashMap<>();
        e.put("orderRef", orderRef);
        e.put("outcome", outcome);
        e.put("orderStatus", orderStatus);
        return e;
    }

    private long count(String sql, String ref) {
        var q = jdbc.sql(sql);
        if (ref != null) {
            q = q.param("r", ref);
        }
        return q.query(Long.class).single();
    }
}
