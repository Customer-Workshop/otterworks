package com.boxoffice.payments.events;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

class PaymentCapturedTest {

    @Test
    void carriesTheContractPayloadFieldsInOrder() throws Exception {
        Instant at = Instant.parse("2026-09-29T00:00:05Z");
        OrderPlaced placed = Fixtures.orderPlaced("BO-TEST000001", "4242", at.plusSeconds(600));
        PaymentCaptured ev = PaymentCaptured.from(placed, "GW-ABCDEFGHJK", 1, 69, at);
        JsonNode json = Fixtures.JSON.valueToTree(ev);

        assertThat(fieldNames(json)).containsExactly("orderRef", "gatewayRef", "amountCents", "currency", "cardLast4",
                "attemptNo", "latencyMs", "capturedAt", "order");
        assertThat(fieldNames(json.get("order"))).containsExactly("customerEmail", "performanceId", "eventTitle",
                "venueName", "startsAt", "holdRef", "totalCents", "items");
        assertThat(fieldNames(json.get("order").get("items").get(0))).containsExactly("seatInventoryId", "section",
                "rowLabel", "seatNumber", "zoneCode");
        assertThat(json.get("amountCents").asLong()).isEqualTo(42836);
        assertThat(json.get("capturedAt").asText()).isEqualTo("2026-09-29T00:00:05Z");
        assertThat(json.get("order").get("items")).hasSize(2);
    }

    @Test
    void failedPayloadHasNullGatewayRefOnTimeoutAndExpiry() {
        PaymentFailed timeout = new PaymentFailed("BO-1", "HLD-1", "TIMEOUT", "PAYMENT_TIMEOUT", 42836, "4242", 1, 4000, null, Instant.EPOCH);
        JsonNode json = Fixtures.JSON.valueToTree(timeout);
        assertThat(fieldNames(json)).containsExactly("orderRef", "holdRef", "outcome", "orderStatus", "amountCents",
                "cardLast4", "attemptNo", "latencyMs", "gatewayRef", "failedAt");
        assertThat(json.get("gatewayRef").isNull()).isTrue();
    }

    private static List<String> fieldNames(JsonNode node) {
        List<String> names = new java.util.ArrayList<>();
        node.fieldNames().forEachRemaining(names::add);
        return names;
    }
}
