package com.otterworks.ticketing.seats.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.otterworks.ticketing.seats.support.SeededServiceTest;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseEntity;

/**
 * Contract tests: the monolith's recorded behaviour on the same synthetic seed
 * (src/test/resources/contracts) must be reproduced by the seats service.
 * Purchases in the monolith are replayed here as hold + inbox event (order-confirmed / payment-failed).
 */
class HoldsApiContractTest extends SeededServiceTest {

    private static List<String> labels(JsonNode seats, String section, String row, String number) {
        List<String> out = new ArrayList<>();
        seats.forEach(s -> out.add(s.get(section).asText() + "/" + s.get(row).asText() + "/" + s.get(number).asInt()));
        return out;
    }

    private void assertError(ResponseEntity<JsonNode> actual, JsonNode fixture) {
        assertThat(actual.getStatusCode().value()).isEqualTo(fixture.get("response").get("status").asInt());
        assertThat(actual.getBody().get("error").asText()).isEqualTo(fixture.get("response").get("body").get("error").asText());
        assertThat(actual.getBody().get("message").asText()).isEqualTo(fixture.get("response").get("body").get("message").asText());
    }

    private void assertAvailability(long performanceId, JsonNode fixture) {
        ResponseEntity<JsonNode> r = get("/api/performances/" + performanceId + "/availability");
        assertThat(r.getStatusCode().value()).isEqualTo(fixture.get("response").get("status").asInt());
        assertThat(r.getBody()).isEqualTo(fixture.get("response").get("body"));
    }

    private String holdAndConfirm(long performanceId, int quantity, String section, String orderRef, JsonNode expectedOrder) {
        ResponseEntity<JsonNode> r = post("/api/holds", hold(performanceId, quantity, section));
        assertThat(r.getStatusCode().value()).isEqualTo(201);
        JsonNode body = r.getBody();
        assertThat(labels(body.get("seats"), "section", "rowLabel", "seatNumber"))
                .isEqualTo(labels(expectedOrder.get("response").get("body").get("items"), "section", "row_label", "seat_number"));
        List<String> zones = new ArrayList<>();
        body.get("seats").forEach(s -> zones.add(s.get("zoneName").asText()));
        List<String> expectedZones = new ArrayList<>();
        expectedOrder.get("response").get("body").get("items").forEach(i -> expectedZones.add(i.get("zone").asText()));
        assertThat(zones).isEqualTo(expectedZones);
        String holdRef = body.get("holdRef").asText();
        ResponseEntity<JsonNode> c = post("/events/order-confirmed", Map.of("orderRef", orderRef, "holdRef", holdRef,
                "performanceId", performanceId, "ticketCount", quantity, "tickets", List.of(), "recipient", "fan@example.test",
                "confirmedAt", "2026-01-01T00:00:00Z"));
        assertThat(c.getStatusCode().value()).isEqualTo(200);
        assertThat(c.getBody().get("applied").asBoolean()).isTrue();
        return holdRef;
    }

    @Test
    void unknownPerformanceIs404NotFound() {
        assertError(post("/api/holds", hold(999, 2, null)), contract("purchase_unknown_performance"));
    }

    @Test
    void quantityBelowOneOrAboveMaxPerOrderIs400BadQuantity() {
        assertError(post("/api/holds", hold(1, 0, null)), contract("purchase_quantity_zero"));
        assertError(post("/api/holds", hold(1, 9, null)), contract("purchase_quantity_over_max"));
    }

    @Test
    void unknownSectionIs409SoldOut() {
        assertError(post("/api/holds", hold(1, 2, "ZZ9")), contract("purchase_unknown_section_sold_out"));
        // a failed hold changes nothing
        assertAvailability(1, wrap(contract("availability_seed_all_performances").get("performances").get(0)));
    }

    private static JsonNode wrap(JsonNode perf) {
        var m = com.fasterxml.jackson.databind.node.JsonNodeFactory.instance.objectNode();
        var resp = m.putObject("response");
        resp.put("status", perf.get("status").asInt());
        resp.set("body", perf.get("body"));
        return m;
    }

    @Test
    void seedAvailabilityMatchesMonolithForEveryPerformance() {
        JsonNode fixture = contract("availability_seed_all_performances");
        assertThat(fixture.get("performances")).hasSize(24);
        for (JsonNode perf : fixture.get("performances")) {
            assertAvailability(perf.get("performanceId").asLong(), wrap(perf));
        }
        Long inventory = jdbc.queryForObject("SELECT COUNT(*) FROM seat_inventory", Long.class);
        assertThat(inventory).isEqualTo(152_400L);
    }

    @Test
    void unknownPerformanceAvailabilityIsZeros() {
        assertAvailability(999, contract("availability_unknown_performance"));
    }

