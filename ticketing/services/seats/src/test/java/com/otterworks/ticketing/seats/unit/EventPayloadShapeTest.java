package com.otterworks.ticketing.seats.unit;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.otterworks.ticketing.seats.domain.Dtos;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.boot.jackson.JsonComponentModule;

/** The hold-expired payload field names are a shared contract (decomposition.json). */
class EventPayloadShapeTest {

    private final ObjectMapper json = new ObjectMapper().findAndRegisterModules().registerModule(new JsonComponentModule())
            .disable(com.fasterxml.jackson.databind.SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

    @Test
    void holdExpiredHasContractFields() throws Exception {
        var e = new Dtos.HoldExpired("H-ABCDEFGHJK", 1L, null, List.of(10L, 11L), Instant.parse("2026-01-01T00:00:00Z"));
        JsonNode n = json.readTree(json.writeValueAsString(e));
        assertThat(n.fieldNames()).toIterable().containsExactlyInAnyOrder(
                "holdRef", "performanceId", "orderRef", "seatInventoryIds", "expiredAt");
        assertThat(n.get("orderRef").isNull()).isTrue();
        assertThat(n.get("seatInventoryIds")).hasSize(2);
        assertThat(n.get("expiredAt").asText()).isEqualTo("2026-01-01T00:00:00Z");
    }

    @Test
    void holdCreatedHasContractFields() throws Exception {
        var seat = new Dtos.SeatView(1, "A01", "R01", 1, 1, "P1", "Premium");
        var created = new Dtos.HoldCreated("H-ABCDEFGHJK", 1, Instant.now(), List.of(seat), List.of(new Dtos.ZoneTally(1, 1, 4000)));
        JsonNode n = json.readTree(json.writeValueAsString(created));
        assertThat(n.fieldNames()).toIterable().containsExactlyInAnyOrder("holdRef", "performanceId", "expiresAt", "seats", "zoneTally");
        assertThat(n.get("seats").get(0).fieldNames()).toIterable().containsExactlyInAnyOrder(
                "seatInventoryId", "section", "rowLabel", "seatNumber", "priceZoneId", "zoneCode", "zoneName");
        assertThat(n.get("zoneTally").get(0).fieldNames()).toIterable().containsExactlyInAnyOrder("priceZoneId", "notAvailable", "total");
    }
}
