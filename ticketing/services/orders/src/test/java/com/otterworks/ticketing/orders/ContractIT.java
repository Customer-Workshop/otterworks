package com.otterworks.ticketing.orders;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.otterworks.ticketing.orders.support.IntegrationTestBase;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

/**
 * Contract tests: every fixture under src/test/resources/contracts was recorded from the monolith
 * (see record.py) on the same synthetic seed. The monolith answered synchronously (201 CONFIRMED /
 * 402 PAYMENT_FAILED); orders answers 202 PENDING_PAYMENT and converges through the inboxes, so each
 * case asserts the same totals, statuses, seat counts and error codes after the downstream events.
 */
class ContractIT extends IntegrationTestBase {

    private static final Path CONTRACTS = Paths.get("src/test/resources/contracts");

    static Stream<Arguments> fixtures() throws IOException {
        try (Stream<Path> files = Files.list(CONTRACTS)) {
            return files.filter(p -> p.toString().endsWith(".json")).sorted()
                    .map(p -> Arguments.of(p.getFileName().toString().replace(".json", ""), p)).toList().stream();
        }
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("fixtures")
    void matchesMonolith(String name, Path fixture) throws Exception {
        JsonNode rec = json.readTree(Files.readString(fixture));
        JsonNode request = rec.path("request");
        JsonNode expected = rec.path("response");
        if (name.startsWith("purchase_")) {
            purchase(request, expected);
        } else if (name.equals("order_lookup_not_found")) {
            Response r = get(request.path("path").asText());
            assertThat(r.status()).isEqualTo(404);
            assertThat(r.body().path("error").asText()).isEqualTo("NOT_FOUND");
        } else if (name.startsWith("order_lookup_")) {
            orderLookup(expected.path("body"));
        } else if (name.equals("stats")) {
            stats(expected.path("body"));
        } else {
            throw new IllegalStateException("no contract handler for " + name);
        }
    }

    private void purchase(JsonNode request, JsonNode expected) throws Exception {
        JsonNode body = request.path("body");
        int expectedStatus = expected.path("status").asInt();
        JsonNode expectedBody = expected.path("body");
        if (body.isTextual()) {
            Response r = post("/api/purchase", body.asText());
            assertThat(r.status()).isEqualTo(expectedStatus);
            assertThat(r.body().path("error").asText()).isEqualTo(expectedBody.path("error").asText());
            return;
        }
        if (expectedStatus >= 400 && expectedStatus != 402) {
            // seats owns quantity / performance / availability validation: its answer passes straight through
            stubHoldError(expectedStatus, expectedBody.path("error").asText(), expectedBody.path("message").asText());
            Response r = post("/api/purchase", body);
            assertThat(r.status()).isEqualTo(expectedStatus);
            assertThat(r.body().path("error").asText()).isEqualTo(expectedBody.path("error").asText());
            return;
        }
        ObjectNode req = body.deepCopy();
        req.put("clientRef", "contract-" + UUID.randomUUID());
        long performanceId = req.path("performanceId").asLong();
        int quantity = req.path("quantity").asInt(2);
        String section = req.path("section").isTextual() ? req.path("section").asText() : null;
        stubHold(seatsStub.hold("HD-" + UUID.randomUUID().toString().substring(0, 10).toUpperCase(), performanceId,
                quantity, section, 0));

        Response placed = post("/api/purchase", req);
        assertThat(placed.status()).isEqualTo(202);
        assertThat(placed.body().path("status").asText()).isEqualTo("PENDING_PAYMENT");
        assertThat(placed.body().path("paymentOutcome").asText()).isEqualTo("PENDING");
        assertThat(placed.body().path("tickets").asInt()).isZero();
        assertThat(placed.body().path("totalCents").asLong()).isEqualTo(expectedBody.path("totalCents").asLong());
        String orderRef = placed.body().path("orderRef").asText();
        assertThat(orderRef).matches("BO-[A-Z2-9]{10}");

        Response converged = converge(orderRef, expectedBody.path("paymentOutcome").asText());
        assertThat(converged.body().path("status").asText()).isEqualTo(expectedBody.path("status").asText());
        assertThat(converged.body().path("paymentOutcome").asText()).isEqualTo(expectedBody.path("paymentOutcome").asText());
        assertThat(converged.body().path("total_cents").asLong()).isEqualTo(expectedBody.path("totalCents").asLong());
        assertThat(converged.body().path("tickets").asLong()).isEqualTo(expectedBody.path("tickets").asLong());
        assertThat(converged.body().path("items").size()).isEqualTo(quantity);
    }

    /** Replays what payments/confirmations do after order-placed, then returns GET /api/orders/{ref}. */
    private Response converge(String orderRef, String outcome) throws Exception {
        Response before = get("/api/orders/" + orderRef);
        assertThat(before.status()).isEqualTo(200);
        String holdRef = before.body().path("hold_ref").asText();
        if ("APPROVED".equals(outcome)) {
            List<Map<String, Object>> tickets = new ArrayList<>();
            for (JsonNode item : before.body().path("items")) {
                Map<String, Object> t = new LinkedHashMap<>();
                t.put("ticketCode", "TK-" + UUID.randomUUID().toString().substring(0, 10).toUpperCase());
                t.put("seatInventoryId", item.path("seat_inventory_id").asLong());
                t.put("barcode", UUID.randomUUID().toString());
                tickets.add(t);
            }
            Map<String, Object> event = new LinkedHashMap<>();
            event.put("orderRef", orderRef);
            event.put("holdRef", holdRef);
            event.put("performanceId", before.body().path("performance_id").asLong());
            event.put("ticketCount", tickets.size());
            event.put("tickets", tickets);
            event.put("recipient", before.body().path("email").asText());
            event.put("confirmedAt", "2026-01-01T00:00:00Z");
            Response ack = post("/events/order-confirmed", event);
            assertThat(ack.status()).isEqualTo(200);
            assertThat(ack.body().path("applied").asBoolean()).isTrue();
        } else {
            Map<String, Object> event = new LinkedHashMap<>();
            event.put("orderRef", orderRef);
            event.put("holdRef", holdRef);
            event.put("outcome", outcome);
            event.put("orderStatus", "DECLINED".equals(outcome) ? "PAYMENT_FAILED"
                    : "TIMEOUT".equals(outcome) ? "PAYMENT_TIMEOUT" : "CANCELLED");
            event.put("amountCents", before.body().path("total_cents").asLong());
            event.put("cardLast4", "0000");
            event.put("attemptNo", 1);
            event.put("latencyMs", 80);
            event.put("gatewayRef", "DECLINED".equals(outcome) ? "GW-SYNTH" : null);
            event.put("failedAt", "2026-01-01T00:00:00Z");
            Response ack = post("/events/payment-failed", event);
            assertThat(ack.status()).isEqualTo(200);
            assertThat(ack.body().path("applied").asBoolean()).isTrue();
        }
        return get("/api/orders/" + orderRef);
    }

    /** GET /api/orders/{ref} shape and values for the recorded confirmed / declined orders. */
    private void orderLookup(JsonNode expectedOrder) throws Exception {
        boolean declined = "PAYMENT_FAILED".equals(expectedOrder.path("status").asText());
        Map<String, Object> req = new LinkedHashMap<>();
        req.put("performanceId", expectedOrder.path("performance_id").asLong());
        req.put("email", expectedOrder.path("email").asText());
        req.put("quantity", expectedOrder.path("items").size());
        req.put("clientRef", "lookup-" + UUID.randomUUID());
        if (declined) {
            req.put("cardLast4", "0000");
        }
        stubHold(seatsStub.hold("HD-LOOKUP" + (declined ? "DECL" : "CONF"), expectedOrder.path("performance_id").asLong(),
                expectedOrder.path("items").size(), null, 0));
        Response placed = post("/api/purchase", req);
        assertThat(placed.status()).isEqualTo(202);
        Response order = converge(placed.body().path("orderRef").asText(), declined ? "DECLINED" : "APPROVED");

        JsonNode o = order.body();
        for (String field : List.of("order_ref", "status", "subtotal_cents", "fees_cents", "total_cents", "channel",
                "email", "event_title", "starts_at", "venue_name", "created_at", "items", "paymentOutcome")) {
            assertThat(o.has(field)).as("field %s", field).isTrue();
        }
        assertThat(o.path("status").asText()).isEqualTo(expectedOrder.path("status").asText());
        assertThat(o.path("subtotal_cents").asLong()).isEqualTo(expectedOrder.path("subtotal_cents").asLong());
        assertThat(o.path("fees_cents").asLong()).isEqualTo(expectedOrder.path("fees_cents").asLong());
        assertThat(o.path("total_cents").asLong()).isEqualTo(expectedOrder.path("total_cents").asLong());
        assertThat(o.path("channel").asText()).isEqualTo(expectedOrder.path("channel").asText());
        assertThat(o.path("email").asText()).isEqualTo(expectedOrder.path("email").asText());
        assertThat(o.path("event_title").asText()).isEqualTo(expectedOrder.path("event_title").asText());
        assertThat(o.path("venue_name").asText()).isEqualTo(expectedOrder.path("venue_name").asText());
        assertThat(o.path("starts_at").asText()).matches("\\d{4}-\\d{2}-\\d{2}T20:00:00Z");
        assertThat(o.path("paymentOutcome").asText()).isEqualTo(declined ? "DECLINED" : "APPROVED");
        assertThat(o.path("items").size()).isEqualTo(expectedOrder.path("items").size());
        for (int i = 0; i < o.path("items").size(); i++) {
            JsonNode mine = o.path("items").get(i);
            JsonNode theirs = expectedOrder.path("items").get(i);
            for (String field : List.of("price_cents", "section", "row_label", "seat_number", "zone", "ticket_code")) {
                assertThat(mine.has(field)).as("item field %s", field).isTrue();
            }
            assertThat(mine.path("price_cents").asLong()).isEqualTo(theirs.path("price_cents").asLong());
            assertThat(mine.path("zone").asText()).isEqualTo(theirs.path("zone").asText());
            assertThat(mine.path("section").asText()).isEqualTo(theirs.path("section").asText());
            assertThat(mine.path("row_label").asText()).isEqualTo(theirs.path("row_label").asText());
            if (declined) {
                assertThat(mine.path("ticket_code").isNull()).isTrue();
            } else {
                assertThat(mine.path("ticket_code").asText()).startsWith("TK-");
            }
        }
        assertThat(o.path("fees").size()).isEqualTo(2); // SERVICE + FACILITY, MOBILE delivery is free
    }

    /** /stats keeps the order-side counts the monolith reported, partitioned to this service. */
    private void stats(JsonNode expectedStats) throws Exception {
        Response r = get("/stats");
        assertThat(r.status()).isEqualTo(200);
        for (String field : List.of("ordersTotal", "ordersByStatus")) {
            assertThat(expectedStats.has(field)).isTrue();
            assertThat(r.body().has(field)).as("stats field %s", field).isTrue();
        }
        long sum = 0;
        for (JsonNode n : r.body().path("ordersByStatus")) {
            sum += n.asLong();
        }
        assertThat(r.body().path("ordersTotal").asLong()).isEqualTo(sum);
        assertThat(r.body().has("outboxUnpublished")).isTrue();
        assertThat(r.body().has("promoUses")).isTrue();
        // the monolith's payment / ticket / seat counters now live in payments, confirmations and seats
        for (String other : List.of("paymentsCaptured", "ticketsIssued", "seatsSold", "seatsHeld")) {
            assertThat(r.body().has(other)).isFalse();
        }
    }

    static String read(Path p) {
        try {
            return Files.readString(p);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