    @Test
    void seedStatsMatchMonolithSeatCounts() {
        JsonNode expected = contract("stats_seed").get("response").get("body");
        JsonNode stats = get("/stats").getBody();
        assertThat(stats.get("seatsSold").asLong()).isEqualTo(expected.get("seatsSold").asLong());
        assertThat(stats.get("seatsHeld").asLong()).isEqualTo(expected.get("seatsHeld").asLong());
        assertThat(stats.get("seatsAvailable").asLong()).isEqualTo(152_400L);
        assertThat(stats.get("holdsByStatus").fieldNames()).toIterable()
                .containsExactly("ACTIVE", "CONVERTED", "EXPIRED", "RELEASED");
    }

    @Test
    void firstHoldPicksTheSameBestAvailableSeatsAsTheMonolith() {
        JsonNode expected = contract("order_perf1_qty2");
        ResponseEntity<JsonNode> r = post("/api/holds", hold(1, 2, null));
        assertThat(r.getStatusCode().value()).isEqualTo(201);
        JsonNode body = r.getBody();
        assertThat(body.get("performanceId").asLong()).isEqualTo(1);
        assertThat(body.get("holdRef").asText()).matches("H-[A-Z2-9]{10}");
        assertThat(labels(body.get("seats"), "section", "rowLabel", "seatNumber"))
                .isEqualTo(labels(expected.get("response").get("body").get("items"), "section", "row_label", "seat_number"));
        // zone tally taken after the hold: two premium seats are no longer available
        JsonNode tally = body.get("zoneTally");
        assertThat(tally).hasSize(3);
        assertThat(tally.get(0).get("notAvailable").asLong()).isEqualTo(2);
        long total = 0;
        for (JsonNode z : tally) {
            total += z.get("total").asLong();
        }
        assertThat(total).isEqualTo(20_000L);
        JsonNode seed = contract("availability_seed_all_performances").get("performances").get(0).get("body");
        JsonNode after = get("/api/performances/1/availability").getBody();
        assertThat(after.get("available").asLong()).isEqualTo(seed.get("available").asLong() - 2);
        assertThat(after.get("held").asLong()).isEqualTo(2);
        assertThat(after.get("sold").asLong()).isEqualTo(seed.get("sold").asLong());
    }

    @Test
    void sectionFilterPicksTheSameSeatsAsTheMonolith() {
        JsonNode expected = contract("order_perf1_section_a02");
        ResponseEntity<JsonNode> r = post("/api/holds", hold(1, 2, "A02"));
        assertThat(r.getStatusCode().value()).isEqualTo(201);
        assertThat(labels(r.getBody().get("seats"), "section", "rowLabel", "seatNumber"))
                .isEqualTo(labels(expected.get("response").get("body").get("items"), "section", "row_label", "seat_number"));
    }

    @Test
    void replayedSalesScenarioMatchesMonolithAvailabilityHoldsAndStats() {
        // 1. two seats confirmed
        holdAndConfirm(1, 2, null, "BO-YNUY2QGKSP", contract("order_perf1_qty2"));
        assertAvailability(1, contract("availability_perf1_after_first_sale"));

        // 2. three seats, card declined -> payment-failed -> RELEASED, seats back
        JsonNode declined = contract("order_perf1_declined");
        ResponseEntity<JsonNode> h = post("/api/holds", hold(1, 3, null));
        assertThat(h.getStatusCode().value()).isEqualTo(201);
        assertThat(labels(h.getBody().get("seats"), "section", "rowLabel", "seatNumber"))
                .isEqualTo(labels(declined.get("response").get("body").get("items"), "section", "row_label", "seat_number"));
        String declinedHold = h.getBody().get("holdRef").asText();
        ResponseEntity<JsonNode> pf = post("/events/payment-failed", Map.of("orderRef", "BO-PX7SVLG2NT", "holdRef", declinedHold,
                "outcome", "DECLINED", "orderStatus", "PAYMENT_FAILED", "amountCents", 64254, "cardLast4", "0000",
                "attemptNo", 1, "latencyMs", 120, "failedAt", "2026-01-01T00:00:00Z"));
        assertThat(pf.getBody().get("applied").asBoolean()).isTrue();
        assertAvailability(1, contract("availability_perf1_after_decline"));

        // 3. section A02, 8 seats (max_per_order), hall performance
        holdAndConfirm(1, 2, "A02", "BO-UHC54Q62UN", contract("order_perf1_section_a02"));
        holdAndConfirm(1, 8, null, "BO-ZV68S5C2S7", contract("order_perf1_qty8"));
        holdAndConfirm(7, 4, null, "BO-CE5VG5N8J4", contract("order_perf7_hall"));
        assertAvailability(1, contract("availability_perf1_after_sales"));
        assertAvailability(7, contract("availability_perf7_after_sale"));

        // 4. an ACTIVE 3-seat hold, nothing due, then aged past expires_at and swept
        ResponseEntity<JsonNode> cart = post("/api/holds", hold(1, 3, null));
        assertThat(cart.getStatusCode().value()).isEqualTo(201);
        assertAvailability(1, contract("availability_perf1_with_cart_hold"));
        assertThat(post("/api/holds/sweep", null).getBody()).isEqualTo(contract("expire_holds_nothing_due").get("response").get("body"));
        jdbc.update("UPDATE seat_holds SET expires_at = now() - interval '1 minute' WHERE status = 'ACTIVE'");
        ResponseEntity<JsonNode> sweep = post("/api/admin/expire-holds", null);
        assertThat(sweep.getStatusCode().value()).isEqualTo(contract("expire_holds_one_due").get("response").get("status").asInt());
        assertThat(sweep.getBody()).isEqualTo(contract("expire_holds_one_due").get("response").get("body"));
        assertAvailability(1, contract("availability_perf1_after_expiry"));

        // 5. reconciliation counts and per-hold outcome match the monolith's database after the same scenario
        JsonNode expectedStats = contract("stats_after_scenario").get("response").get("body");
        JsonNode stats = get("/stats").getBody();
        assertThat(stats.get("seatsSold").asLong()).isEqualTo(expectedStats.get("seatsSold").asLong());
        assertThat(stats.get("seatsHeld").asLong()).isEqualTo(expectedStats.get("seatsHeld").asLong());
        assertThat(stats.get("seatsAvailable").asLong()).isEqualTo(152_400L - expectedStats.get("seatsSold").asLong());

        JsonNode expectedHolds = contract("holds_after_scenario_db").get("holds");
        List<Map<String, Object>> holds = jdbc.queryForList("SELECT hold_ref, status FROM seat_holds ORDER BY id");
        assertThat(holds).hasSize(expectedHolds.size());
        Map<String, Long> byStatus = new java.util.TreeMap<>();
        for (int i = 0; i < holds.size(); i++) {
            JsonNode exp = expectedHolds.get(i);
            assertThat(holds.get(i).get("status")).isEqualTo(exp.get("status").asText());
            byStatus.merge(exp.get("status").asText(), 1L, Long::sum);
            JsonNode view = get("/api/holds/" + holds.get(i).get("hold_ref")).getBody();
            assertThat(view.get("status").asText()).isEqualTo(exp.get("status").asText());
            assertThat(view.get("active").asBoolean()).isFalse();
            assertThat(labels(view.get("seats"), "section", "rowLabel", "seatNumber"))
                    .isEqualTo(labels(exp.get("seats"), "section", "rowLabel", "seatNumber"));
            List<String> inventoryStatus = new ArrayList<>();
            exp.get("seats").forEach(s -> inventoryStatus.add(s.get("inventoryStatus").asText()));
            List<String> actualStatus = jdbc.queryForList("""
                    SELECT si.status FROM seat_hold_items hi JOIN seat_inventory si ON si.id = hi.seat_inventory_id
                    JOIN seats s ON s.id = si.seat_id JOIN venue_sections vs ON vs.id = s.section_id
                    JOIN seat_holds h ON h.id = hi.hold_id WHERE h.hold_ref = ?
                    ORDER BY vs.code, s.row_label, s.seat_number""", String.class, holds.get(i).get("hold_ref"));
            assertThat(actualStatus).isEqualTo(inventoryStatus);
        }
        byStatus.forEach((status, n) -> assertThat(stats.get("holdsByStatus").get(status).asLong()).isEqualTo(n));
        assertThat(stats.get("holdsByStatus").get("ACTIVE").asLong()).isZero();
    }

    @Test
    void idleSweepReleasesNothing() {
        JsonNode fixture = contract("expire_holds_idle");
        ResponseEntity<JsonNode> r = post("/api/admin/expire-holds", null);
        assertThat(r.getStatusCode().value()).isEqualTo(fixture.get("response").get("status").asInt());
        assertThat(r.getBody()).isEqualTo(fixture.get("response").get("body"));
        assertThat(post("/api/holds/sweep", null).getBody()).isEqualTo(fixture.get("response").get("body"));
    }

    @Test
    void healthIsUpLikeTheLegacyHealthEndpoint() {
        JsonNode fixture = contract("health");
        ResponseEntity<JsonNode> r = get("/actuator/health");
        assertThat(r.getStatusCode().value()).isEqualTo(fixture.get("response").get("status").asInt());
        assertThat(r.getBody().get("status").asText()).isEqualTo(fixture.get("response").get("body").get("status").asText());
        assertThat(get("/actuator/health/readiness").getStatusCode().value()).isEqualTo(200);
        assertThat(get("/actuator/health/liveness").getStatusCode().value()).isEqualTo(200);
    }
}
